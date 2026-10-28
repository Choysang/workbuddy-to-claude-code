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
| 每轮身份块 `user-context-identity.tpl` | 只保留 SOUL/IDENTITY/USER 正文、语气和用户自定义指令；删除人设扮演说明、BOOTSTRAP 引导和“You are WorkBuddy AI, a powerful AI assistant” |
| 预批准工具 `--allowedTools` | 原厂列表（widget、connect_cloud_service、`Bash(mcporter:*)`、A2A×4）缩为 present_files、WebFetch |
| 每轮上下文 `main/tar.js` | 删除 `<connector-status>` 块。该块列出生态连接器，还会指示模型调用已禁用的 reconnect_plugin |
| CLI 技能解析 | 插件来源的内置生态技能在程序层强制 off，不再依赖 `settings.skillOverrides`（桌面端会回写这个字段）；用户自建的同名技能不受影响 |
| 工具面 | 按 trace 调用量拆分：19 个常驻工具，16 个延迟加载工具（名字常驻，schema 经 ToolSearch 按需加载） |
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
| 引擎实际工具 | PID 22556 冷启动 `[Dispatch] entry opts … argv` 中 `--tools` 与工程清单逐字一致（当时 19 常驻 + 22 延迟）；`SkillManageTool.isEnabled … enabled=false` |
| MCP | 实际连接 `connector-proxy, context7, agentmemory, headroom`；weixinpay、sheetagent、space-library 未出现，对应子进程未启动 |
| 系统提示 | generation system 输入含 `workbuddy-engineering-v5` |
| 延迟工具 | 模型调用 `ToolSearch {"tool_names":["PowerShell"]}`，再通过 `DeferExecuteTool` 执行 PowerShell，退出码 0；后续会话（PID 22952）同样经 DeferExecuteTool 跑 pytest，13 passed，新增的 Gbps 用例被收集并通过 |
| 首轮请求 | PID 22556 首轮 20,340 prompt tokens；v4 工程版首轮 24,318–27,152（PID 25560、18504、20116）、原厂 5.8.4 约 39,556。两者的用户消息不同，只作量级对比 |

### 第二轮验收发现（PID 23672）

模型按名称用 ToolSearch 查找 EnterPlanMode、Workflow、Monitor、EnterWorktree、ExitPlanMode，引擎返回 “No matching tools found”；按关键词搜索只返回 TeamCreate、SendMessage、PowerShell。这几个名字在 5.8.4 引擎的枚举里有，但没有进入工具注册表，`Defer(...)` 只能延迟加载已注册的工具。处理：
- 从延迟清单和提示词中移除 EnterPlanMode、ExitPlanMode、EnterWorktree、LeaveWorktree、Monitor、Workflow，并加测试锁定。
- 计划改为“先给出计划、等用户批准”，或切到 WorkBuddy 的 plan 交互模式（只读模式的工具清单原样保留）。
- 隔离写入交给 `isolation: worktree` 的 worktree-worker 子代理。
- 大规模并行改用 TeamCreate、SendMessage 和共享任务清单。

### 第三轮验收（PID 16364，工程版 `5.8.4-e560fde459a18012`）

`verify --runtime` 36/36。引擎收到 35 项工具，即 19 项常驻加 16 项延迟。

| 项 | 证据 |
|---|---|
| 团队并行 | `ToolSearch` 找到 TeamCreate 和 SendMessage，经 DeferExecuteTool 创建团队 `speed-acceptance`。两个 Agent 同批派出（impl-reviewer、test-reviewer，类型为 code-reviewer）并行审查，汇总后用 SendMessage 发出 `shutdown_request`，再用 TeamDelete 清理团队目录，全程 status ok |
| worktree 隔离 | 隔离 worktree 位于 `D:/workBuddy/harness-selftest-wt-v5`，分支 `v5-gbps-bps`。实现在分支上提交为 `8ea7e1d`（Gbps/bps 解析、拒绝字节单位、溢出保护），之后合回 main，测试通过 |
| 每轮身份块 | 首轮请求不再包含 `product_identity`、`identity_context`、`connector-status`，只剩 `workspace_profile` |
| 预批准工具 | `--allowedTools` 只剩 present_files、WebFetch |
| 首轮请求 | 20,169 prompt tokens |

尚未覆盖：同模型同任务的 A/B 通过率（基准见 `bench/README.md`）。

## 历史数据更正

首版 README 写“prompt 中位数从 24.8 万降到 5.5 万（约 -78%）”，这不是 harness 带来的效果。按会话首轮请求比较（新会话首轮约等于固定开销）：

- 原厂 5.6.2：约 4.5–4.8 万。
- 首版精简（lean-v2）：约 4.8–5.2 万。
- 原厂 5.8.4：约 4.0 万。
- v4 工程版：约 2.4–3.1 万。

78% 来自两组样本的会话长度差异。长会话的上下文主要由对话和工具输出累积而成，常在 10–50 万 token 之间。

## 第二轮结论更正：工具被工作模式清单过滤，不是没有注册

