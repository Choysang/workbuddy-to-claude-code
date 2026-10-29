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

修复（`engineering.patch_compaction`）：把阈值默认值从 `.15` 改为 `.02`。1M 上下文下，只有不到约 20K 的历史才原样保留，其余都走引擎自带的 LLM 摘要路径（`runLlmSummaryForPreMessage`），与 Claude Code 的做法一致。环境变量 `CODEBUDDY_ENGINEERING_COMPACT_SUFFICIENCY_PCT` 仍可覆盖。实测见下文"压缩实测"：压缩后下一次请求降到 22.3K。

压缩触发点（用户 2026-10-28 拍板：1M 窗口 650K 压缩）。原厂有两条触发路径，日志都对得上：
- 回合之间（PreMessage）：产品开关关闭了按阈值压缩（日志 `thresholdEnabled=false`），只在缓存过期满 1 小时后、超过窗口 50% 时压缩。femto.tar 就是空闲后在 513K、543K、605K 才压缩。
- 回合之内（`shouldCompact`）：窗口的 `inputTokens.emergency` = 90%，即 900K。

`patch_compaction` 把两条路径的默认比例都改成 0.65（1M 窗口 650K；选 300K 窗口时约 195K），并默认打开回合之间的阈值压缩。原厂环境变量 `CODEBUDDY_PRE_MESSAGE_COMPACT`、`CODEBUDDY_PRE_MESSAGE_COMPACT_PCT`、`CODEBUDDY_AUTOCOMPACT_PCT_OVERRIDE` 仍可覆盖。注意：deepseek-v4.1-flash 默认窗口是 300K，界面选了 1M 才按 1M 计算。

## 自动化基准：hy3 工程版（2026-10-28 18:45–20:27）

通过 `bench/queue_runs.py` 用 WorkBuddy 自动化无人值守执行，模型 hy3（免费），每个任务 3 次，trace 标记均为 `workbuddy-engineering-v5`。表中调用次数、token、耗时为中位数。

| 任务 | 通过 | 隐藏测试 | 调用 | 首个请求 | 总 token | 耗时 |
|---|---|---|---|---|---|---|
| t07_bughunt（13 个埋点 bug） | 3/3 | 13/13 | 15 | 21.2K | 546K | 156 s |
| t02_feature | 3/3 | 8/8 | 13 | 21.3K | 360K | 81 s |

参考（单个样本，不作结论）：r902 在修复工作模式提示词之前运行，实际是原厂提示词，t07_bughunt 修好 12/13，调用 21 次，首个请求 27.1K，总 token 937K，耗时 345 s。试点 r903（t01_bugfix，9/10）不计入矩阵。bughunt r3 触发免费额度限流（`automation-rate-limited`），但任务已完成并通过。

## 适配 WorkBuddy 5.9.3 与第二轮基准（2026-10-29）

5.9.3 重命名了压缩后的标识符，并把 `renderConnectorStatusBlock` 移到 `main/authority-snapshot.js`。`engineering.py` 改为正则锚点（`sub_once`，标识符用 `[\w$]+` 匹配），按锚点内容定位 bundle（`_bundle_with`），自更新另外拦截 `installVerifiedUpdate`。工程版 `5.9.3-7a4f5188ae10ee7d`，`verify --runtime` 37/37。

hy3 被限流（`automation-rate-limited`）的 3 次不计入：t02_feature r1（2 次调用即中止）、t07_bughunt r3（1/13）和 r1（13/13 通过，但 token 被截断）。

| 版本 | 模型 | 任务 | 有效通过 | 首个请求 | 总 token（中位） | 耗时（中位） |
|---|---|---|---|---|---|---|
| 5.9.3 工程版 | hy3 | t07_bughunt | 1/1 | 19.4K | 472K | 400 s |
| 5.9.3 工程版 | hy3 | t02_feature | 2/2 | 19.5K | 368K | 110 s |
| 5.9.3 工程版 | deepseek-v4.1-flash | t07_bughunt | 3/3 | 19.6K | 589K | 122 s |
| 5.9.3 工程版 | deepseek-v4.1-flash | t02_feature | 3/3 | 19.6K | 239K | 60 s |

首个请求在 5.9.3 上比 5.8.4 工程版（21.2K）再少约 1.7K。deepseek 6/6 全部通过，无限流，耗时约为 hy3 的一半。10-28 的原厂版 hy3 4 次 bughunt 均被限流，不可比较。

