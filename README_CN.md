# ContextSpindle

为 AI Agent 提供长期任务连续性与节省 token 的上下文构建。

ContextSpindle 的产品目标是让 Agent 在长对话、多任务穿插、跨会话乃至多年后，仍能迅速找回原任务的目标、完成标准、进度、关键决定与下一步。任务状态需要独立、可靠地持久化；执行时再按任务相关性与 token 预算构建上下文。现有有界 Rust 记忆引擎能做选择性、可重复的检索，但不能充当不丢任务的权威账本。这里的“确定性”仅指固定状态、查询和配置下的检索算法，不代表模型输出一定相同。

CLI 与 MCP 现已提供独立的追加式任务账本及任务感知上下文构建。原有 `remember`/`recall` 是有界检索缓存，不是任务的权威记录。见[产品定义](docs/PRODUCT-SCOPE.md)。

Agent 在工作开始和结束时应遵循[任务连续性协议](docs/AGENT-PROTOCOL.md)。未写入账本的任务，系统无法凭空保存。

## 快速开始

```bash
cargo install --path crates/continuum-cli
contextspindle init .
contextspindle remember "RULE: 不要提交 API 密钥"
contextspindle recall "API 密钥规则" 3
contextspindle stats
```

创建、更新和恢复任务：

```bash
contextspindle task create "发布新版本" --criteria "测试通过并完成发布"
contextspindle task update <任务ID> --status active --next "运行最终测试" --expect-version 1
contextspindle task inbox 10
contextspindle task context <任务ID> 2048
contextspindle task search "新版本" 10
contextspindle task verify
contextspindle task backup /path/to/new-backup-directory
```

任务记录保存在 `.contextspindle/tasks/`，以带校验的追加式版本文件记录更新。该目录被 Git 忽略，推送代码仓库不会备份任务。`task restore <备份目录>` 可以将已校验备份恢复到新工作区，不覆盖内容不同的任务。要保证跨设备、跨年可恢复，需要定期将备份保存到设备之外。上下文预算目前以 UTF-8 字节上限保守代理 token 上限，并非针对某个模型的精确分词计数；必需的任务状态装不下时会报错，可选内容省略数量会显示。

`task list [offset] [limit]` 与 `task history <任务ID> [起始版本] [limit]` 支持分页。收件箱和搜索只返回有限的任务摘要；使用 `task show` 或 `task context` 查看选定任务的完整状态。

可通过 [`.mcp.json`](.mcp.json) 从当前仓库直接启动 MCP；安装 CLI 后也可执行 `contextspindle mcp`。过渡期间，有界记忆状态继续使用 `.continuum/` 以读取旧快照；旧命令 `continuum-cli` 继续可用。

记忆容量有上限，发生淘汰后无法保证每条旧事件仍可找回。研究和基准结果见 [基准文档](docs/BENCHMARKS.md)。改名范围、已检查的重名项目和兼容策略见 [命名决定](docs/NAME-CHANGE.md)。

[English](README.md) · [许可证](LICENSE)
