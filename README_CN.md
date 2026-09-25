# ContextSpindle

**给 AI Agent 一条不会被长对话冲掉的任务主线。** 把目标、关键决定和下一步保存在独立任务账本里；换 Agent、切换任务或重启后，只按当前任务组装所需上下文。

[English](README.md) · [产品定义](docs/PRODUCT-SCOPE.md) · [Agent 工作协议](docs/AGENT-PROTOCOL.md) · [运维手册](docs/OPERATIONS.md) · [完整测试条件](docs/TASK-LEDGER-BENCHMARK.md)

## 为什么创建这个项目？

长对话会压缩上下文，Agent 可能临时处理其他任务，几天、几个月后再回来。如果原任务只存在于聊天记录或会淘汰内容的检索缓存中，Agent 即使记得零散细节，也可能忘记「到底要完成什么」。ContextSpindle 把两件事分开：**持久任务账本保存事实主线，有界记忆引擎只提供可选提示**。恢复时先读任务，再装配上下文，而不是重放整段历史。

![任务从 Agent 写入持久账本，再经预算控制的上下文组装交给下一个 Agent；有界检索缓存只提供可选提示。](docs/assets/task-continuity.svg)

任务账本记录稳定 ID、目标、完成标准、状态、负责人、阻塞原因、下一步、父子任务与依赖、决定、证据和版本历史。跨进程写入串行化；预期版本号可发现并发冲突。只有完成标准、依赖和阻塞条件满足时才能标记完成。系统提供校验、备份和恢复；组装上下文时必需状态不会被悄悄裁掉，可选内容的省略数量会明确报告。

## 用户具体得到什么？

- **接力时知道该做什么：** 用任务 ID 就能看到目标、已有决定、阻塞原因和下一步；不依赖上一个模型私有的聊天上下文。
- **减少无关输入：** 只装配当前任务，不把所有任务一股脑送入模型。下面的数据展示一种明确场景的差异，不承诺所有场景都有相同比例的节省。
- **可追溯、可协作：** 保留历史版本、决定和证据；`expected_version` 防止多个 Agent 悄悄覆盖彼此的更新。Agent 名称是调用方声明的记录，不是身份认证。
- **缓存坏了也不丢任务：** `.continuum/` 的有界检索缓存不是事实来源；`.contextspindle/tasks/` 的账本可独立校验、备份和恢复。
- **统一接口：** 本地 CLI 与 15 个 MCP 工具可供不同 Agent 使用。

## 真实运行数据，而不是概念数字

[可复现脚本](benchmarks/task_ledger_product.py)在全新工作区创建了 1 个包含 24 条备注的主任务和 **999 个无关任务**。Apple M4 / macOS 26.6.2 上，发布版 CLI 从新进程组装主任务的 2,048 字节预算上下文，中位耗时 **34.23 ms**、p95 **35.73 ms**（暖文件缓存、连续 11 次）。每个测试预算都保留了目标和下一步。随后故意损坏可选检索快照，任务仍可读取；备份到新工作区并恢复也通过。[原始 JSON 结果](benchmarks/results/task-ledger-2026-09-25.json)列出了精确条件。

![1,000 任务实测中，不同 UTF-8 字节预算对应的实际 cl100k_base token 数与被省略的可选项目数。](docs/assets/measured-context.svg)

| 同一批 1,000 个任务，按 `cl100k_base` 计数 | UTF-8 字节 | 实测 token |
| --- | ---: | ---: |
| 直接拼接 10 页全部任务摘要 | 322,607 | 94,701 |
| 只组装主任务，2,048 字节上限 | 1,908 | 420 |

这个明确的对照里，选定任务的输入 token 数 **少 99.56%**。对照基线刻意采用「把所有任务摘要都送入模型」的朴素方式，两种输入也并非语义完全相同；**这不是对所有用户或模型的节省承诺**。产品实际控制的是保守的 UTF-8 字节上限；这里的 token 数由 `tiktoken` 0.12.0 的 `cl100k_base` 编码测得。任务内容为合成测试数据，但耗时、输出和计数都来自真实执行。

| 该 1,000 任务工作区上的操作 | 中位耗时 | p95 | 次数 |
| --- | ---: | ---: | ---: |
| 收件箱，10 条 | 32.80 ms | 33.92 ms | 11 |
| 搜索主任务 | 32.49 ms | 32.89 ms | 11 |
| 组装主任务上下文，2,048 字节上限 | 34.23 ms | 35.73 ms | 11 |
| 校验全部任务 | 62.73 ms | 63.44 ms | 11 |

这些耗时包含每次启动一个 CLI 进程，但不包含模型回答时间；也没有验证冷盘、Linux、大量单任务历史或多年后的可恢复性。旧有记忆引擎的研究结果见[历史基准](docs/BENCHMARKS.md)，不能当成新任务账本的成绩。

这次仓库更名和发布工作也实际使用了 ContextSpindle 自己的任务账本。版本 3 的接力上下文保留了真实目标与下一步，输出为 1,892 字节 / 438 个 `cl100k_base` token。这是一条[自用观察](docs/TASK-LEDGER-BENCHMARK.md#real-project-dogfood-observation)，不是可独立复现的基准测试：运营中的账本按设计被 Git 忽略。

## 本地开始使用

从当前仓库构建，无需改 IDE 设置、装 Git Hook 或全局安装：

```bash
cargo build --release --bin contextspindle
./target/release/contextspindle init .
./target/release/contextspindle task create \
  "发布新版本" --criteria "测试通过并完成发布" \
  --idempotency-key ship-release
```

复制返回的任务 ID，再更新和恢复：

```bash
./target/release/contextspindle task update TASK_ID \
  --status active --next "运行最终测试" --expect-version 1
./target/release/contextspindle task inbox 10
./target/release/contextspindle task context TASK_ID 2048
./target/release/contextspindle task verify
./target/release/contextspindle task backup /path/to/new-backup-directory
```

不知道旧任务 ID 时用 `task search <查询词>`，查看修改记录用 `task history <id>`，在新工作区用 `task restore <备份目录>` 恢复。**从未写进账本的任务，系统无法凭空保存。** [Agent 协议](docs/AGENT-PROTOCOL.md)说明开始、切换和结束任务的动作；[运维手册](docs/OPERATIONS.md)说明备份与安全边界。

项目内的 [`.mcp.json`](.mcp.json)可启动同一服务。兼容期保留旧的 `continuum-cli` 命令、Python 模块、Rust crate 名称及 `.continuum/` 快照路径；见[更名记录](docs/NAME-CHANGE.md)。

## 必须知道的边界

账本保存在本机且被 Git 忽略：**推送代码不等于备份任务**。需要跨年保存时，必须安排受保护的异地备份并定期演练恢复。校验和能发现意外损坏，不能防止有权限改写文件的人伪造记录。任务文本与检索提示应作为数据处理，不应提升为高优先级指令。部分列表和搜索操作会扫描任务目录，规模目标应在自己的工作负载上测量。检索算法在固定快照和配置下可重复，不代表语言模型每次回答相同。

[GitHub 项目](https://github.com/reacherwu/ContextSpindle) · [许可证](LICENSE)
