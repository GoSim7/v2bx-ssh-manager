# V2bX SSH Manager

**AI-assisted V2bX Windows desktop deployment tool, powered by GPT-5.5**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-Desktop-0078D4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![V2bX](https://img.shields.io/badge/Based%20on-wyx2685%2FV2bX-22c55e)](https://github.com/wyx2685/V2bX)
[![SSH](https://img.shields.io/badge/SSH-Password%20Login-0f766e)](#)
[![Xray](https://img.shields.io/badge/Core-Xray-f97316)](#)

简体中文 | [V2bX](https://github.com/wyx2685/V2bX) | [V2bX Script](https://github.com/wyx2685/V2bX-script)

快速开始 • 核心功能 • 部署流程 • 节点配置 • 安全说明 • 致谢

---

## 项目简介

> [!IMPORTANT]
> V2bX SSH Manager 是一个面向 Windows 桌面的 V2bX VPS 快捷部署与配置工具。它不替代 V2bX，也不内置代理核心；它通过 SSH 连接单台 VPS，自动调用上游 V2bX 安装脚本和 `V2bX generate` 配置流程，帮助操作者减少手工输入出错。

本项目适合需要频繁管理 V2bX 节点、但又不想反复在 SSH 命令行里一步一步输入配置的场景。当前重点支持：

- `xray` core
- `VLESS Reality`
- `Shadowsocks`
- 单台 Windows 电脑管理单台 VPS
- SSH 密码登录
- 本地模板保存与复用

项目基于 [wyx2685/V2bX](https://github.com/wyx2685/V2bX) 生态设计，并由 GPT-5.5 辅助完成产品逻辑梳理、脚本流程分析和代码实现。

---

## 快速开始

### 1. 克隆项目

```powershell
git clone https://github.com/GoSim7/v2bx-ssh-manager.git
cd v2bx-ssh-manager
```

### 2. 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 3. 运行桌面程序

```powershell
.\run.bat
```

### 4. 构建 Windows exe

```powershell
.\build.bat
```

构建完成后，程序会输出到：

```text
dist\V2bX-SSH-Manager.exe
```

---

## 核心功能

| 功能 | 说明 |
|------|------|
| SSH 密码连接 | 通过 Paramiko 连接 VPS，支持 keepalive 和一次自动重连 |
| 安装/更新 V2bX | 调用上游 `install.sh` 安装或更新 V2bX 程序 |
| 拉取远程配置 | 读取 `/etc/V2bX/config.json` 到本地编辑区 |
| 节点本地编辑 | 新增、更新、删除 `Nodes[]` 中的 xray 节点 |
| 模板复用 | 软件本地保存 VLESS Reality、Shadowsocks 等节点模板 |
| 按脚本部署 | 自动驱动官方 `V2bX generate` 交互流程 |
| Reality 修正 | 部署后自动修正 VLESS Reality 节点的 `CertMode=reality` |
| 部署后校验 | 回读远程配置，对比 `ApiHost + NodeID + NodeType`，防止脚本截断节点 |
| 备份与回滚 | 上传或部署前备份配置，支持回滚最新备份 |
| 日志诊断 | 查看 systemd 状态、V2bX 日志、配置路径和片段文件 |
| 防火墙开放 | 可选执行常见防火墙开放动作 |

---

## 推荐工作流

```text
连接 / 测试 SSH
    ↓
检测安装 或 安装/更新 V2bX
    ↓
拉取配置
    ↓
新增到列表 / 更新选中节点
    ↓
部署节点(按脚本)
    ↓
查看日志 / 配置诊断
```

部署成功时，日志中应出现类似：

```text
部署后校验通过：6 个节点已写入 /etc/V2bX/config.json。
```

如果出现：

```text
Get node info failed
server is not exist
```

通常表示 `ApiHost + ApiKey + NodeID + NodeType` 与面板中的真实节点不匹配。

---

## 支持的节点类型

| Core | NodeType | CertMode | 部署方式 |
|------|----------|----------|----------|
| xray | vless | reality | 官方 `V2bX generate` + Reality 修正 |
| xray | shadowsocks | none | 官方 `V2bX generate` |

> [!NOTE]
> V2bX 的本地 `config.json` 只保存面板连接信息。真实端口、Reality 参数、用户列表等通常由面板 API 返回，因此节点是否可用还取决于面板中的节点配置是否存在、类型是否匹配、API Key 是否有权限。

---

## 配置文件说明

默认操作的远程配置文件：

```text
/etc/V2bX/config.json
```

核心结构：

```json
{
  "Log": {},
  "Cores": [],
  "Nodes": []
}
```

关键原则：

- 一个面板节点对应 `Nodes[]` 中一个对象
- 不要把多个 `NodeID` 合并到同一条节点配置
- 多个面板地址可以共存于同一个 `Nodes[]`
- `ApiKey` 属于敏感信息，不建议截图或公开粘贴

---

## 本地数据

用户模板保存在软件本地：

```text
data\templates.json
```

该目录不会提交到 GitHub，用于避免把个人模板、面板地址或密钥误传到远程仓库。

---

## 安全与合规声明

> [!WARNING]
> 本项目仅用于合法、授权的 VPS 与 V2bX 节点管理场景。请确保你拥有目标服务器、面板、节点和 API Key 的合法使用权限，并遵守所在地法律法规、服务商条款和上游项目许可。

请特别注意：

- 不要公开粘贴真实 `ApiKey`
- 不要把 SSH 密码写入源码
- 公开仓库前确认 `data/`、`build/`、`.venv/`、日志和打包文件没有被提交
- 如果面板返回 `server is not exist`，应优先检查面板里的 `NodeID`、节点类型和 API Key 权限

---

## 开发结构

```text
v2bx-ssh-manager
├── src/v2bx_manager/
│   ├── app.py          # Tkinter GUI
│   ├── remote_ops.py   # V2bX 远程 SSH 操作
│   ├── ssh_client.py   # Paramiko SSH 封装
│   ├── config_model.py # config.json 数据模型与校验
│   ├── templates.py    # 本地模板存储
│   └── main.py         # 程序入口
├── run.bat
├── build.bat
└── requirements.txt
```

---

## 相关项目

| 项目 | 说明 |
|------|------|
| [wyx2685/V2bX](https://github.com/wyx2685/V2bX) | 上游 V2bX 节点服务端 |
| [wyx2685/V2bX-script](https://github.com/wyx2685/V2bX-script) | 上游安装与管理脚本 |
| [XTLS/Xray-core](https://github.com/XTLS/Xray-core) | Xray 核心 |
| [paramiko/paramiko](https://github.com/paramiko/paramiko) | Python SSH 库 |
| [pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller) | Windows exe 打包 |

---

## 致谢

感谢 [wyx2685/V2bX](https://github.com/wyx2685/V2bX) 及其脚本项目提供 V2bX 节点服务端和安装管理流程。本项目是在实际 VPS 节点部署、配置排错和多节点自动化场景中整理出来的桌面辅助工具。

如果这个项目帮你减少了 SSH 手工配置出错，欢迎 Star。
