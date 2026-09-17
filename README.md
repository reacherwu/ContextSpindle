# Continuum — AI Team Handover & Anti-Regression Guard

[![Rust: 100% Native](https://img.shields.io/badge/Rust-100%25%20Pure%20Native-dea584.svg?logo=rust&logoColor=white)](crates/continuum-core)
[![Zero External Crates](https://img.shields.io/badge/Dependencies-0%20(Pure%20std)-brightgreen.svg?logo=rust&logoColor=white)](#)
[![Tests: 82 Passing](https://img.shields.io/badge/tests-82%20passing-brightgreen)](#)
[![Memory: Flat O(K)](https://img.shields.io/badge/Memory-750%20Slots%20Flat%20O(K)-blue.svg)](#)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22765180.svg)](https://doi.org/10.5281/zenodo.22765180)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-purple.svg)](LICENSE)

> **“让新接手的 AI，少重复团队已经解决过的错误。”**  
> *Prevent new AI sessions and agents from repeating errors your team has already solved.*  
> 专为同时维护多个代码仓库、重度使用 AI 编程（Cursor, Claude Code, Windsurf, Hermes）的开发团队与外包团队设计。

---

## 🎯 核心交付的 3 个确定性结果

| 交付价值 | 传统 AI 编程现状 | 接入 Continuum 团队守护 |
| :--- | :--- | :--- |
| **1. 跨成员/跨 Agent 零成本交接** | 换人接手、换 IDE 或开新会话，AI 瞬间失忆，必须手动复制一堆 Prompt 交代项目潜规则。 | **自动感知项目流形**：项目约束常驻在仓库根目录，换谁接手都无需重复解释。 |
| **2. 故障与避坑有据可查** | 解决过的疑难杂症散落在聊天记录里，AI 靠模糊概率脑补，经常给出似是而非的答案。 | **带验证闭环的因果记录**：自动关联报错症状、成功修复命令（如测试通过）与 Git 版本。 |
| **3. 提醒与物理阻断防返工** | AI 稍不注意就把上周刚修好的边界条件又改坏了，反复踩同一个坑。 | **编码时精准提醒，CI 中测试物理拦截**：关键规则沉淀为回归测试，死守质量红线。 |

---

## 💡 为什么多项目团队与外包团队最需要它？

在频繁切换代码仓库的多项目开发中，**AI 造成的返工消耗的是真金白银的工时与客户交付信任**：

1. **规则混淆**：团队上午修客户 A 的 React 18，下午改客户 B 的 Vue 2 遗留系统。AI 极易把 A 项目的语法和包习惯性代入 B 项目；
2. **隐性暗坑重复踩**：比如“客户的支付网关有严格顺序要求”、“表 X 写入必须加分布式锁”，老员工踩过一次，新员工或新开的会话依然会反复中招；
3. **返工无法计费**：因为重复犯错导致的调试和返工，无法向客户结算工时，直接侵蚀团队的利润。

---

## 🚀 3 步极简接入（0 学习成本）

### 1. 安装 Continuum CLI
```bash
curl -fsSL https://raw.githubusercontent.com/reacherwu/continuum/main/install.sh | bash 2>/dev/null || cargo install --path crates/continuum-cli
```

### 2. 在项目仓库中初始化并挂载 Hook
```bash
# 在代码仓库根目录下执行
continuum-cli init .
continuum-cli hook install .
```
- 创建 `< 75 KB` 的物理有界状态文件 `.continuum/memory.state`；
- 自动安装 Git post-commit hook，后续团队提交代码时自动捕获配置变更与关键提交。

### 3. 配置到团队的常用 IDE (Cursor / Claude / Windsurf)

Continuum 内置了**零依赖的标准 MCP (Model Context Protocol) 服务**。

#### Cursor 接入 (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "continuum": {
      "command": "continuum-cli",
      "args": ["mcp"]
    }
  }
}
```

#### Claude Code / Claude Desktop:
```bash
claude mcp add continuum continuum-cli mcp
```

---

## 🛠️ 日常工作流：无感流转

团队成员**完全不需要改变日常开发习惯**，Continuum 在水面之下默默守护：

```bash
# 1. 记下一条关键项目约束或安全底线
continuum-cli remember "RULE: 客户支付网关回调接口必须验证 HMAC 签名，且超时时间为 3 秒"

# 2. 自动因果结对：用 runner 跑测试，报错自动捕获，修好后自动配对记录
continuum-cli run cargo test
# 或
continuum-cli run pytest

# 3. 任何 Agent 遇到疑似报错或在重构前，微秒级检索相关经验
continuum-cli recall "支付网关超时" 2
# 机器模式支持结构化 JSON 输出
continuum-cli recall "支付网关超时" 2 --json
```

---

## ⚡ 底层硬核技术保障（100% 纯 Native Rust）

Continuum 绝不是玩具式的胶水脚本，而是采用生产级标准构建的高性能系统：

- **100% 纯 Rust 标准库**：`crates/continuum-core` **0 外部 crate 依赖**，单二进制独立运行，内存占用严格封顶在 **~75 KB**，绝无 Python 堆碎片膨胀；
- **OS 内核级 `flock` 并发保护**：使用操作系统原生的文件锁描述符，多 IDE 窗口或并行 Agent 写入时绝不死锁、不丢更新；
- **断电安全与 Checksum**：原子重命名后显式执行**父目录 `fsync`**，快照内置 `CTNMFOOT` 签名与 64 位校验和，杜绝坏文件加载；
- **全套回归测试守卫**：82 项自动化单元测试与端到端回归测试 100% PASS。

---

## 📄 学术背景与规范

Continuum 的双层流形与因果回溯理论体系由团队独立推导并发表存档于 **CERN Zenodo**：
- **Paper**: *Continuum: A Deterministic O(K)-Bounded Two-Tier Memory Manifold for Resilient Autonomous Agents under Temporal Alert Storms*
- **Author**: Jun Wu
- **DOI**: [https://doi.org/10.5281/zenodo.22765180](https://doi.org/10.5281/zenodo.22765180)

---

## 📜 开源协议

本项目采用 **GNU Affero General Public License v3.0 (AGPL-v3)** 开源。个人开发者与团队均可免费在本地使用。
