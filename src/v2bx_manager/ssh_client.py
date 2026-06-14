from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

import paramiko


T = TypeVar("T")


@dataclass
class CommandResult:
    command: str
    exit_status: int
    output: str

    @property
    def ok(self) -> bool:
        return self.exit_status == 0


class SSHClient:
    def __init__(self) -> None:
        self.client: paramiko.SSHClient | None = None
        self.host = ""
        self.port = 22
        self.username = ""
        self.password = ""
        self.timeout = 12

    @property
    def connected(self) -> bool:
        transport = self.client.get_transport() if self.client else None
        return bool(transport and transport.is_active())

    @property
    def can_reconnect(self) -> bool:
        return bool(self.host and self.username and self.password)

    def connect(self, host: str, port: int, username: str, password: str, timeout: int = 12) -> None:
        self.close()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        try:
            self._connect_once()
        except Exception:
            self.host = ""
            self.port = 22
            self.username = ""
            self.password = ""
            self.timeout = 12
            raise

    def _connect_once(self) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            banner_timeout=self.timeout,
            auth_timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        self.client = client

    def ensure_connected(self) -> None:
        if self.connected:
            return
        if not self.can_reconnect:
            raise RuntimeError("SSH 未连接")
        self.close()
        self._connect_once()

    def _with_reconnect(self, operation: Callable[[], T]) -> T:
        self.ensure_connected()
        try:
            return operation()
        except (EOFError, OSError, RuntimeError, paramiko.SSHException, socket.error) as error:
            if isinstance(error, TimeoutError):
                raise
            self.close()
            self.ensure_connected()
            return operation()

    def close(self) -> None:
        if self.client:
            self.client.close()
        self.client = None

    def run(self, command: str, timeout: int = 300) -> CommandResult:
        return self._with_reconnect(lambda: self._run_once(command, timeout))

    def _run_once(self, command: str, timeout: int = 300) -> CommandResult:
        if not self.client:
            raise RuntimeError("SSH 未连接")
        transport = self.client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError("SSH transport 不可用")
        channel = transport.open_session()
        channel.get_pty()
        channel.exec_command(command)
        chunks: list[bytes] = []
        start = time.monotonic()
        while True:
            while channel.recv_ready():
                chunks.append(channel.recv(4096))
            while channel.recv_stderr_ready():
                chunks.append(channel.recv_stderr(4096))
            if channel.exit_status_ready():
                while channel.recv_ready():
                    chunks.append(channel.recv(4096))
                while channel.recv_stderr_ready():
                    chunks.append(channel.recv_stderr(4096))
                break
            if timeout and time.monotonic() - start > timeout:
                channel.close()
                raise TimeoutError(f"命令超时: {command}")
            time.sleep(0.1)
        exit_status = channel.recv_exit_status()
        output = b"".join(chunks).decode("utf-8", errors="replace")
        return CommandResult(command=command, exit_status=exit_status, output=output)

    def read_text(self, remote_path: str) -> str:
        def operation() -> str:
            if not self.client:
                raise RuntimeError("SSH 未连接")
            with self.client.open_sftp() as sftp:
                with sftp.open(remote_path, "rb") as handle:
                    return handle.read().decode("utf-8", errors="replace")

        return self._with_reconnect(operation)

    def write_text(self, remote_path: str, text: str, mode: int = 0o600) -> None:
        temp_path = f"/tmp/v2bx-manager-{int(time.time())}.tmp"

        def operation() -> None:
            if not self.client:
                raise RuntimeError("SSH 未连接")
            with self.client.open_sftp() as sftp:
                with sftp.open(temp_path, "wb") as handle:
                    handle.write(text.encode("utf-8"))

        self._with_reconnect(operation)
        result = self.run(f"mkdir -p \"$(dirname '{remote_path}')\" && install -m {oct(mode)[2:]} '{temp_path}' '{remote_path}' && rm -f '{temp_path}'")
        if not result.ok:
            raise RuntimeError(result.output or f"写入远程文件失败: {remote_path}")


def describe_connection_error(error: Exception) -> str:
    if isinstance(error, paramiko.AuthenticationException):
        return "SSH 认证失败，请检查用户名和密码。"
    if isinstance(error, paramiko.SSHException):
        return f"SSH 错误: {error}"
    if isinstance(error, socket.timeout):
        return "SSH 连接超时。"
    return str(error)
