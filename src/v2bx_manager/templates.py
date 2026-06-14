from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "VLESS Reality (xray)": {
        "NodeType": "vless",
        "CertMode": "reality",
        "CertDomain": "example.com",
        "ListenIP": "0.0.0.0",
        "SendIP": "0.0.0.0",
        "EnableProxyProtocol": False,
        "EnableUot": True,
        "EnableTFO": True,
        "EnableDNS": False,
        "DNSType": "UseIPv4",
        "RejectUnknownSni": False,
        "Note": "VLESS Reality 节点模板，CertMode 使用 reality，具体 Reality 参数通常由面板节点配置控制。",
    },
    "Shadowsocks (xray)": {
        "NodeType": "shadowsocks",
        "CertMode": "none",
        "CertDomain": "example.com",
        "ListenIP": "0.0.0.0",
        "SendIP": "0.0.0.0",
        "EnableProxyProtocol": False,
        "EnableUot": True,
        "EnableTFO": True,
        "EnableDNS": False,
        "DNSType": "UseIPv4",
        "RejectUnknownSni": False,
        "Note": "通用 Shadowsocks 节点模板。",
    },
    "VLESS TLS HTTP Cert (xray)": {
        "NodeType": "vless",
        "CertMode": "http",
        "CertDomain": "example.com",
        "ListenIP": "0.0.0.0",
        "SendIP": "0.0.0.0",
        "EnableProxyProtocol": False,
        "EnableUot": True,
        "EnableTFO": True,
        "EnableDNS": False,
        "DNSType": "UseIPv4",
        "RejectUnknownSni": False,
        "Note": "HTTP ACME 证书模式，需要域名解析到 VPS 且 80 端口可用。",
    },
}


def app_local_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


class TemplateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_local_dir() / "data" / "templates.json"
        self.user_templates: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.user_templates = {}
            self.save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.user_templates = {}
            return
        if isinstance(data, dict):
            self.user_templates = {
                str(name): value
                for name, value in data.items()
                if isinstance(value, dict)
            }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.user_templates, ensure_ascii=False, indent=2), encoding="utf-8")

    def names(self) -> list[str]:
        return list(BUILTIN_TEMPLATES.keys()) + sorted(self.user_templates.keys())

    def get(self, name: str) -> dict[str, Any]:
        if name in BUILTIN_TEMPLATES:
            return dict(BUILTIN_TEMPLATES[name])
        return dict(self.user_templates.get(name, {}))

    def set(self, name: str, template: dict[str, Any]) -> None:
        self.user_templates[name] = dict(template)
        self.save()
