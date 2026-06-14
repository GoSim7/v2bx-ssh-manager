from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any


SUPPORTED_CORE_TYPES = ["xray", "sing", "hysteria2"]
SUPPORTED_NODE_TYPES = ["shadowsocks", "vless", "vmess", "hysteria", "hysteria2", "trojan", "tuic", "anytls"]
CERT_MODES = ["none", "http", "dns", "self", "reality"]
DNS_TYPES = ["AsIs", "UseIP", "UseIPv4", "UseIPv6"]


DEFAULT_XRAY_CORE: dict[str, Any] = {
    "Type": "xray",
    "Log": {
        "Level": "error",
        "ErrorPath": "/etc/V2bX/error.log",
    },
    "OutboundConfigPath": "/etc/V2bX/custom_outbound.json",
    "RouteConfigPath": "/etc/V2bX/route.json",
}


DEFAULT_CUSTOM_OUTBOUND = """[
  {
    "tag": "IPv4_out",
    "protocol": "freedom",
    "settings": {
      "domainStrategy": "UseIPv4v6"
    }
  },
  {
    "tag": "IPv6_out",
    "protocol": "freedom",
    "settings": {
      "domainStrategy": "UseIPv6"
    }
  },
  {
    "protocol": "blackhole",
    "tag": "block"
  }
]
"""


DEFAULT_DNS = """{
  "servers": [
    "1.1.1.1",
    "8.8.8.8",
    "localhost"
  ],
  "tag": "dns_inbound"
}
"""


DEFAULT_CUSTOM_INBOUND = """[
  {
    "listen": "0.0.0.0",
    "port": 1234,
    "protocol": "socks",
    "settings": {
      "auth": "noauth",
      "accounts": [
        {
          "user": "my-username",
          "pass": "my-password"
        }
      ],
      "udp": false,
      "ip": "127.0.0.1",
      "userLevel": 0
    }
  }
]
"""


DEFAULT_ROUTE = """{
  "domainStrategy": "AsIs",
  "rules": [
    {
      "outboundTag": "block",
      "ip": [
        "geoip:private"
      ]
    },
    {
      "outboundTag": "block",
      "protocol": [
        "bittorrent"
      ]
    },
    {
      "outboundTag": "IPv4_out",
      "network": "udp,tcp"
    }
  ]
}
"""


DEFAULT_SING_ORIGIN = """{
  "dns": {
    "servers": [
      {
        "tag": "cf",
        "address": "1.1.1.1"
      }
    ],
    "strategy": "prefer_ipv4"
  },
  "outbounds": [
    {
      "tag": "direct",
      "type": "direct",
      "domain_resolver": {
        "server": "cf",
        "strategy": "prefer_ipv4"
      }
    },
    {
      "type": "block",
      "tag": "block"
    }
  ],
  "route": {
    "rules": [
      {
        "ip_is_private": true,
        "outbound": "block"
      },
      {
        "outbound": "direct",
        "network": [
          "udp",
          "tcp"
        ]
      }
    ]
  },
  "experimental": {
    "cache_file": {
      "enabled": true
    }
  }
}
"""


DEFAULT_HY2_CONFIG = """quic:
  initStreamReceiveWindow: 8388608
  maxStreamReceiveWindow: 8388608
  initConnReceiveWindow: 20971520
  maxConnReceiveWindow: 20971520
  maxIdleTimeout: 30s
  maxIncomingStreams: 1024
  disablePathMTUDiscovery: false
ignoreClientBandwidth: false
disableUDP: false
udpIdleTimeout: 60s
resolver:
  type: system
acl:
  inline:
    - direct(geosite:google)
    - reject(geosite:cn)
    - reject(geoip:cn)
masquerade:
  type: 404
"""


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def default_config() -> dict[str, Any]:
    return {
        "Log": {
            "Level": "error",
            "Output": "",
        },
        "Cores": [copy.deepcopy(DEFAULT_XRAY_CORE)],
        "Nodes": [],
    }


