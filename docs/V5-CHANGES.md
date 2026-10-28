# v5：真正落地的工具面与 Claude Code 式延迟加载

日期：2026-10-28。原厂版本：WorkBuddy AI 5.8.4。

## v4 遗留缺陷：编码工具清单从未生效

v4 只修补了 `main/server.js` 中的 `buildAgentCliRuntimeArgs`。实际会话由守护进程的预热池（prewarm）启动，参数由 `main/node.js` 的会话启动器拼装，并且原样转发原厂工作模式的工具清单。

本机日志记录了 10-27 至 10-28 全部 9 次预热激活（`[Prewarm] activated pid=… args=[…]`）。其中包括工程版会话 20116、18504、26680、17176。这 9 次的 `--tools` 都是同一份 43 项原厂清单，含 A2A×4、SkillManage、show_widget、widget_guidelines、automation_update，以及延迟加载的 ImageGen、VideoGen 和建站部署工具。

同一启动器还把 weixinpay、sheetagent、space-library 写进 `--mcp-config`。CLI 会照常拉起这些 MCP 子进程，只是把它们的工具隐藏掉。

v4 记录的 token 下降来自插件停用和技能清单收缩，工具这一块并没有发生变化。

## v5 改动

| 层 | 改动 |
|---|---|
| 会话启动器 `main/node.js` | 把 `A.tools` 替换为工程清单，命令行参数和产品配置环境变量同时生效；`A.tools` 未设置时同样注入；只读模式（工具清单里没有 Write，例如 ask）保留自己的清单 |
| 运行时参数 `main/server.js` | 冷启动路径使用相同规则；会话 MCP 在数据源 `applyConfig` 处剔除 `tool-control.json` 中禁用的生态服务器（同一份数据同时生成 `--mcp-config` 和 ACP `session/new` 列表，CLI 优先采用后者），项目级 MCP 按同一名单过滤 |
| 每轮上下文 `main/tar.js` | 删除 `<connector-status>` 块。该块列出生态连接器，还会指示模型调用已禁用的 reconnect_plugin |
| CLI 技能解析 | 插件来源的内置生态技能在程序层强制 off，不再依赖 `settings.skillOverrides`（桌面端会回写这个字段）；用户自建的同名技能不受影响 |
| 工具面 | 按 trace 调用量拆分：19 个常驻工具，22 个延迟加载工具（名字常驻，schema 经 ToolSearch 按需加载） |
| 提示词 | 标记升为 `workbuddy-engineering-v5`；去掉重复的 agent_loop、final_answer、tool_use；增加延迟工具、并行子代理、worktree 隔离、Workflow 扇出和计划模式的用法；结尾段统一为英文 |
| verify | 新增运行时检查：“引擎实际工具清单”读取预热激活时引擎收到的 argv，“生态 MCP 未启动”读取 CLI 的 `[MCP][buildMcpServers] connected servers` 记录；按行内时间戳取每个 PID 的最新记录；日志匹配从仅 `harness__*.log` 改为所有工作区；`claw` 键回写降级为警告，因为工程版已把 Claw 频道启动改为空操作，该键不会生效 |

### 工具面

常驻工具：Agent、AskUserQuestion、Bash、DeferExecuteTool、Edit、Glob、Grep、Read、Skill、TaskCreate、TaskList、TaskOutput、TaskStop、TaskUpdate、ToolSearch、WebFetch、WebSearch、Write、present_files。

延迟加载工具：
- PowerShell、MultiEdit、NotebookEdit、LSP
- TaskGet、SendMessage
- EnterPlanMode、ExitPlanMode
- EnterWorktree、LeaveWorktree
- Monitor、Workflow
- ListAgents、InterruptAgent
- TeamCreate、TeamDelete
- CronCreate、CronList、CronDelete
- ListMcpResources、ReadMcpResource、WaitForMcpServers

