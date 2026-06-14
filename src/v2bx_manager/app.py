from __future__ import annotations

import copy
import queue
import threading
from datetime import datetime
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from v2bx_manager import __version__
from v2bx_manager.config_model import (
    default_config,
    ensure_xray_core,
    make_node,
    node_summary,
    validate_config,
)
from v2bx_manager.remote_ops import RemoteV2bX
from v2bx_manager.ssh_client import CommandResult, SSHClient, describe_connection_error


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Bananas_V2bx v{__version__}")
        self.root.geometry("1220x760")
        self.root.minsize(1080, 680)

        self.ssh = SSHClient()
        self.remote = RemoteV2bX(self.ssh)
        self.config: dict[str, Any] = default_config()
        self.selected_index: int | None = None
        self.task_queue: queue.Queue[tuple[str, bool, Any]] = queue.Queue()
        self.task_running = False
        self.cell_editor: tk.Widget | None = None

        self._build_vars()
        self._build_ui()
        self.refresh_tree()
        self.log(f"软件版本: v{__version__}")
        self.log("双击表格单元格可直接编辑。VLESS 默认 Reality，Shadowsocks 默认 none。")

    def _build_vars(self) -> None:
        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar(value="22")
        self.username_var = tk.StringVar(value="root")
        self.password_var = tk.StringVar()
        self.connection_var = tk.StringVar(value="未连接")

        self.table_columns = ("index", "api_host", "api_key", "node_id", "node_type", "cert_mode")
        self.editable_columns = {"api_host", "api_key", "node_id", "node_type", "cert_mode"}

    def _build_ui(self) -> None:
        self.root.configure(bg="#edf8f1")
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=14, style="Glass.TFrame")
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(self.root, padding=(0, 14, 14, 14), style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self._build_connection_panel(left)
        self._build_action_panel(left)
        self._build_notebook(right)

    def _build_connection_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="服务器连接", padding=12, style="Glass.TLabelframe")
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="IP / 域名").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.host_var, width=24).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="端口").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.port_var, width=24).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="用户").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.username_var, width=24).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="密码").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.password_var, show="*", width=24).grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Button(frame, text="连接 / 测试", command=self.connect, style="Accent.TButton").grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(10, 4),
        )
        ttk.Label(frame, textvariable=self.connection_var, foreground="#137a4c").grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=4,
        )

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="远程操作", padding=12, style="Glass.TLabelframe")
        frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for index in range(2):
            frame.columnconfigure(index, weight=1)

        actions = [
            ("检测安装", self.detect_install),
            ("安装/更新", self.install_v2bx),
            ("拉取配置", self.pull_config),
            ("部署节点", self.deploy_nodes_via_script),
        ]
        for index, (label, callback) in enumerate(actions):
            row, col = divmod(index, 2)
            ttk.Button(frame, text=label, command=callback).grid(row=row, column=col, sticky="ew", padx=3, pady=4)

        hint = ttk.Label(
            frame,
            text="常规流程：连接 VPS -> 拉取配置 -> 编辑节点列表 -> 部署节点。",
            wraplength=250,
            foreground="#476657",
        )
        hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _build_notebook(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent, style="Glass.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")
        parent.rowconfigure(0, weight=1)

        nodes_tab = ttk.Frame(notebook, padding=12, style="Panel.TFrame")
        logs_tab = ttk.Frame(notebook, padding=12, style="Panel.TFrame")
        notebook.add(nodes_tab, text="节点配置")
        notebook.add(logs_tab, text="输出日志")

        self._build_nodes_tab(nodes_tab)
        self._build_logs_tab(logs_tab)

    def _build_nodes_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent, style="Panel.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(toolbar, text="新增节点", command=self.add_node, style="Accent.TButton").pack(side="left")
        ttk.Button(toolbar, text="删除选中", command=self.delete_selected_node).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="复制选中", command=self.copy_selected_node).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="清空列表", command=self.clear_node_list).pack(side="left", padx=(8, 0))

        self.node_tree = ttk.Treeview(parent, columns=self.table_columns, show="headings", selectmode="extended")
        headings = {
            "index": "#",
            "api_host": "ApiHost",
            "api_key": "ApiKey",
            "node_id": "NodeID",
            "node_type": "NodeType",
            "cert_mode": "CertMode",
        }
        widths = {
            "index": 48,
            "api_host": 330,
            "api_key": 310,
            "node_id": 90,
            "node_type": 130,
            "cert_mode": 120,
        }
        for column in self.table_columns:
            self.node_tree.heading(column, text=headings[column])
            self.node_tree.column(column, width=widths[column], minwidth=widths[column], anchor="w", stretch=True)
        self.node_tree.grid(row=1, column=0, sticky="nsew")
        self.node_tree.bind("<<TreeviewSelect>>", self.on_node_selected)
        self.node_tree.bind("<Double-1>", self.start_cell_edit)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.node_tree.yview)
        self.node_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=0, sticky="nse")

        footnote = ttk.Label(
            parent,
            text="双击单元格编辑；复制节点会自动分配新的 NodeID，部署前请确认它和面板里的真实节点一致。",
            foreground="#476657",
        )
        footnote.grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_logs_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(
            parent,
            height=24,
            wrap="word",
            bg="#f8fff9",
            fg="#173b2f",
            insertbackground="#173b2f",
            relief="flat",
            borderwidth=8,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log("应用已启动。")

    def refresh_tree(self) -> None:
        self.destroy_cell_editor()
        for item in self.node_tree.get_children():
            self.node_tree.delete(item)
        nodes = self.config.get("Nodes", [])
        if not isinstance(nodes, list):
            return
        for index, node in enumerate(nodes):
            if isinstance(node, dict):
                self.node_tree.insert("", "end", iid=str(index), values=node_summary(index + 1, node))

    def select_tree_index(self, index: int | None) -> None:
        self.node_tree.selection_remove(self.node_tree.selection())
        self.selected_index = index
        if index is None:
            return
        item_id = str(index)
        if self.node_tree.exists(item_id):
            self.node_tree.selection_set(item_id)
            self.node_tree.focus(item_id)
            self.node_tree.see(item_id)

    def selected_indices(self) -> list[int]:
        nodes = self.config.get("Nodes", [])
        max_index = len(nodes) - 1 if isinstance(nodes, list) else -1
        indices: list[int] = []
        for item_id in self.node_tree.selection():
            try:
                index = int(item_id)
            except ValueError:
                continue
            if 0 <= index <= max_index:
                indices.append(index)
        return sorted(set(indices))

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

    def run_task(
        self,
        label: str,
        func: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if self.task_running:
            messagebox.showinfo("任务进行中", "已有任务正在执行，请稍等。")
            return
        self.task_running = True
        self.log(f"开始: {label}")

        def worker() -> None:
            try:
                result = func()
                self.task_queue.put((label, True, (result, on_success)))
            except Exception as error:  # noqa: BLE001 - surface all task failures in the UI
                self.task_queue.put((label, False, (error, on_error)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(120, self.poll_tasks)

    def poll_tasks(self) -> None:
        try:
            label, ok, payload = self.task_queue.get_nowait()
        except queue.Empty:
            if self.task_running:
                self.root.after(120, self.poll_tasks)
            return
        self.task_running = False
        if ok:
            result, on_success = payload
            self.log(f"完成: {label}")
            if on_success:
                on_success(result)
        else:
            error, on_error = payload
            self.log(f"失败: {label}: {error}")
            if on_error:
                on_error(error)
            else:
                messagebox.showerror("操作失败", str(error))

    def connect(self) -> None:
        host = self.host_var.get().strip()
        username = self.username_var.get().strip() or "root"
        password = self.password_var.get()
        try:
            port = int(self.port_var.get().strip() or "22")
        except ValueError:
            messagebox.showerror("端口错误", "SSH 端口必须是数字。")
            return
        if not host:
            messagebox.showerror("缺少地址", "请输入 VPS IP 或域名。")
            return
        if not password:
            messagebox.showerror("缺少密码", "请输入 SSH 密码。")
            return

        def task() -> CommandResult:
            self.ssh.connect(host, port, username, password)
            return self.remote.test()

        def success(result: CommandResult) -> None:
            self.connection_var.set(f"已连接 {username}@{host}:{port}")
            self.log(result.output.strip())

        def error_handler(error: Exception) -> None:
            self.connection_var.set("未连接")
            messagebox.showerror("连接失败", describe_connection_error(error))

        self.run_task("SSH 连接测试", task, success, error_handler)

    def require_connection(self) -> bool:
        if not self.ssh.connected:
            if self.ssh.can_reconnect:
                self.connection_var.set("SSH 空闲/断开，将自动重连")
                self.log("SSH 当前不活跃，下一次远程操作会自动重连。")
                return True
            messagebox.showwarning("未连接", "请先连接 VPS。")
            return False
        return True

    def detect_install(self) -> None:
        if not self.require_connection():
            return
        self.run_task("检测 V2bX 安装", self.remote.detect, self.log_command_result)

    def install_v2bx(self) -> None:
        if not self.require_connection():
            return
        if not messagebox.askyesno(
            "确认安装/更新",
            "将在远程 VPS 执行 V2bX 官方 install.sh，并跳过交互式配置生成。\n\n"
            "这个按钮只安装或更新 V2bX 程序，不会部署表格里的节点。\n"
            "节点要生效，请安装后点击“部署节点”。\n\n"
            "继续吗？",
        ):
            return

        def success(result: CommandResult) -> None:
            self.log_command_result(result)
            if result.ok:
                self.log("安装/更新程序已完成；节点配置尚未部署，请点击“部署节点”。")

        self.run_task("安装/更新 V2bX 程序", self.remote.install, success)

    def pull_config(self) -> None:
        if not self.require_connection():
            return

        def success(config: dict[str, Any]) -> None:
            self.config = config
            ensure_xray_core(self.config)
            self.refresh_tree()
            self.select_tree_index(None)
            self.log(f"已拉取配置，节点数: {len(self.config.get('Nodes', []))}")

        self.run_task("拉取远程配置", self.remote.pull_config, success)

    def deploy_nodes_via_script(self) -> None:
        if not self.require_connection():
            return
        self.normalize_all_nodes()
        nodes = self.config.get("Nodes", [])
        if not isinstance(nodes, list) or not nodes:
            messagebox.showwarning("没有节点", "请先在列表中新增 VLESS Reality 或 Shadowsocks 节点。")
            return
        deploy_errors = self.deployable_node_errors(nodes)
        if deploy_errors:
            messagebox.showerror("节点检查失败", "\n".join(deploy_errors))
            return
        validation = validate_config(self.config)
        if not validation.ok:
            messagebox.showerror("配置校验失败", "\n".join(validation.errors))
            return
        if not messagebox.askyesno(
            "确认部署节点",
            "这会把当前表格中的节点写入远程 VPS。\n\n"
            "软件会远程执行 V2bX 官方 generate 流程，并按表格节点自动输入问答内容。\n"
            "支持：VLESS Reality 和 Shadowsocks。\n"
            "脚本会覆盖 /etc/V2bX/config.json，并自动重启 V2bX。\n\n"
            "继续吗？",
        ):
            return

        def success(result: CommandResult) -> None:
            self.log_command_result(result)
            if result.ok:
                self.log("节点部署流程已完成；请查看输出日志中的部署后校验结果。")

        self.run_task("按脚本流程部署节点", lambda: self.remote.deploy_nodes_via_script(self.config), success)

    def log_command_result(self, result: CommandResult) -> None:
        status = "成功" if result.ok else f"退出码 {result.exit_status}"
        self.log(f"命令结果: {status}")
        output = result.output.strip()
        if output:
            self.log(output)

    def config_nodes(self) -> list[Any]:
        ensure_xray_core(self.config)
        nodes = self.config.setdefault("Nodes", [])
        if not isinstance(nodes, list):
            nodes = []
            self.config["Nodes"] = nodes
        return nodes

    def next_node_id(self) -> int:
        highest = 0
        for node in self.config_nodes():
            if not isinstance(node, dict):
                continue
            try:
                highest = max(highest, int(node.get("NodeID", 0) or 0))
            except (TypeError, ValueError):
                continue
        return highest + 1

    def make_blank_node(self) -> dict[str, Any]:
        return make_node(
            api_host="",
            api_key="",
            node_id=self.next_node_id(),
            node_type="vless",
            cert_mode="reality",
            cert_domain="example.com",
            listen_ip="0.0.0.0",
            send_ip="0.0.0.0",
            enable_proxy_protocol=False,
            enable_uot=True,
            enable_tfo=True,
            enable_dns=False,
            dns_type="UseIPv4",
            reject_unknown_sni=False,
            name="",
        )

    def normalize_node_type_cert(self, node: dict[str, Any]) -> None:
        node["Core"] = "xray"
        node_type = str(node.get("NodeType", "vless")).strip().lower()
        if node_type in {"ss", "shadowsocks"}:
            node_type = "shadowsocks"
            cert_mode = "none"
        else:
            node_type = "vless"
            cert_mode = "reality"
        node["NodeType"] = node_type
        node.setdefault("Timeout", 30)
        node.setdefault("ListenIP", "0.0.0.0")
        node.setdefault("SendIP", "0.0.0.0")
        node.setdefault("DeviceOnlineMinTraffic", 200)
        node.setdefault("MinReportTraffic", 0)
        node.setdefault("EnableProxyProtocol", False)
        node.setdefault("EnableUot", True)
        node.setdefault("EnableTFO", True)
        node.setdefault("EnableDNS", False)
        node.setdefault("DNSType", "UseIPv4")
        cert = node.setdefault("CertConfig", {})
        if not isinstance(cert, dict):
            cert = {}
            node["CertConfig"] = cert
        cert["CertMode"] = cert_mode
        cert.setdefault("RejectUnknownSni", False)
        cert.setdefault("CertDomain", "example.com")
        cert.setdefault("CertFile", "/etc/V2bX/fullchain.cer")
        cert.setdefault("KeyFile", "/etc/V2bX/cert.key")
        cert.setdefault("Email", "v2bx@github.com")
        cert.setdefault("Provider", "cloudflare")
        cert.setdefault("DNSEnv", {"EnvName": "env1"})

    def normalize_all_nodes(self) -> None:
        for node in self.config_nodes():
            if isinstance(node, dict):
                self.normalize_node_type_cert(node)
        self.refresh_tree()

    def deployable_node_errors(self, nodes: list[Any]) -> list[str]:
        errors: list[str] = []
        for index, node in enumerate(nodes, start=1):
            if not isinstance(node, dict):
                errors.append(f"第 {index} 行不是节点对象。")
                continue
            api_host = str(node.get("ApiHost", "")).strip()
            api_key = str(node.get("ApiKey", "")).strip()
            node_type = str(node.get("NodeType", "")).strip().lower()
            cert = node.get("CertConfig", {}) if isinstance(node.get("CertConfig"), dict) else {}
            cert_mode = str(cert.get("CertMode", "")).strip().lower()
            if not api_host.startswith(("http://", "https://")):
                errors.append(f"第 {index} 行 ApiHost 必须以 http:// 或 https:// 开头。")
            if not api_key:
                errors.append(f"第 {index} 行 ApiKey 不能为空。")
            try:
                node_id = int(node.get("NodeID"))
                if node_id <= 0:
                    errors.append(f"第 {index} 行 NodeID 必须是正整数。")
            except (TypeError, ValueError):
                errors.append(f"第 {index} 行 NodeID 必须是数字。")
            if node_type not in {"vless", "shadowsocks"}:
                errors.append(f"第 {index} 行 NodeType 只支持 vless 或 shadowsocks。")
            if node_type == "vless" and cert_mode != "reality":
                errors.append(f"第 {index} 行 VLESS 节点必须使用 CertMode=reality。")
            if node_type == "shadowsocks" and cert_mode != "none":
                errors.append(f"第 {index} 行 Shadowsocks 节点必须使用 CertMode=none。")
        return errors

    def add_node(self) -> None:
        nodes = self.config_nodes()
        node = self.make_blank_node()
        nodes.append(node)
        new_index = len(nodes) - 1
        self.refresh_tree()
        self.select_tree_index(new_index)
        self.log(f"已新增节点行: NodeID {node['NodeID']} / vless")

    def copy_selected_node(self) -> None:
        indices = self.selected_indices()
        if not indices:
            messagebox.showwarning("未选择节点", "请先在列表中选择要复制的节点。")
            return
        nodes = self.config_nodes()
        next_id = self.next_node_id()
        new_indices: list[int] = []
        for index in indices:
            source = nodes[index]
            if not isinstance(source, dict):
                continue
            clone = copy.deepcopy(source)
            clone["NodeID"] = next_id
            next_id += 1
            self.normalize_node_type_cert(clone)
            nodes.append(clone)
            new_indices.append(len(nodes) - 1)
        self.refresh_tree()
        self.node_tree.selection_remove(self.node_tree.selection())
        for index in new_indices:
            item_id = str(index)
            if self.node_tree.exists(item_id):
                self.node_tree.selection_add(item_id)
                self.node_tree.see(item_id)
        self.selected_index = new_indices[0] if new_indices else None
        self.log(f"已复制 {len(new_indices)} 个节点；请确认新 NodeID 和面板真实节点一致。")

    def delete_selected_node(self) -> None:
        indices = self.selected_indices()
        if not indices:
            messagebox.showwarning("未选择节点", "请先在列表中选择要删除的节点。")
            return
        if not messagebox.askyesno(
            "确认删除",
            f"只会从本地编辑列表删除 {len(indices)} 个节点，重新部署后才会影响远程配置。\n\n继续吗？",
        ):
            return
        nodes = self.config_nodes()
        for index in sorted(indices, reverse=True):
            del nodes[index]
        self.selected_index = None
        self.refresh_tree()
        self.log(f"已从本地列表删除 {len(indices)} 个节点。")

    def clear_node_list(self) -> None:
        nodes = self.config_nodes()
        if not nodes:
            return
        if not messagebox.askyesno(
            "确认清空",
            "只会清空本地编辑列表，重新部署后才会影响远程配置。\n\n继续吗？",
        ):
            return
        nodes.clear()
        self.selected_index = None
        self.refresh_tree()
        self.log("已清空本地节点列表。")

    def on_node_selected(self, _event: tk.Event[Any]) -> None:
        selected = self.selected_indices()
        self.selected_index = selected[0] if selected else None

    def start_cell_edit(self, event: tk.Event[Any]) -> None:
        if self.node_tree.identify_region(event.x, event.y) != "cell":
            return
        item_id = self.node_tree.identify_row(event.y)
        column_token = self.node_tree.identify_column(event.x)
        if not item_id or not column_token:
            return
        try:
            column_index = int(column_token.replace("#", "")) - 1
        except ValueError:
            return
        if column_index < 0 or column_index >= len(self.table_columns):
            return
        column = self.table_columns[column_index]
        if column not in self.editable_columns:
            return
        bbox = self.node_tree.bbox(item_id, column)
        if not bbox:
            return
        x, y, width, height = bbox
        current_value = self.node_tree.set(item_id, column)
        self.destroy_cell_editor()

        if column == "node_type":
            editor: tk.Widget = ttk.Combobox(self.node_tree, values=("vless", "shadowsocks"), state="readonly")
            editor.set(current_value if current_value in {"vless", "shadowsocks"} else "vless")
        elif column == "cert_mode":
            node = self.node_at_item(item_id)
            node_type = str(node.get("NodeType", "vless")).strip().lower() if isinstance(node, dict) else "vless"
            values = ("none",) if node_type == "shadowsocks" else ("reality",)
            editor = ttk.Combobox(self.node_tree, values=values, state="readonly")
            editor.set(current_value if current_value in values else values[0])
        else:
            editor = ttk.Entry(self.node_tree)
            editor.insert(0, current_value)
            editor.select_range(0, "end")
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()
        self.cell_editor = editor

        def commit(_event: tk.Event[Any] | None = None) -> None:
            if self.cell_editor is not editor:
                return
            value = editor.get() if isinstance(editor, (ttk.Entry, ttk.Combobox)) else ""
            self.commit_cell_edit(item_id, column, value)

        editor.bind("<Return>", commit)
        editor.bind("<Escape>", lambda _event: self.destroy_cell_editor())
        editor.bind("<FocusOut>", commit)
        if isinstance(editor, ttk.Combobox):
            editor.bind("<<ComboboxSelected>>", commit)

    def node_at_item(self, item_id: str) -> dict[str, Any] | None:
        try:
            index = int(item_id)
        except ValueError:
            return None
        nodes = self.config_nodes()
        if index < 0 or index >= len(nodes):
            return None
        node = nodes[index]
        return node if isinstance(node, dict) else None

    def commit_cell_edit(self, item_id: str, column: str, value: str) -> None:
        node = self.node_at_item(item_id)
        if node is None:
            self.destroy_cell_editor()
            return
        value = value.strip()
        if column == "api_host":
            node["ApiHost"] = value
        elif column == "api_key":
            node["ApiKey"] = value
        elif column == "node_id":
            try:
                node_id = int(value)
                if node_id <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("NodeID 错误", "NodeID 必须是正整数。")
                self.destroy_cell_editor()
                self.refresh_tree()
                return
            node["NodeID"] = node_id
        elif column == "node_type":
            node["NodeType"] = "shadowsocks" if value.lower() in {"ss", "shadowsocks"} else "vless"
            self.normalize_node_type_cert(node)
        elif column == "cert_mode":
            cert = node.setdefault("CertConfig", {})
            if isinstance(cert, dict):
                cert["CertMode"] = value
            self.normalize_node_type_cert(node)
        self.destroy_cell_editor()
        self.refresh_tree()
        try:
            self.select_tree_index(int(item_id))
        except ValueError:
            self.select_tree_index(None)

    def destroy_cell_editor(self) -> None:
        if self.cell_editor is None:
            return
        try:
            self.cell_editor.destroy()
        except tk.TclError:
            pass
        self.cell_editor = None


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    base = "#edf8f1"
    panel = "#f7fff9"
    glass = "#f3fff6"
    accent = "#34c759"
    accent_active = "#28ad4f"
    text = "#173b2f"
    muted = "#476657"
    line = "#b7dfc4"
    selection = "#bdf4d0"

    style.configure(".", font=("Segoe UI", 10), background=base, foreground=text)
    style.configure("App.TFrame", background=base)
    style.configure("Panel.TFrame", background=panel)
    style.configure("Glass.TFrame", background=glass)
    style.configure("TFrame", background=base)
    style.configure("TLabel", background=base, foreground=text)
    style.configure("TLabelframe", background=glass, foreground=text, bordercolor=line, relief="solid")
    style.configure("TLabelframe.Label", background=glass, foreground=text, font=("Segoe UI", 10, "bold"))
    style.configure("Glass.TLabelframe", background=glass, bordercolor=line, relief="solid")
    style.configure("TButton", padding=(12, 7), background="#ffffff", foreground=text, bordercolor=line, focusthickness=1)
    style.map("TButton", background=[("active", "#e5f8ea")], foreground=[("disabled", muted)])
    style.configure("Accent.TButton", background=accent, foreground="#ffffff", bordercolor=accent_active)
    style.map("Accent.TButton", background=[("active", accent_active), ("pressed", "#1f8d43")])
    style.configure("TEntry", fieldbackground="#ffffff", foreground=text, bordercolor=line, insertcolor=text)
    style.configure("TCombobox", fieldbackground="#ffffff", foreground=text, bordercolor=line)
    style.configure("Glass.TNotebook", background=base, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 8), background="#dff5e6", foreground=text)
    style.map("TNotebook.Tab", background=[("selected", panel)], foreground=[("selected", text)])
    style.configure(
        "Treeview",
        background="#fbfffc",
        fieldbackground="#fbfffc",
        foreground=text,
        rowheight=30,
        bordercolor=line,
        borderwidth=1,
    )
    style.configure("Treeview.Heading", background="#e2f7e9", foreground=text, font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", selection)], foreground=[("selected", text)])

    app = App(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.ssh.close(), root.destroy()))
    root.mainloop()