def parse_config(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("config.json 顶层必须是 JSON object")
    ensure_shape(data)
    return data


def dump_config(config: dict[str, Any]) -> str:
    ensure_shape(config)
    ensure_xray_core(config)
    return json.dumps(config, ensure_ascii=False, indent=4) + "\n"


def ensure_shape(config: dict[str, Any]) -> None:
    if not isinstance(config.get("Log"), dict):
        config["Log"] = {"Level": "error", "Output": ""}
    if not isinstance(config.get("Cores"), list):
        config["Cores"] = []
    if not isinstance(config.get("Nodes"), list):
        config["Nodes"] = []


def ensure_xray_core(config: dict[str, Any]) -> None:
    ensure_shape(config)
    cores = config["Cores"]
    for core in cores:
        if isinstance(core, dict) and core.get("Type") == "xray":
            if "OutboundConfigPath" not in core:
                core["OutboundConfigPath"] = "/etc/V2bX/custom_outbound.json"
            if "RouteConfigPath" not in core:
                core["RouteConfigPath"] = "/etc/V2bX/route.json"
            return
    cores.append(copy.deepcopy(DEFAULT_XRAY_CORE))


def make_node(
    *,
    api_host: str,
    api_key: str,
    node_id: int,
    node_type: str,
    cert_mode: str,
    cert_domain: str,
    listen_ip: str,
    send_ip: str,
    enable_proxy_protocol: bool,
    enable_uot: bool,
    enable_tfo: bool,
    enable_dns: bool,
    dns_type: str,
    reject_unknown_sni: bool,
    name: str = "",
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "Core": "xray",
        "ApiHost": api_host.strip(),
        "ApiKey": api_key.strip(),
        "NodeID": int(node_id),
        "NodeType": node_type.strip(),
        "Timeout": 30,
        "ListenIP": listen_ip.strip() or "0.0.0.0",
        "SendIP": send_ip.strip() or "0.0.0.0",
        "DeviceOnlineMinTraffic": 200,
        "MinReportTraffic": 0,
        "EnableProxyProtocol": bool(enable_proxy_protocol),
        "EnableUot": bool(enable_uot),
        "EnableTFO": bool(enable_tfo),
        "EnableDNS": bool(enable_dns),
        "DNSType": dns_type,
        "CertConfig": {
            "CertMode": cert_mode,
            "RejectUnknownSni": bool(reject_unknown_sni),
            "CertDomain": cert_domain.strip() or "example.com",
            "CertFile": "/etc/V2bX/fullchain.cer",
            "KeyFile": "/etc/V2bX/cert.key",
            "Email": "v2bx@github.com",
            "Provider": "cloudflare",
            "DNSEnv": {
                "EnvName": "env1",
            },
        },
    }
    if name.strip():
        node["Name"] = name.strip()
    return node


def validate_node(node: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    api_host = str(node.get("ApiHost", "")).strip()
    if not api_host.startswith(("http://", "https://")):
        errors.append("ApiHost 必须以 http:// 或 https:// 开头")
    if not str(node.get("ApiKey", "")).strip():
        errors.append("ApiKey 不能为空")
    try:
        node_id = int(node.get("NodeID"))
        if node_id <= 0:
            errors.append("NodeID 必须是正整数")
    except (TypeError, ValueError):
        errors.append("NodeID 必须是数字")
    if node.get("NodeType") not in SUPPORTED_NODE_TYPES:
        errors.append(f"NodeType 目前支持: {', '.join(SUPPORTED_NODE_TYPES)}")
    cert = node.get("CertConfig", {})
    if not isinstance(cert, dict):
        errors.append("CertConfig 必须是对象")
    elif cert.get("CertMode") not in CERT_MODES:
        errors.append(f"CertMode 目前支持: {', '.join(CERT_MODES)}")
    if node.get("DNSType") is not None and node.get("DNSType") not in DNS_TYPES:
        errors.append(f"DNSType 目前支持: {', '.join(DNS_TYPES)}")
    return ValidationResult(ok=not errors, errors=errors)


def validate_config(config: dict[str, Any]) -> ValidationResult:
    ensure_shape(config)
    errors: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    core_types: set[str] = set()
    core_names: set[str] = set()
    for index, core in enumerate(config["Cores"], start=1):
        if not isinstance(core, dict):
            errors.append(f"Cores[{index}] 必须是对象")
            continue
        core_type = str(core.get("Type", ""))
        if not core_type:
            errors.append(f"Cores[{index}] 缺少 Type")
        elif core_type not in SUPPORTED_CORE_TYPES:
            errors.append(f"Cores[{index}] Type 暂不认识: {core_type}")
        else:
            core_types.add(core_type)
        if core.get("Name"):
            core_names.add(str(core["Name"]))
    for index, node in enumerate(config["Nodes"], start=1):
        if not isinstance(node, dict):
            errors.append(f"Nodes[{index}] 必须是对象")
            continue
        node_core = str(node.get("Core", ""))
        if not node_core:
            errors.append(f"Nodes[{index}] 缺少 Core")
        elif node_core not in core_types:
            errors.append(f"Nodes[{index}] Core 未在 Cores[] 中定义: {node_core}")
        core_name = node.get("CoreName")
        if core_name and str(core_name) not in core_names:
            errors.append(f"Nodes[{index}] CoreName 未在 Cores[] 中定义: {core_name}")
        result = validate_node(node)
        errors.extend(f"Nodes[{index}]: {item}" for item in result.errors)
        try:
            duplicate_node_id = int(node.get("NodeID", 0) or 0)
        except (TypeError, ValueError):
            duplicate_node_id = -index
        key = (str(node.get("ApiHost", "")), duplicate_node_id, str(node.get("NodeType", "")))
        if key in seen:
            errors.append(f"Nodes[{index}] 与已有节点重复: {key[1]} / {key[2]} / {key[0]}")
        seen.add(key)
    return ValidationResult(ok=not errors, errors=errors)


def node_summary(index: int, node: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    cert = node.get("CertConfig", {}) if isinstance(node.get("CertConfig"), dict) else {}
    return (
        str(index),
        str(node.get("Core", "")),
        str(node.get("NodeType", "")),
        str(node.get("NodeID", "")),
        str(node.get("ApiHost", "")),
        str(cert.get("CertMode", "")),
    )


def redact_node(node: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(node)
    if clone.get("ApiKey"):
        clone["ApiKey"] = "REDACTED_API_KEY"
    return clone
