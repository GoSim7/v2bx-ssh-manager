from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from v2bx_manager.config_model import (
    DEFAULT_CUSTOM_INBOUND,
    DEFAULT_CUSTOM_OUTBOUND,
    DEFAULT_DNS,
    DEFAULT_HY2_CONFIG,
    DEFAULT_ROUTE,
    DEFAULT_SING_ORIGIN,
    default_config,
    dump_config,
    parse_config,
)
from v2bx_manager.ssh_client import CommandResult, SSHClient


CONFIG_PATH = "/etc/V2bX/config.json"
INSTALL_URL = "https://raw.githubusercontent.com/wyx2685/V2bX-script/master/install.sh"


class RemoteV2bX:
    def __init__(self, ssh: SSHClient) -> None:
        self.ssh = ssh

    def test(self) -> CommandResult:
        return self.ssh.run("uname -a && id", timeout=30)

    def detect(self) -> CommandResult:
        command = (
            "if [ -x /usr/local/V2bX/V2bX ]; then "
            "echo installed; /usr/local/V2bX/V2bX version 2>/dev/null || true; "
            "else echo missing; fi"
        )
        return self.ssh.run(command, timeout=60)

    def install(self) -> CommandResult:
        command = (
            "set -e; "
            f"curl -Ls '{INSTALL_URL}' -o /tmp/v2bx-install.sh; "
            "chmod +x /tmp/v2bx-install.sh; "
            "printf 'n\\n' | bash /tmp/v2bx-install.sh"
        )
        return self.ssh.run(command, timeout=900)

    def service_status(self) -> CommandResult:
        command = (
            "if command -v systemctl >/dev/null 2>&1; then "
            "systemctl status V2bX --no-pager -l; "
            "else service V2bX status; fi"
        )
        return self.ssh.run(command, timeout=60)

    def restart(self) -> CommandResult:
        command = (
            "if command -v systemctl >/dev/null 2>&1; then "
            "systemctl restart V2bX; "
            "else service V2bX restart; fi"
        )
        return self.ssh.run(command, timeout=120)

    def logs(self, lines: int = 120) -> CommandResult:
        command = (
            "if command -v journalctl >/dev/null 2>&1; then "
            f"journalctl -u V2bX.service -n {int(lines)} --no-pager; "
            "else tail -n 120 /var/log/messages 2>/dev/null || true; fi"
        )
        return self.ssh.run(command, timeout=90)

    def diagnose_paths(self) -> CommandResult:
        command = (
            "echo '== V2bX service =='; "
            "if command -v systemctl >/dev/null 2>&1; then "
            "systemctl show V2bX -p FragmentPath -p WorkingDirectory -p ExecStart --no-pager 2>/dev/null || true; "
            "systemctl cat V2bX --no-pager 2>/dev/null || true; "
            "else service V2bX status 2>/dev/null || true; fi; "
            "echo; echo '== running process =='; "
            "ps -eo pid,args | grep '[V]2bX' || true; "
            "echo; echo '== possible config files =='; "
            "for f in /etc/V2bX/config.json /usr/local/V2bX/config.json; do "
            "if [ -f \"$f\" ]; then echo \"-- $f\"; ls -l \"$f\"; grep -nE '\"Type\"|\"OriginalPath\"|\"ApiHost\"|\"NodeID\"|\"NodeType\"' \"$f\" | head -n 80; "
            "else echo \"-- missing $f\"; fi; done; "
            "echo; echo '== fragment files =='; "
            "for f in /etc/V2bX/custom_outbound.json /etc/V2bX/route.json /etc/V2bX/sing_origin.json /etc/V2bX/hy2config.yaml; do "
            "if [ -f \"$f\" ]; then ls -l \"$f\"; else echo \"missing $f\"; fi; done; "
            "echo; echo '== recent error lines =='; "
            "if command -v journalctl >/dev/null 2>&1; then journalctl -u V2bX.service -n 80 --no-pager | grep -Ei 'config|core|error|failed|sing|xray|hysteria' || true; fi"
        )
        return self.ssh.run(command, timeout=90)

    def open_firewall(self) -> CommandResult:
        command = (
            "systemctl stop firewalld.service 2>/dev/null || true; "
            "systemctl disable firewalld.service 2>/dev/null || true; "
            "setenforce 0 2>/dev/null || true; "
            "ufw disable 2>/dev/null || true; "
            "iptables -P INPUT ACCEPT 2>/dev/null || true; "
            "iptables -P FORWARD ACCEPT 2>/dev/null || true; "
            "iptables -P OUTPUT ACCEPT 2>/dev/null || true; "
            "iptables -t nat -F 2>/dev/null || true; "
            "iptables -t mangle -F 2>/dev/null || true; "
            "iptables -F 2>/dev/null || true; "
            "iptables -X 2>/dev/null || true; "
            "netfilter-persistent save 2>/dev/null || true; "
            "echo firewall-opened"
        )
        return self.ssh.run(command, timeout=120)

    def pull_config(self) -> dict[str, Any]:
        exists = self.ssh.run(f"test -f {CONFIG_PATH}", timeout=20)
        if not exists.ok:
            return default_config()
        return parse_config(self.ssh.read_text(CONFIG_PATH))

    def backup_config(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"{CONFIG_PATH}.bak-{timestamp}"
        result = self.ssh.run(
            f"mkdir -p /etc/V2bX && if [ -f {CONFIG_PATH} ]; then cp {CONFIG_PATH} {backup_path}; else touch {backup_path}; fi",
            timeout=30,
        )
        if not result.ok:
            raise RuntimeError(result.output or "备份配置失败")
        return backup_path

    def ensure_fragment_files(self, config: dict[str, Any]) -> None:
        outbound = self.ssh.run("test -f /etc/V2bX/custom_outbound.json", timeout=20)
        if not outbound.ok:
            self.ssh.write_text("/etc/V2bX/custom_outbound.json", DEFAULT_CUSTOM_OUTBOUND)
        route = self.ssh.run("test -f /etc/V2bX/route.json", timeout=20)
        if not route.ok:
            self.ssh.write_text("/etc/V2bX/route.json", DEFAULT_ROUTE)
        dns = self.ssh.run("test -f /etc/V2bX/dns.json", timeout=20)
        if not dns.ok:
            self.ssh.write_text("/etc/V2bX/dns.json", DEFAULT_DNS)
        inbound = self.ssh.run("test -f /etc/V2bX/custom_inbound.json", timeout=20)
        if not inbound.ok:
            self.ssh.write_text("/etc/V2bX/custom_inbound.json", DEFAULT_CUSTOM_INBOUND)
        cores = config.get("Cores", [])
        nodes = config.get("Nodes", [])
        has_sing = any(isinstance(core, dict) and core.get("Type") == "sing" for core in cores)
        has_hy2 = any(isinstance(core, dict) and core.get("Type") == "hysteria2" for core in cores)
        has_hy2 = has_hy2 or any(
            isinstance(node, dict) and str(node.get("NodeType", "")).lower() == "hysteria2"
            for node in nodes
        )
        if has_sing:
            sing_origin = self.ssh.run("test -f /etc/V2bX/sing_origin.json", timeout=20)
            if not sing_origin.ok:
                self.ssh.write_text("/etc/V2bX/sing_origin.json", DEFAULT_SING_ORIGIN)
        if has_hy2:
            hy2_config = self.ssh.run("test -f /etc/V2bX/hy2config.yaml", timeout=20)
            if not hy2_config.ok:
                self.ssh.write_text("/etc/V2bX/hy2config.yaml", DEFAULT_HY2_CONFIG)

    def apply_config(self, config: dict[str, Any]) -> tuple[str, CommandResult]:
        backup_path = self.backup_config()
        self.ensure_fragment_files(config)
        self.ssh.write_text(CONFIG_PATH, dump_config(config))
        restart_result = self.restart()
        return backup_path, restart_result

    def deploy_nodes_via_script(self, config: dict[str, Any]) -> CommandResult:
        nodes = config.get("Nodes", [])
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("没有可部署的节点。请先在界面添加 VLESS Reality 或 Shadowsocks 节点。")

        target_summary = self._format_target_nodes(nodes)
        input_text = self._build_generate_input(nodes)
        backup_path = self.backup_config()
        temp_path = f"/tmp/v2bx-manager-generate-{datetime.now().strftime('%Y%m%d%H%M%S')}.input"
        self.ssh.write_text(temp_path, input_text, mode=0o600)
        command = (
            "set +e; "
            "if command -v V2bX >/dev/null 2>&1; then mgr=V2bX; "
            "elif command -v v2bx >/dev/null 2>&1; then mgr=v2bx; "
            "elif [ -x /usr/bin/V2bX ]; then mgr=/usr/bin/V2bX; "
            "else echo 'V2bX 管理脚本不存在，请先安装 V2bX'; rm -f '{temp}'; exit 127; fi; "
            "$mgr generate < '{temp}'; status=$?; rm -f '{temp}'; exit $status"
        ).format(temp=temp_path)
        script_result = self.ssh.run(command, timeout=900)
        output_parts = [
            f"预部署备份: {backup_path}",
            target_summary,
            "脚本生成输出:",
            script_result.output.strip(),
        ]
        if not script_result.ok:
            return CommandResult(
                command="V2bX generate < generated input",
                exit_status=script_result.exit_status,
                output="\n".join(part for part in output_parts if part),
            )

        restart_exit_status = 0
        try:
            patch_changed = self._patch_reality_cert_modes(nodes)
        except Exception as error:  # noqa: BLE001 - keep script output visible with the failure
            output_parts.append(f"Reality 节点修正失败，远程配置可能未完整生成: {error}")
            return CommandResult(
                command="V2bX generate < generated input",
                exit_status=1,
                output="\n".join(part for part in output_parts if part),
            )
        if patch_changed:
            restart_result = self.restart()
            output_parts.extend(
                [
                    "已按界面选择修正 VLESS Reality 节点的 CertMode=reality。",
                    "修正后重启输出:",
                    restart_result.output.strip(),
                ]
            )
            restart_exit_status = restart_result.exit_status

        verification_ok, verification_message = self._verify_deployed_nodes(nodes)
        output_parts.append(verification_message)
        if not verification_ok:
            exit_status = 1
        else:
            exit_status = restart_exit_status

        return CommandResult(
            command="V2bX generate < generated input",
            exit_status=exit_status,
            output="\n".join(part for part in output_parts if part),
        )

    def _build_generate_input(self, nodes: list[Any]) -> str:
        lines: list[str] = ["y"]
        script_isreality = ""
        script_istls = ""
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError(f"节点 {index + 1} 格式不是对象")
            api_host = str(node.get("ApiHost", "")).strip()
            api_key = str(node.get("ApiKey", "")).strip()
            node_id = str(node.get("NodeID", "")).strip()
            node_type = str(node.get("NodeType", "")).strip().lower()
            core = str(node.get("Core", "")).strip().lower()
            cert = node.get("CertConfig", {}) if isinstance(node.get("CertConfig"), dict) else {}
            cert_mode = str(cert.get("CertMode", "none")).strip().lower()
            if core != "xray":
                raise ValueError(f"节点 {index + 1} 不是 xray core，脚本部署模式只支持 xray")
            if not api_host or not api_key or not node_id:
                raise ValueError(f"节点 {index + 1} 缺少 ApiHost、ApiKey 或 NodeID")
            try:
                parsed_node_id = int(node_id)
            except ValueError as error:
                raise ValueError(f"节点 {index + 1} 的 NodeID 必须是数字") from error
            if parsed_node_id <= 0:
                raise ValueError(f"节点 {index + 1} 的 NodeID 必须是正整数")
            if node_type not in ("vless", "shadowsocks"):
                raise ValueError(f"节点 {index + 1} 类型为 {node_type}，脚本部署模式只支持 vless reality 和 shadowsocks")
            if node_type == "vless" and cert_mode != "reality":
                raise ValueError(f"节点 {index + 1} 是 vless，但 CertMode 不是 reality")
            if node_type == "shadowsocks" and cert_mode not in ("none", ""):
                raise ValueError(f"节点 {index + 1} 是 shadowsocks，脚本部署模式要求 CertMode 为 none")

            if index == 0:
                lines.extend([api_host, api_key, "n"])
            else:
                lines.extend(["", api_host, api_key])

            lines.extend(["1", node_id])
            if node_type == "vless":
                lines.extend(["2", "y"])
                script_isreality = "y"
            else:
                lines.append("1")
                # The upstream script keeps isreality/istls between nodes. After
                # a VLESS Reality node, Shadowsocks no longer prompts for TLS.
                if script_isreality.lower() != "y" and script_istls.lower() != "y":
                    lines.append("n")
                    script_istls = "n"

        lines.extend(["n", "", "17"])
        return "\n".join(lines) + "\n"

    def _node_identity(self, node: dict[str, Any]) -> tuple[str, int, str] | None:
        try:
            return (
                str(node.get("ApiHost", "")).strip(),
                int(node.get("NodeID")),
                str(node.get("NodeType", "")).strip().lower(),
            )
        except (TypeError, ValueError):
            return None

    def _format_identity(self, identity: tuple[str, int, str]) -> str:
        api_host, node_id, node_type = identity
        return f"{api_host} / {node_type}:{node_id}"

    def _format_target_nodes(self, nodes: list[Any]) -> str:
        lines = [f"部署目标节点: {len(nodes)} 个"]
        for index, node in enumerate(nodes, start=1):
            if isinstance(node, dict):
                identity = self._node_identity(node)
                if identity is not None:
                    lines.append(f"{index}. {self._format_identity(identity)}")
                else:
                    lines.append(f"{index}. 节点身份无法解析")
            else:
                lines.append(f"{index}. 节点格式不是对象")
        return "\n".join(lines)

    def _verify_deployed_nodes(self, desired_nodes: list[Any]) -> tuple[bool, str]:
        desired = [
            identity
            for node in desired_nodes
            if isinstance(node, dict)
            for identity in [self._node_identity(node)]
            if identity is not None
        ]
        try:
            config = self.pull_config()
        except Exception as error:  # noqa: BLE001 - report remote config parse/read problems
            return False, f"部署后校验失败：无法读取或解析 {CONFIG_PATH}: {error}"
        actual_nodes = config.get("Nodes", [])
        actual = [
            identity
            for node in actual_nodes
            if isinstance(node, dict)
            for identity in [self._node_identity(node)]
            if identity is not None
        ]

        desired_counter = Counter(desired)
        actual_counter = Counter(actual)
        if desired_counter == actual_counter:
            return True, f"部署后校验通过：{len(actual)} 个节点已写入 {CONFIG_PATH}。"

        missing = list((desired_counter - actual_counter).elements())
        extra = list((actual_counter - desired_counter).elements())
        lines = [
            "部署后校验失败：脚本生成的节点和界面节点不一致。",
            f"界面节点数: {len(desired)}，远程配置节点数: {len(actual)}。",
        ]
        if missing:
            lines.append("缺失节点:")
            lines.extend(f"- {self._format_identity(identity)}" for identity in missing)
        if extra:
            lines.append("远程多出的节点:")
            lines.extend(f"- {self._format_identity(identity)}" for identity in extra)
        lines.append("请重新部署或使用回滚配置，避免继续使用不完整配置。")
        return False, "\n".join(lines)

    def _patch_reality_cert_modes(self, desired_nodes: list[Any]) -> bool:
        reality_keys = {
            (str(node.get("ApiHost", "")).strip(), int(node.get("NodeID")), str(node.get("NodeType", "")).strip().lower())
            for node in desired_nodes
            if isinstance(node, dict)
            and str(node.get("NodeType", "")).strip().lower() == "vless"
            and isinstance(node.get("CertConfig"), dict)
            and str(node["CertConfig"].get("CertMode", "")).strip().lower() == "reality"
        }
        if not reality_keys:
            return False
        config = self.pull_config()
        changed = False
        for node in config.get("Nodes", []):
            if not isinstance(node, dict):
                continue
            try:
                key = (
                    str(node.get("ApiHost", "")).strip(),
                    int(node.get("NodeID")),
                    str(node.get("NodeType", "")).strip().lower(),
                )
            except (TypeError, ValueError):
                continue
            if key in reality_keys:
                cert = node.setdefault("CertConfig", {})
                if isinstance(cert, dict) and cert.get("CertMode") != "reality":
                    cert["CertMode"] = "reality"
                    changed = True
        if changed:
            self.ensure_fragment_files(config)
            self.ssh.write_text(CONFIG_PATH, dump_config(config))
        return changed

    def latest_backup(self) -> str | None:
        result = self.ssh.run(f"ls -1t {CONFIG_PATH}.bak-* 2>/dev/null | head -n 1", timeout=30)
        path = result.output.strip().splitlines()
        return path[0] if path else None

    def rollback_latest(self) -> CommandResult:
        backup = self.latest_backup()
        if not backup:
            raise RuntimeError("没有找到可回滚的配置备份")
        result = self.ssh.run(f"cp '{backup}' {CONFIG_PATH}", timeout=30)
        if not result.ok:
            raise RuntimeError(result.output or "回滚复制失败")
        return self.restart()