继续查源码后确认，EnterPlanMode、ExitPlanMode、EnterWorktree、LeaveWorktree、Monitor 都有实现类，并以 `Component(oZ.NL)` 注册进工具表（Monitor 默认启用）。会话最终可见的工具是 `--tools` 与工作模式 frontmatter（craft 的 `interaction.md`）清单的交集，原厂 craft 清单里没有这几个，所以 ToolSearch 查不到。之前查得到的 PowerShell、TeamCreate、SendMessage 恰好都在原厂清单里，与这个结论一致。

修复：
- 工程版 ASAR 和插件缓存（`plugins/cache/workbuddy-builtin/interactionmode-craft/*/fragments/interaction.md`）中的 craft 清单都替换成与 `CODE_TOOLS` 逐项一致的工具面，由 `install.apply` 写入，可回滚。
- verify 增加“craft 模式工具清单”静态检查。
- 计划模式、worktree、Monitor 重新加入：ExitPlanMode 常驻（只在计划模式下显示），其余延迟加载。
- Workflow 在 5.8.4 引擎中没有实现类，仍不列入。

### 第四轮验收（PID 29400，工程版 `5.8.4-f1f15fe534fd4146`）

| 工具 | 证据 |
|---|---|
| ToolSearch | 按名称一次找到 EnterPlanMode、EnterWorktree、LeaveWorktree、Monitor 4 个工具（上一版 0 个） |
| EnterPlanMode / ExitPlanMode | 经 DeferExecuteTool 进入计划模式，只读调研后把计划写入 `~/.workbuddy-ai/plans/radiant-thunder-lovelace-x4f9GERW.md`。ExitPlanMode 弹出审批（planBytes=1300），用户批准后权限恢复为 fullAccess |
| EnterWorktree | 执行成功 2 次（326ms、97ms），在 `harness-selftest/.codebuddy/worktrees/feat-tbps-regression` 创建隔离 worktree。实现和回归用例提交为 `46f789f`、`bbaa894`，经 `c769a98` 合回 main |
| Monitor | 128ms 返回后台句柄（`background mode → returning handle immediately`），3 秒后 pytest 输出以 BackgroundTaskNotifier 事件送达，会话不阻塞 |

已知限制：
- 会话工作目录（`D:/zuomian/idea/harness`）不是 git 仓库时，EnterWorktree 需要显式传入目标仓库，模型为此向用户确认了一次。
- 计划模式下读取工作区以外的文件需要审批：原权限模式 fullAccess 没有对应的计划策略，引擎回退到默认审批规则。
- Workflow 在 5.8.4 中没有实现，大规模扇出用 TeamCreate 代替。

## Token 回测：长会话与自动压缩

用户反馈 token 消耗突然变高。用 `python bench/score.py pids --minutes 20000` 回测 10-20 至 10-28 的全部 trace（`first` 是本轮开始时已经带着的上下文，`total` 是本轮所有请求的 prompt token 之和）。

| 样本 | 每轮首个请求 | 单轮合计 | 缓存命中 |
|---|---|---|---|
| 工程版新会话（10-28，6 个） | 20–27K | 0.1–0.8M | 79–98% |
| 原厂新会话（10-26/27） | 28–43K | 0.5–9M | 92–98% |
| 原厂长会话（10-20 至 10-23） | 随会话增长，最高 61 万 | 最高 28M | 97–99.9% |
| 工程版长会话 femto.tar（10-28，PID 17176、21988） | 12–44 万 | 14–24M | 98.7–99.6% |

结论：
- 变高的是 femto.tar 这一个会话。它从 10-20 持续到 10-28，共 1363 次工具调用；每次模型请求都要重发全部上下文，所以单轮消耗随会话长度上升。工程版的固定开销没有变大，新会话首个请求仍是约 20K。
- 根因在引擎的自动压缩。`PreMessage` 策略先做“工程压缩”（`HistoryEngineeringCompactor`）：保留全部用户和助手消息、全部工具调用参数（只省略 `content`/`widget_code`/`new_string` 与工具结果），上一次的压缩内容也原样嵌入。只有估算结果超过上下文预算的 15% 才调用 LLM 摘要；估算按 字符数/4，明显低估中文。
- 证据：日志 `[Compact:PreMessage] Engineering compact done: 1003 items → 67733 estimated tokens`、`Engineering compact sufficient, skipping LLM summary`；压缩后下一轮实际首个请求 120,787 token（PID 17176）。femto.tar 的两次压缩产物分别是 472,300 和 287,705 字符，内含 609 和 345 条历史工具调用。压缩后会话从 12–19 万 token 重新增长。

修复（`engineering.patch_compaction`）：把阈值默认值从 `.15` 改为 `.02`。1M 上下文下，只有不到约 20K 的历史才原样保留，其余都走引擎自带的 LLM 摘要路径（`runLlmSummaryForPreMessage`），与 Claude Code 的做法一致。环境变量 `CODEBUDDY_ENGINEERING_COMPACT_SUFFICIENCY_PCT` 仍可覆盖。实际效果要等重建工程版、长会话触发一次压缩后，看下一轮 `first` 是否降到几万 token。

未改动的口径：压缩触发点。deepseek 的触发比例来自产品配置（`tokenUsageThresholds.compact.modelOverrides.deepseek = 0.5`），`autoCompactWindow` 未设置，所以 1M 窗口约在 50 万 token 时压缩。是否调低需要用户决定。
