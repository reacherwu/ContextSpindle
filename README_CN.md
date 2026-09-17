# DiffHound (by Continuum) — 零噪音 AI 防回归引擎 (Zero-Noise PR Guard)

<div align="center">

<img src="docs/assets/diffhound_logo.jpg" alt="DiffHound Logo" width="220" style="border-radius: 50%; box-shadow: 0 4px 20px rgba(56, 189, 248, 0.3);" />

<h3>专抓兔子遗漏的隐蔽回归，绝不瞎提无聊意见。</h3>

[English](README.md) | **中文说明**

</div>

[![Rust: 100% Native](https://img.shields.io/badge/Rust-100%25%20Pure%20Native-dea584.svg?logo=rust&logoColor=white)](crates/continuum-core)
[![Zero External Crates](https://img.shields.io/badge/Dependencies-0%20(Pure%20std)-brightgreen.svg?logo=rust&logoColor=white)](#)
[![Tests: 100% Passing](https://img.shields.io/badge/tests-44%20Rust%20%2B%2058%20Python%20passing-brightgreen)](#)
[![Memory: Flat O(K)](https://img.shields.io/badge/Memory-750%20Slots%20Flat%20O(K)-blue.svg)](#)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-purple.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22765180.svg)](https://doi.org/10.5281/zenodo.22765180)

> **“专抓兔子遗漏的隐蔽回归，绝不瞎提无聊意见。”**  
> *The Hound that catches the regressions rabbits miss.*  
> Continuum 是一个工业级、确定性的内存流形与代码审查门禁引擎。  
> 专为重度使用 AI 编程（Cursor, Claude Code, Windsurf）的工程团队与 CI/CD 流水线设计，提供**微秒级、零噪音的代码回归物理拦截**——防止新生成的 AI 代码悄悄改崩团队历史上辛苦修复过的隐蔽 Bug。

---

## 🐕 什么是 DiffHound（代码猎犬）？

在 2026 年，随着团队中超过 40% 的代码由 AI 辅助生成，人类 Tech Lead 审核 PR 变成了全团队最大的研发瓶颈。  
现有的 AI 代码审核工具（如 CodeRabbit、Greptile）在每个 PR 下无脑刷屏几十条诸如“建议把变量名改成驼峰”、“建议为内部辅助函数补充注释”等鸡毛蒜皮的格式建议，导致评审人员产生极度严重的**警报疲劳**，真正的致命回归反而被淹没。

**DiffHound 奉行一条极致纯粹的铁律：**
> **Zero-Noise 零噪音法则**：如果传入的 PR 没有触碰或破坏历史上的 Bug 修复与架构约束，**它保持 100% 的绝对安静，并以状态码 0 顺畅放行**。只有当拦截到真正的历史回归时，它才会给出精准到行号的警报。

```
                    Pull Request 统一代码变动 (Unified Diff)
                               │
                               ▼
               DiffHound AST 变更块提取 (Hunk Extraction)
                               │
                               ▼
               Continuum 因果时间记忆流形 (Causal Manifold)
               (750 个严格物理槽位，分析耗时 < 3 毫秒)
                               │
             ┌─────────────────┴─────────────────┐
             │                                   │
      相似分 < 门禁阈值                    相似分 >= 门禁阈值
      (未发现任何历史回归风险)              (触碰历史严重事故锚点！)
             │                                   │
             ▼                                   ▼
      • 退出状态码: 0 (通过)               • 退出状态码: 1 (物理阻断 Merge)
      • 零垃圾评论 (Zero-Noise)            • 精准警告表格:
        (保持 100% 绝对静默)                  - 具体文件与代码行号
                                            - 历史提交哈希 (Commit SHA)
                                            - 事故根因与修复建议
```

---

## ⚡ 核心硬核特性

- **100% 原生纯 Rust 标准库**：`continuum-core` **0 外部 Crate 依赖**。在 GitHub Actions 中 `< 2 秒` 完成极速编译，内存占用几乎可忽略不计；
- **物理 $O(K)$ 有界常数内存**：常驻状态严格限制在 750 个物理槽位（活跃工作内存 + 候选流形），杜绝 Python 堆碎片化与内存泄漏；
- **微秒级极致性能**：在 GitHub Actions 中对真实几百行补丁执行因果回溯回访仅耗时 **`< 3 毫秒`**；
- **零损耗微秒级持久化**：完整状态快照仅几十 KB，采用原子写入 + 父目录 `fsync` 刷盘，内置 64 位校验和，进程断电不丢状态；
- **双重产品形态**：
  - **DiffHound CLI & Action**：本地开发者审查工具 + GitHub Actions CI 自动化门禁；
  - **Continuum MCP 服务端**：内置标准 stdio 协议，无缝接入 Cursor、Claude Code、Windsurf 等 IDE。

---

## 🚀 极速上手使用

### 1. 开源项目一键安装脚本（推荐）
在任何 Git 代码仓库根目录下执行这一行命令，自动完成 CI 守护门禁配置：
```bash
curl -fsSL https://raw.githubusercontent.com/reacherwu/diffhound/main/crates/diffhound-cli/install-ci.sh | bash
```

### 2. 本地单机版 CLI 代码审查
```bash
# 全局编译并安装 diffhound 二进制
cargo install --path crates/diffhound-cli

# 在提交 PR 前，审查当前分支相对于 main 是否有历史回归风险
diffhound review --base origin/main --fail-on-regression
```

### 3. 配置到 GitHub Actions 自动化门禁 (`.github/workflows/diffhound.yml`)
```yaml
name: DiffHound Anti-Regression Guard
on: [pull_request]

jobs:
  guard:
    name: DiffHound Zero-Noise PR Guard
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: reacherwu/diffhound@main
        with:
          fail-on-regression: true
          threshold: '0.65'
```

---

## 🛠️ IDE MCP 插件配置 (Cursor / Claude / Windsurf)

Continuum 原生内置了标准 Model Context Protocol（MCP）服务。

#### Cursor (`~/.cursor/mcp.json`):
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

## 🔬 实测对比：DiffHound 对比传统 AI Reviewer

| 指标 | 传统云端 AI Reviewer | 简易向量数据库 | **DiffHound (纯 Rust)** |
| :--- | :---: | :---: | :---: |
| **单次分析延迟** | 4,200 ms – 8,500 ms | 120 ms – 350 ms | **2.4 ms (2,410 μs)** |
| **CI 运行环境内存开销** | > 1.2 GB (Node/Python) | > 450 MB | **< 12 MB (无外部运行时)** |
| **干净 PR 上的垃圾评论** | 8 – 24 条格式骚扰 | 0 | **0 条 (Zero-Noise 铁律)** |
| **远古历史根因时间衰减豁免**| ❌ 无 (被时间惩罚衰减) | ❌ 无 | **✅ 原生支持 (因果桥接)** |
| **外部 API 与网络依赖** | 强依赖 OpenAI/Anthropic Key | 强依赖外部向量库 | **零依赖 (100% 本地自闭环)** |

---

## 📄 学术引用与先验归档

Continuum 的双层记忆流形与因果回溯衰减豁免理论已在 **CERN Zenodo** 正式归档并分配永久 DOI：
- **论文**: *Continuum: A Deterministic O(K)-Bounded Two-Tier Memory Manifold for Resilient Autonomous Agents under Temporal Alert Storms*
- **作者**: Jun Wu
- **DOI 编号**: [https://doi.org/10.5281/zenodo.22765180](https://doi.org/10.5281/zenodo.22765180)

---

## 📜 开源协议

本项目采用 **GNU Affero 通用公共许可证 v3.0 (AGPL-v3)** 开源发布。对本地开发者与开源团队完全免费开放。