依据：
- 历史 trace 的工具调用量：Bash 3477、Edit 1269、Read 650、Write 634、TaskOutput 207、TaskCreate 176、Grep 157、TaskUpdate 133、PowerShell 118、present_files 103、WebSearch 76、WebFetch 75。
- 产品配置中的工具说明体积：Workflow 18.5K 字符、Agent 8.4K、Bash 7.4K、PowerShell 5.9K、SendMessage 5.0K、EnterPlanMode 4.0K、TaskCreate 3.1K、MultiEdit 2.7K。

与 v4 相比：
- 移出：A2A×4、SkillManage、show_widget、widget_guidelines、automation_update，以及原厂延迟加载的生态工具。
- 改为延迟加载：PowerShell、SendMessage、MultiEdit、TaskGet、MCP 资源工具。
- 新增按需能力：计划模式、worktree、Monitor、Workflow、NotebookEdit、Cron、ListAgents、InterruptAgent。

## 验证

| 项 | 结果 |
|---|---|
| 单元与协议回归 | `tests.test_engineering`、`test_install`、`test_hooks`、`test_runtime_evidence` 共 74 项通过。新增测试用 Node 实际执行补丁后的启动器、会话 MCP 数据源、技能解析和连接器块，并覆盖运行时证据的选取规则 |
| 原厂源码锚点 | 在 5.8.4 原厂 `server.js`、`node.js`、`tar.js` 和 CLI 上，每个锚点只命中一次，`node --check` 通过 |
| 模板渲染 | 用 nunjucks 渲染 craft、ask、plan、expert、quick 五种模式，均成功 |
| 独立审查 | 发现 MCP 过滤被 ACP `session/new` 绕过（高危）、`A.tools` 缺省时退回全量工具、同名用户技能被误关、verify 证据选取不稳，均已修复并补测试 |
| 新运行时检查 | 对仍在运行的 v4 工程版（PID 17176）如实报 FAIL：43 项原厂工具，已连接 sheetagent、space-library、weixinpay |

## 真实会话验收（2026-10-28 12:05–12:20）

工程版目录 `5.8.4-7978e6522f4778c6`。生成后静态检查 30/30；`verify --runtime` 36/36。

| 项 | 证据 |
|---|---|
| 引擎实际工具 | PID 22556 冷启动 `[Dispatch] entry opts … argv` 中 `--tools` 与工程清单逐字一致（19 常驻 + 22 延迟）；`SkillManageTool.isEnabled … enabled=false` |
| MCP | 实际连接 `connector-proxy, context7, agentmemory, headroom`；weixinpay、sheetagent、space-library 未出现，对应子进程未启动 |
| 系统提示 | generation system 输入含 `workbuddy-engineering-v5` |
| 延迟工具 | 模型调用 `ToolSearch {"tool_names":["PowerShell"]}`，再通过 `DeferExecuteTool` 执行 PowerShell，退出码 0；后续会话（PID 22952）同样经 DeferExecuteTool 跑 pytest，13 passed，新增的 Gbps 用例被收集并通过 |
| 首轮请求 | PID 22556 首轮 20,340 prompt tokens；v4 工程版首轮 24,318–27,152（PID 25560、18504、20116）、原厂 5.8.4 约 39,556。两者的用户消息不同，只作量级对比 |

尚未覆盖：Workflow、worktree、计划模式、Monitor 的端到端调用；同模型同任务的 A/B 通过率（基准见 `bench/README.md`）。

## 历史数据更正

首版 README 写“prompt 中位数从 24.8 万降到 5.5 万（约 -78%）”，这不是 harness 带来的效果。按会话首轮请求比较（新会话首轮约等于固定开销）：

- 原厂 5.6.2：约 4.5–4.8 万。
- 首版精简（lean-v2）：约 4.8–5.2 万。
- 原厂 5.8.4：约 4.0 万。
- v4 工程版：约 2.4–3.1 万。

78% 来自两组样本的会话长度差异。长会话的上下文主要由对话和工具输出累积而成，常在 10–50 万 token 之间。