### 原厂版对照（5.9.3，deepseek-v4.1-flash，2026-10-29 15:17–16:34）

切回原厂 `D:\Program Files\WorkBuddyAI`（5.9.3），配置回滚到 `20261027-104340-apply` 与 `20261029-100627-apply` 两份备份，确认 5.9.3 提示词无工程标记后运行同一矩阵，随后重新 `apply`。同模型、同版本，各 3 次，中位数：

| 任务 | 版本 | 通过 | 调用 | 首个请求 | 总 token | 耗时 |
|---|---|---|---|---|---|---|
| t07_bughunt | 原厂 | 3/3 | 27 | 35.2K | 1,472K | 165 s |
| t07_bughunt | 工程 | 3/3 | 17 | 19.6K | 589K | 122 s |
| t02_feature | 原厂 | 3/3 | 11 | 35.3K | 446K | 58 s |
| t02_feature | 工程 | 3/3 | 10 | 19.6K | 239K | 60 s |

质量持平（6/6 对 6/6），工程版首个请求少 44%，总 token：bughunt 少 60%、feature 少 46%；bughunt 调用次数从 27 降到 17，耗时少 26%。

### 压缩实测（2026-10-29 16:39，PID 26244）

用 `CODEBUDDY_AUTOCOMPACT_PCT_OVERRIDE=10`、`CODEBUDDY_PRE_MESSAGE_COMPACT_PCT=10` 启动工程版，跑一次 t07_bughunt（deepseek-v4.1-flash），验证压缩链路本身；默认值 0.65 已在 `codebuddy-lite-wb.mjs` 中静态确认。

- 触发：第 4 次请求后上下文 30.9K，日志 `tokenCount=30935/1000000 (3.1%, threshold=10.0%) ... trigger=emergency_threshold`。比例按模型的 `maxInputTokens`（deepseek 默认 300K）计算，不是日志里显示的 1M 窗口：300K × 10% ≈ 30K。所以默认 0.65 在 deepseek 默认窗口下约 195K 触发，界面选 1M 后才是 650K。
- 摘要：`Summary Agent succeeded: 2830 estimated tokens`，`session.history trimmed in-place: 37 -> 1`。
- 压缩后：下一次请求输入 22.3K（系统提示 19.9K + 摘要），任务继续执行，隐藏测试 13/13 通过。
- 界面"最大模式"会给会话写 `preMessageCompactPct=0`，关闭回合之间的压缩，但不影响回合之内的 0.65 触发。个人账号默认不开最大模式。

副产物：引擎在压缩后不再写这个 trace，基准统计会漏掉压缩之后的调用（这次 trace 只有 5 次调用，日志里有 31 次）。`queue_runs.py collect` 现在会检查最后一个 span 与自动化结束的时间差：正常运行 0.3–0.4 s，这次 194 s；超过 30 s 就输出警告。这次运行在本地结果里单独归为 `compact-test`，不计入矩阵。

### 回滚覆盖用户设置（已修复）

现象：恢复工程版后，首个请求从 19.6K 涨到 20.0K，缓存前缀多出 384 token。原因是对照前用 `rollback --backup 20261027-104340-apply` 回滚，这份旧格式备份的 `settings.json` 没有记录 `installed_sha256`，`restore_backup` 只能整份覆盖。10-27 之后你在设置里改的内容因此丢失：51 项 `skillOverrides`（`off` 和 `user-invocable-only`）、关闭 `agent-browser`、禁用 `connector-proxy`。几个技能重新对模型可见，提示词随之变长。

修复：
- `restore_backup` 新增 `merge` 参数。`settings.json` 被用户改过，或者备份缺少安装哈希时，回滚不再整份覆盖，也不再整份保留，而是调用 `install.unmerge_settings` 合并。
- 合并时只把 harness 拥有的部分恢复到安装前的值：profile 顶层键、`claw`/`pluginConfigs`、`sandbox.extraAllowWrite`、harness hook、`plugins.json` 列出的插件、`builtin-skills-off.json` 列出的技能、`tool-control.json` 列出的 ID。其余保持当前状态。
- 新增测试覆盖两种情况：用户改过设置后回滚，以及旧格式备份回滚。
- 本机设置已从 `20261029-100627-apply` 备份恢复后重新 `apply`。修复前的文件另存为 `.harness/settings-before-repair-20261029.json`。
