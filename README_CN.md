# ContextSpindle

为 AI Agent 提供可持久化、可确定性检索的上下文记忆。

ContextSpindle 将经过选择的架构决定、约束与故障根因保存在本地，让新的 Agent 会话能够找回关键背景。核心是有界的 Rust 记忆引擎，支持持续写入、快照持久化与可重复的检索。这里的“确定性”指固定状态、查询和配置下的检索算法，不代表语言模型生成结果一定相同。

**DiffHound** 是基于该记忆引擎的防回归应用：它检查代码变更是否触碰过去记录的修复与约束。项目主线是 Agent 记忆，PR 审查只是一个使用场景。

## 快速开始

```bash
cargo install --path crates/continuum-cli
contextspindle init .
contextspindle remember "RULE: 不要提交 API 密钥"
contextspindle recall "API 密钥规则" 3
contextspindle stats
```

可通过 [`.mcp.json`](.mcp.json) 接入 MCP，或执行 `contextspindle mcp`。过渡期间，本地状态继续使用 `.continuum/`，以便读取旧快照；旧命令 `continuum-cli` 继续可用。

可选的 DiffHound PR 审查：

```bash
cargo install --path crates/diffhound-cli
diffhound review --base origin/main --fail-on-regression
```

记忆容量有上限，发生淘汰后无法保证每条旧事件仍可找回。研究和基准结果见 [基准文档](docs/BENCHMARKS.md)。改名范围、已检查的重名项目和兼容策略见 [命名决定](docs/NAME-CHANGE.md)。

[English](README.md) · [许可证](LICENSE) · [DiffHound GitHub Action](action.yml)
