from __future__ import annotations

import queue
import threading
from datetime import datetime
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from v2bx_manager import __version__
from v2bx_manager.config_model import (
    default_config,
    ensure_xray_core,
    make_node,
    node_summary,
    parse_config,
    validate_config,
    validate_node,
)
from v2bx_manager.remote_ops import RemoteV2bX
from v2bx_manager.ssh_client import CommandResult, SSHClient, describe_connection_error
from v2bx_manager.templates import TemplateStore


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"V2bX SSH Manager v{__version__}")
        self.root.geometry("1180x760")
        self.root.minsize(1040, 680)

        self.ssh = SSHClient()
        self.remote = RemoteV2bX(self.ssh)
        self.config: dict[str, Any] = default_config()
        self.selected_index: int | None = None
        self.task_queue: queue.Queue[tuple[str, bool, Any]] = queue.Queue()
        self.task_running = False
        self.templates = TemplateStore()

        self._build_vars()
        self._build_ui()
        self.refresh_template_list()
        self.refresh_tree()
        self.log(f"软件版本: v{__version__}")
        self.log(f"模板保存位置: {self.templates.path}")

    def _build_vars(self) -> None:
        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar(value="22")
        self.username_var = tk.StringVar(value="root")
        self.password_var = tk.StringVar()
        self.connection_var = tk.StringVar(value="未连接")

        self.template_var = tk.StringVar()
        self.node_name_var = tk.StringVar()
        self.api_host_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.node_id_var = tk.StringVar()
        self.node_type_var = tk.StringVar(value="vless")
        self.cert_mode_var = tk.StringVar(value="reality")
        self.cert_domain_var = tk.StringVar(value="example.com")
        self.listen_ip_var = tk.StringVar(value="0.0.0.0")
        self.send_ip_var = tk.StringVar(value="0.0.0.0")
        self.dns_type_var = tk.StringVar(value="UseIPv4")

        self.enable_proxy_protocol_var = tk.BooleanVar(value=False)
        self.enable_uot_var = tk.BooleanVar(value=True)
        self.enable_tfo_var = tk.BooleanVar(value=True)
        self.enable_dns_var = tk.BooleanVar(value=False)
        self.reject_unknown_sni_var = tk.BooleanVar(value=False)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=10)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(self.root, padding=(0, 10, 10, 10))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self._build_connection_panel(left)
        self._build_action_panel(left)
        self._build_notebook(right)

    def _build_connection_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="服务器连接", padding=10)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="IP / 域名").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.host_var, width=24).grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="端口").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.port_var, width=24).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="用户").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.username_var, width=24).grid(row=2, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="密码").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.password_var, show="*", width=24).grid(row=3, column=1, sticky="ew", pady=3)

        ttk.Button(frame, text="连接 / 测试", command=self.connect).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 3))
        ttk.Label(frame, textvariable=self.connection_var, foreground="#0f766e").grid(row=5, column=0, columnspan=2, sticky="w", pady=3)

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="远程操作", padding=10)
        frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for index in range(2):
            frame.columnconfigure(index, weight=1)

        actions = [
            ("检测安装", self.detect_install),
            ("安装/更新", self.install_v2bx),
            ("拉取配置", self.pull_config),
            ("部署节点(按脚本)", self.deploy_nodes_via_script),
        ]
        for index, (label, callback) in enumerate(actions):
            row, col = divmod(index, 2)
            ttk.Button(frame, text=label, command=callback).grid(row=row, column=col, sticky="ew", padx=3, pady=3)

        hint = ttk.Label(
            frame,
            text="常规流程：连接 VPS -> 拉取配置 -> 新增或更新节点 -> 部署节点(按脚本)。",
            wraplength=240,
            foreground="#475569",
        )
        hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_notebook(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        parent.rowconfigure(0, weight=1)

        nodes_tab = ttk.Frame(notebook, padding=10)
        logs_tab = ttk.Frame(notebook, padding=10)
        notebook.add(nodes_tab, text="节点配置")
        notebook.add(logs_tab, text="输出日志")

        self._build_nodes_tab(nodes_tab)
        self._build_logs_tab(logs_tab)

    def _build_nodes_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="新建空配置", command=self.new_blank_config).pack(side="left")
        ttk.Button(toolbar, text="粘贴导入 JSON", command=self.import_json_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="清空表单", command=self.clear_form).pack(side="left", padx=(6, 0))

        columns = ("index", "core", "type", "node_id", "api_host", "cert")
        self.node_tree = ttk.Treeview(parent, columns=columns, show="headings", height=16)
        headings = {
            "index": "#",
            "core": "Core",
            "type": "NodeType",
            "node_id": "NodeID",
            "api_host": "ApiHost",
            "cert": "CertMode",
        }
        widths = {
            "index": 44,
            "core": 70,
            "type": 110,
            "node_id": 80,
            "api_host": 320,
            "cert": 100,
        }
        for column in columns:
            self.node_tree.heading(column, text=headings[column])
            self.node_tree.column(column, width=widths[column], anchor="w")
        self.node_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.node_tree.bind("<<TreeviewSelect>>", self.on_node_selected)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.node_tree.yview)
        self.node_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=0, sticky="nse", padx=(0, 10))

        form = ttk.LabelFrame(parent, text="节点表单", padding=10)
        form.grid(row=1, column=1, sticky="ns")
        form.columnconfigure(1, weight=1)
        self._build_node_form(form)

    def _build_node_form(self, form: ttk.LabelFrame) -> None:
        row = 0
        ttk.Label(form, text="模板").grid(row=row, column=0, sticky="w", pady=3)
        self.template_combo = ttk.Combobox(form, textvariable=self.template_var, width=28, state="readonly")
        self.template_combo.grid(row=row, column=1, sticky="ew", pady=3)
        self.template_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_template())
        row += 1

        fields = [
            ("ApiHost", self.api_host_var),
            ("ApiKey", self.api_key_var),
            ("NodeID", self.node_id_var),
        ]
        for label, variable in fields:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            show = "*" if label == "ApiKey" else ""
            ttk.Entry(form, textvariable=variable, width=30, show=show).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        ttk.Label(form, text="NodeType").grid(row=row, column=0, sticky="w", pady=3)
        self.node_type_combo = ttk.Combobox(form, textvariable=self.node_type_var, values=("vless", "shadowsocks"), width=28, state="readonly")
        self.node_type_combo.grid(
            row=row, column=1, sticky="ew", pady=3
        )
        self.node_type_combo.bind("<<ComboboxSelected>>", lambda _event: self.sync_cert_mode_for_node_type())
        row += 1

        ttk.Label(form, text="CertMode").grid(row=row, column=0, sticky="w", pady=3)
        self.cert_mode_combo = ttk.Combobox(form, textvariable=self.cert_mode_var, values=("reality",), width=28, state="readonly")
        self.cert_mode_combo.grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1

        edit_buttons = ttk.Frame(form)
        edit_buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(10, 3))
        edit_buttons.columnconfigure(0, weight=1)
        edit_buttons.columnconfigure(1, weight=1)
        ttk.Button(edit_buttons, text="新增到列表", command=self.add_node).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(edit_buttons, text="更新选中节点", command=self.update_selected_node).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        row += 1
        ttk.Button(form, text="删除选中节点", command=self.delete_selected_node).grid(row=row, column=0, columnspan=2, sticky="ew", pady=3)
        row += 1
        ttk.Button(form, text="保存为模板", command=self.save_current_template).grid(row=row, column=0, columnspan=2, sticky="ew", pady=3)

    def _build_logs_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(parent, height=24, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log("应用已启动。")

    def refresh_template_list(self) -> None:
        names = self.templates.names()
        self.template_combo["values"] = names
        if names and not self.template_var.get():
            self.template_var.set(names[0])
            self.apply_template()

    def refresh_tree(self) -> None:
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
            self.connection_var.set(f"已连接: {username}@{host}:{port}")
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
            "这个按钮只安装/更新 V2bX 程序，不会部署主界面里编辑的节点。\n"
            "节点要生效，请安装后点击“部署节点(按脚本)”。\n\n"
            "继续吗？",
        ):
            return

        def success(result: CommandResult) -> None:
            self.log_command_result(result)
            if result.ok:
                self.log("安装/更新程序已完成；节点配置尚未部署，请点击“部署节点(按脚本)”。")

        self.run_task("安装/更新 V2bX 程序", self.remote.install, success)

    def pull_config(self) -> None:
        if not self.require_connection():
            return

        def success(config: dict[str, Any]) -> None:
            self.config = config
            ensure_xray_core(self.config)
            self.refresh_tree()
            self.clear_form(log_template_note=False)
            self.log(f"已拉取配置，节点数: {len(self.config.get('Nodes', []))}")

        self.run_task("拉取远程配置", self.remote.pull_config, success)

    def apply_remote_config(self) -> None:
        if not self.require_connection():
            return
        ensure_xray_core(self.config)
        validation = validate_config(self.config)
        if not validation.ok:
            messagebox.showerror("配置校验失败", "\n".join(validation.errors))
            return
        if not messagebox.askyesno(
            "确认上传 JSON",
            "将直接备份并覆盖远程 /etc/V2bX/config.json，然后重启 V2bX。\n\n"
            "这是高级模式；常规节点部署建议使用“部署节点(按脚本)”。\n\n"
            "继续吗？",
        ):
            return

        def success(result: tuple[str, CommandResult]) -> None:
            backup_path, restart_result = result
            self.log(f"远程备份: {backup_path}")
            self.log_command_result(restart_result)

        self.run_task("上传 JSON 并重启", lambda: self.remote.apply_config(self.config), success)

    def deploy_nodes_via_script(self) -> None:
        if not self.require_connection():
            return
        if not self.sync_form_node_for_deploy():
            return
        nodes = self.config.get("Nodes", [])
        if not isinstance(nodes, list) or not nodes:
            messagebox.showwarning("没有节点", "请先填写并添加 VLESS Reality 或 Shadowsocks 节点。")
            return
        validation = validate_config(self.config)
        if not validation.ok:
            messagebox.showerror("配置校验失败", "\n".join(validation.errors))
            return
        if not messagebox.askyesno(
            "确认部署节点",
            "这会把主界面的节点写入远程 VPS。\n\n"
            "软件将远程执行 V2bX 官方 generate 流程，按界面节点自动输入问答内容。\n\n"
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

    def rollback_config(self) -> None:
        if not self.require_connection():
            return
        if not messagebox.askyesno("确认回滚", "将恢复远程最新 config.json.bak-* 备份并重启 V2bX。继续吗？"):
            return
        self.run_task("回滚远程配置", self.remote.rollback_latest, self.log_command_result)

    def show_status(self) -> None:
        if not self.require_connection():
            return
        self.run_task("查看服务状态", self.remote.service_status, self.log_command_result)

    def show_logs(self) -> None:
        if not self.require_connection():
            return
        self.run_task("查看最近日志", self.remote.logs, self.log_command_result)

    def open_firewall(self) -> None:
        if not self.require_connection():
            return
        if not messagebox.askyesno("确认开放端口", "此操作会停止 firewalld/ufw 并清空常见 iptables 规则。继续吗？"):
            return
        self.run_task("开放 VPS 端口", self.remote.open_firewall, self.log_command_result)

    def diagnose_paths(self) -> None:
        if not self.require_connection():
            return
        self.run_task("诊断配置路径和片段文件", self.remote.diagnose_paths, self.log_command_result)

    def log_command_result(self, result: CommandResult) -> None:
        status = "成功" if result.ok else f"退出码 {result.exit_status}"
        self.log(f"命令结果: {status}")
        output = result.output.strip()
        if output:
            self.log(output)

    def new_blank_config(self) -> None:
        if messagebox.askyesno("新建配置", "将清空本地编辑区，重新创建一个只有 xray core 的空配置。继续吗？"):
            self.config = default_config()
            self.selected_index = None
            self.refresh_tree()
            self.clear_form()
            self.log("已新建本地空配置。")

    def import_json_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("粘贴导入 config.json")
        dialog.geometry("820x580")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(dialog, text="粘贴完整 V2bX config.json。导入只更新本地编辑区，部署或上传后才会影响远程。").grid(
            row=0,
            column=0,
            sticky="ew",
            padx=10,
            pady=(10, 6),
        )
        text = ScrolledText(dialog, wrap="none")
        text.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)

        try:
            clipboard = self.root.clipboard_get().strip()
            if clipboard.startswith("{") and '"Nodes"' in clipboard:
                text.insert("1.0", clipboard)
        except tk.TclError:
            pass

        buttons = ttk.Frame(dialog)
        buttons.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 10))

        def do_import() -> None:
            raw = text.get("1.0", "end").strip()
            if not raw:
                messagebox.showwarning("内容为空", "请先粘贴 config.json 内容。", parent=dialog)
                return
            try:
                config = parse_config(raw)
                ensure_xray_core(config)
                validation = validate_config(config)
            except Exception as error:  # noqa: BLE001 - show JSON parse errors to the user
                messagebox.showerror("导入失败", str(error), parent=dialog)
                return
            if not validation.ok:
                messagebox.showerror("配置校验失败", "\n".join(validation.errors), parent=dialog)
                return
            self.config = config
            self.selected_index = None
            self.refresh_tree()
            self.clear_form()
            dialog.destroy()
            self.log(f"已导入本地配置，节点数: {len(self.config.get('Nodes', []))}")

        ttk.Button(buttons, text="导入到本地编辑区", command=do_import).pack(side="right")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=(0, 6))

    def apply_template(self, log_note: bool = True) -> None:
        template = self.templates.get(self.template_var.get())
        if not template:
            return
        self.node_type_var.set(str(template.get("NodeType", "vless")))
        self.cert_mode_var.set(str(template.get("CertMode", "none")))
        self.cert_domain_var.set(str(template.get("CertDomain", "example.com")))
        self.listen_ip_var.set(str(template.get("ListenIP", "0.0.0.0")))
        self.send_ip_var.set(str(template.get("SendIP", "0.0.0.0")))
        self.dns_type_var.set(str(template.get("DNSType", "UseIPv4")))
        self.enable_proxy_protocol_var.set(bool(template.get("EnableProxyProtocol", False)))
        self.enable_uot_var.set(bool(template.get("EnableUot", True)))
        self.enable_tfo_var.set(bool(template.get("EnableTFO", True)))
        self.enable_dns_var.set(bool(template.get("EnableDNS", False)))
        self.reject_unknown_sni_var.set(bool(template.get("RejectUnknownSni", False)))
        self.sync_cert_mode_for_node_type()
        note = template.get("Note")
        if note and log_note:
            self.log(f"模板说明: {note}")

    def sync_cert_mode_for_node_type(self) -> None:
        node_type = self.node_type_var.get().strip().lower()
        if node_type == "shadowsocks":
            values = ("none",)
        else:
            values = ("reality",)
            self.node_type_var.set("vless")
        if hasattr(self, "cert_mode_combo"):
            self.cert_mode_combo["values"] = values
        if self.cert_mode_var.get() not in values:
            self.cert_mode_var.set(values[0])

    def on_node_selected(self, _event: tk.Event[Any]) -> None:
        selected = self.node_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        nodes = self.config.get("Nodes", [])
        if not isinstance(nodes, list) or index >= len(nodes):
            return
        node = nodes[index]
        if not isinstance(node, dict):
            return
        self.selected_index = index
        self.populate_form(node)

    def populate_form(self, node: dict[str, Any]) -> None:
        cert = node.get("CertConfig", {}) if isinstance(node.get("CertConfig"), dict) else {}
        self.node_name_var.set(str(node.get("Name", "")))
        self.api_host_var.set(str(node.get("ApiHost", "")))
        self.api_key_var.set(str(node.get("ApiKey", "")))
        self.node_id_var.set(str(node.get("NodeID", "")))
        self.node_type_var.set(str(node.get("NodeType", "vless")))
        self.cert_mode_var.set(str(cert.get("CertMode", "none")))
        self.cert_domain_var.set(str(cert.get("CertDomain", "example.com")))
        self.listen_ip_var.set(str(node.get("ListenIP", "0.0.0.0")))
        self.send_ip_var.set(str(node.get("SendIP", "0.0.0.0")))
        self.dns_type_var.set(str(node.get("DNSType", "UseIPv4")))
        self.enable_proxy_protocol_var.set(bool(node.get("EnableProxyProtocol", False)))
        self.enable_uot_var.set(bool(node.get("EnableUot", True)))
        self.enable_tfo_var.set(bool(node.get("EnableTFO", True)))
        self.enable_dns_var.set(bool(node.get("EnableDNS", False)))
        self.reject_unknown_sni_var.set(bool(cert.get("RejectUnknownSni", False)))
        self.sync_cert_mode_for_node_type()

    def clear_form(self, log_template_note: bool = True) -> None:
        self.select_tree_index(None)
        self.node_name_var.set("")
        self.api_host_var.set("")
        self.api_key_var.set("")
        self.node_id_var.set("")
        self.apply_template(log_template_note)

    def form_has_node_data(self) -> bool:
        return any(
            value.strip()
            for value in (
                self.api_host_var.get(),
                self.api_key_var.get(),
                self.node_id_var.get(),
            )
        )

    def form_to_node(self) -> dict[str, Any] | None:
        self.sync_cert_mode_for_node_type()
        try:
            node_id = int(self.node_id_var.get().strip())
        except ValueError:
            messagebox.showerror("NodeID 错误", "NodeID 必须是数字。")
            return None
        node = make_node(
            api_host=self.api_host_var.get(),
            api_key=self.api_key_var.get(),
            node_id=node_id,
            node_type=self.node_type_var.get(),
            cert_mode=self.cert_mode_var.get(),
            cert_domain=self.cert_domain_var.get(),
            listen_ip=self.listen_ip_var.get(),
            send_ip=self.send_ip_var.get(),
            enable_proxy_protocol=self.enable_proxy_protocol_var.get(),
            enable_uot=self.enable_uot_var.get(),
            enable_tfo=self.enable_tfo_var.get(),
            enable_dns=self.enable_dns_var.get(),
            dns_type=self.dns_type_var.get(),
            reject_unknown_sni=self.reject_unknown_sni_var.get(),
            name=self.node_name_var.get(),
        )
        validation = validate_node(node)
        if not validation.ok:
            messagebox.showerror("节点校验失败", "\n".join(validation.errors))
            return None
        return node

    def config_nodes(self) -> list[Any]:
        ensure_xray_core(self.config)
        nodes = self.config.setdefault("Nodes", [])
        if not isinstance(nodes, list):
            nodes = []
            self.config["Nodes"] = nodes
        return nodes

    def find_matching_node_index(self, node: dict[str, Any]) -> int | None:
        for index, existing in enumerate(self.config_nodes()):
            if (
                isinstance(existing, dict)
                and str(existing.get("ApiHost", "")).strip() == str(node.get("ApiHost", "")).strip()
                and str(existing.get("NodeID", "")).strip() == str(node.get("NodeID", "")).strip()
                and str(existing.get("NodeType", "")).strip() == str(node.get("NodeType", "")).strip()
            ):
                return index
        return None

    def add_node(self) -> None:
        self.add_form_node()

    def add_form_node(self) -> bool:
        node = self.form_to_node()
        if node is None:
            return False
        nodes = self.config_nodes()
        matched_index = self.find_matching_node_index(node)
        if matched_index is not None:
            messagebox.showwarning(
                "节点已存在",
                "列表中已有相同 ApiHost、NodeID、NodeType 的节点。\n\n"
                "为避免覆盖拉取到的配置，本次新增已取消。\n"
                "如果要修改原节点，请选中那一行后点击“更新选中节点”。",
            )
            return False
        nodes.append(node)
        new_index = len(nodes) - 1
        self.refresh_tree()
        self.select_tree_index(new_index)
        self.log(f"已新增节点: NodeID {node['NodeID']} / {node['NodeType']}")
        self.log("节点已保存到本地编辑区；要写入 VPS，请点击“部署节点(按脚本)”。")
        return True

    def update_selected_node(self) -> None:
        self.update_selected_form_node()

    def update_selected_form_node(self) -> bool:
        if self.selected_index is None:
            messagebox.showwarning("未选择节点", "请先在列表中选择要更新的节点。新增节点请点击“新增到列表”。")
            return False
        nodes = self.config_nodes()
        if self.selected_index >= len(nodes):
            messagebox.showwarning("选择失效", "当前选中的节点已经不存在，请重新选择。")
            self.select_tree_index(None)
            return False
        existing = nodes[self.selected_index]
        if isinstance(existing, dict) and existing.get("Core") != "xray":
            messagebox.showwarning(
                "非 xray 节点",
                "当前表单只安全编辑 xray 节点。这个节点会被保留，但请用“粘贴导入 JSON”方式修改 sing/hysteria2 节点。",
            )
            return False
        node = self.form_to_node()
        if node is None:
            return False
        matched_index = self.find_matching_node_index(node)
        if matched_index is not None and matched_index != self.selected_index:
            messagebox.showwarning(
                "目标节点已存在",
                "列表中另一行已经有相同 ApiHost、NodeID、NodeType 的节点。\n\n"
                "为避免误覆盖，更新已取消。",
            )
            return False
        update_index = self.selected_index
        nodes[update_index] = node
        self.refresh_tree()
        self.select_tree_index(update_index)
        self.log(f"已更新选中节点: NodeID {node['NodeID']} / {node['NodeType']}")
        self.log("节点已保存到本地编辑区；要写入 VPS，请点击“部署节点(按脚本)”。")
        return True

    def sync_form_node_for_deploy(self) -> bool:
        if not self.form_has_node_data():
            return True
        if self.selected_index is None:
            return self.add_form_node()
        if messagebox.askyesno(
            "部署前更新选中节点",
            "表单里有节点内容，并且当前选中了一条列表节点。\n\n"
            "是否先用表单内容更新选中节点，再继续部署？\n"
            "选择“否”会保留列表现有内容并继续部署。",
        ):
            return self.update_selected_form_node()
        return True

    def delete_selected_node(self) -> None:
        if self.selected_index is None:
            messagebox.showwarning("未选择节点", "请先在列表中选择要删除的节点。")
            return
        nodes = self.config.get("Nodes", [])
        if not isinstance(nodes, list) or self.selected_index >= len(nodes):
            return
        node = nodes[self.selected_index]
        node_id = node.get("NodeID", "") if isinstance(node, dict) else ""
        if not messagebox.askyesno("确认删除", f"只会从本地编辑区删除 NodeID {node_id}，重新部署后才会影响远程。继续吗？"):
            return
        del nodes[self.selected_index]
        self.selected_index = None
        self.refresh_tree()
        self.clear_form()
        self.log(f"已从本地配置删除节点: NodeID {node_id}")

    def current_template_data(self) -> dict[str, Any]:
        return {
            "NodeType": self.node_type_var.get(),
            "CertMode": self.cert_mode_var.get(),
            "CertDomain": self.cert_domain_var.get(),
            "ListenIP": self.listen_ip_var.get(),
            "SendIP": self.send_ip_var.get(),
            "EnableProxyProtocol": self.enable_proxy_protocol_var.get(),
            "EnableUot": self.enable_uot_var.get(),
            "EnableTFO": self.enable_tfo_var.get(),
            "EnableDNS": self.enable_dns_var.get(),
            "DNSType": self.dns_type_var.get(),
            "RejectUnknownSni": self.reject_unknown_sni_var.get(),
        }

    def save_current_template(self) -> None:
        name = simpledialog.askstring("保存模板", "模板名称：", parent=self.root)
        if not name:
            return
        self.templates.set(name.strip(), self.current_template_data())
        self.refresh_template_list()
        self.template_var.set(name.strip())
        self.log(f"已保存模板: {name.strip()}")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.ssh.close(), root.destroy()))
    root.mainloop()
