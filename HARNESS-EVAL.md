# WorkBuddy Harness 评估报告

> 范围：WorkBuddy AI 5.6.2（`D:\Program Files\WorkBuddyAI`），配置目录 `~/.workbuddy-ai`。
> 证据：本机 431 条 trace（2026-09-15 ~ 10-05，约 6,000 次模型调用、6,598 次工具调用）、CLI 日志、安装包内的提示词模板与 CLI 源码。
> 分析脚本与原始统计在 `analysis/`。

## 一句话结论

引擎不差，配置拖后腿。WorkBuddy 的执行引擎就是 CodeBuddy Code CLI，和 Claude Code 同构（同一套工具、子代理、hooks、CODEBUDDY.md/rules、自动压缩）。编码体验差，来自产品层四个设置：**系统提示是办公助手版、零用户指令、上下文放任到几十万 token、主力用免费 flash 模型**。前三个已修，第四个需要你拍板。

## 引擎能力对照（不是瓶颈）

| 能力 | Claude Code | WorkBuddy 引擎 | 实际是否用上 |
|---|---|---|---|
| Read/Edit/MultiEdit/Write/Glob/Grep/Bash | 有 | 有（同名同语义） | 用了，但 Grep 96 次、Glob 14 次，Bash 3,256 次 |
| 子代理（Explore/Plan/general-purpose/自定义） | 有 | 有 | 431 条 trace 里只调用 28 次 |
| 用户级/项目级指令（CLAUDE.md ↔ CODEBUDDY.md、AGENTS.md、rules） | 有 | 有 | **日志：`[MemoryLoader] No memory rules loaded`** |
| Hooks（PreToolUse/PostToolUse/Stop/…11 种） | 有 | 有 | 未配置 |
| 自动压缩 | 约 80% 窗口 | 有，`autoCompactWindow` 可调 | 阈值 90% × 1M = 900K，等于没开 |
| 任务清单 | TodoWrite | TaskCreate/Update | 用了（172 次） |

## 四个根因

### 1. code 模式的系统提示是办公助手提示

- `welcomemode/code/prompt.tpl` 与 `welcomemode/work/prompt.tpl` 的 diff 只有一段行业插槽，**code 模式没有任何编码专属内容**。
- 实际系统提示 43,680 字符。占比最大的是产品功能：技能体系 6.0K、Visualizer 5.0K、记忆系统 3.7K、插件/连接器推荐 3.5K、自动化 3.2K。
- CLI 自带一份 Claude Code 风格的编码提示（`cli-agent-prompt`：Doing tasks、Executing actions with care、Output efficiency、Code References），在 WorkBuddy 里被整体替换掉了。
- 推荐片段里写着：涉及代码仓库、数据库、云服务时"MUST search Connectors"——编码任务会被拽去推荐插件。

### 2. 零用户指令

- 所有会话日志都是 `No memory rules loaded`：没有 `~/.workbuddy-ai/CODEBUDDY.md`，没有 rules，项目里也没有 CODEBUDDY.md/AGENTS.md。
- 你在 Claude Code 里积累的规则（working-style、opus-briefing 六条纪律、本机坑表）在 WorkBuddy 里完全不存在。
- 身份文件反而在注入噪音：`SOUL.md` 只有标题（空）；`USER.md` 把 2026-09-18 的一次性专项（Qwen3.6 输出压缩问题 + 三条硬约束）注入到每一个会话。

### 3. 上下文放任膨胀

| 模型 | 调用数 | prompt p50 | p90 | max | >200K 占比 |
|---|---|---|---|---|---|
| deepseek-v4.1-flash | 4,288 | 247,803 | 518,645 | 874,351 | 61% |
| hy4-preview-f | 1,435 | 170,252 | 240,837 | 270,327 | 31% |
| kimi-k3 | 86 | 118,978 | 167,034 | 177,506 | 0% |

- 机制：deepseek-v4.1-flash 被设成 1M 上下文；`shouldCompact` 的触发点 = min(窗口, autoCompactWindow) × 0.9 = 900K。日志里会话跑到 45 万~53 万 token 仍未压缩。
- 子代理几乎不用，所有探索输出都堆在主线程。
- 对 flash 级模型，几十万 token 的上下文会明显稀释注意力：忘约束、重复劳动、改错位置。

### 4. 主力模型

- 71% 的调用是 deepseek-v4.1-flash（加上 -sg 变体 75%，WorkBuddy 内 0 credits）。每次调用的推理 token 中位数 154，28% 为 0。
- 同一个产品里可选更强的编码模型，例如 GPT-6-Sol（产品描述"专为复杂编码和智能体工作流构建"，×1.33 credits）、Kimi-K3（×1.62）、GLM-5.3（×0.79）。**本机没有这些模型的对比数据，属推荐，未实测。**

### 次要发现

- 工具失败率不高：Edit 失败 1.6%（deepseek）~2.5%（hy4），Write 未先 Read 报错 14 次。不是主要矛盾，但已在协议里约束。
- 沙箱限制会反复消耗回合：cmd.exe 被拦、PowerShell 工具 stdout 可能不回显、`Remove-Item` 被改道回收站。这些事实散落在单个技能里，没有全局注入；已写入 CODEBUDDY.md。
- **安全**：`~/.workbuddy-ai/models.json` 里有一个明文 OpenAI key 的自定义模型 `gpt-5.6-sol`，且 `maxInputTokens`/`maxOutputTokens` 都填了 32（单位是 token，不是 K），这个条目选中即不可用。未改动，待你处理。

## 做了什么（全部可回滚）

| 层 | 改动 | 对应根因 |
|---|---|---|
| A | `CODEBUDDY.md`：Claude Code 式工程协议（流程、读改纪律、验证纪律、范围纪律、风险操作、上下文管理、沙箱事实、产品功能降噪、本机坑表） | 1、2 |
| A | `rules/`：Python、JS/TS、C++/Qt、脚本四份按路径生效的规则 | 2 |
| A | `agents/`：code-reviewer、debugger、verifier、build-error-resolver | 3 |
| A | `hooks/post_edit_check.py` + settings 注册：编辑后自动检查 Python/JSON/YAML/TOML/XML/JS/PowerShell/bash/bat，问题直接回传模型 | 1 |
| A | `settings.json`：`autoCompactWindow = 200000`，约 180K 触发压缩 | 3 |
| A | `SOUL.md` 补全；`USER.md` 的一次性专项降级为"仅相关任务适用" | 2 |
| A | 移植 Claude Code 技能：deep-audit、spec-trace、remote-long-job | 2 |
| B | code 模式 `prompt.tpl`（插件缓存副本）：插入 `<software_engineering>`，删除强制连接器/专家推荐，编码场景不强制画图 | 1 |

A 层只用官方扩展点，WorkBuddy 升级不受影响。B 层改的是插件缓存里的模板副本（不碰签名安装目录），WorkBuddy 升级后需重新 `apply`。

安装状态（2026-10-06 11:03）：已安装，`scripts/verify.py` 静态检查 51/51 通过。
- 安装备份：`backups/20261006-110343-279128-install`
- 补丁备份：`backups/20261006-110347-584442-prompt`
- `prompt.tpl` 从 32,091 字符变为 34,257 字符；sha256 由 `77e161d3…` 变为 `052e90b4…`。

## 质量保证

- 测试 39 项，在受管 Python 和系统 Python 上都通过。
  - hook 32 项：每种文件类型的真/假阳性、坏输入、中文路径、运行日志。
  - 安装/回滚集成 7 项，使用临时配置目录和合成模板，不碰真实目录。覆盖：字节级还原、重复安装后整体回退、安装后被改的文件不丢、回滚中途失败先撤 hook 且可续跑。
- code-reviewer 子代理独立审查，提出 12 项问题（2 HIGH、5 MEDIUM、5 LOW），已全部修复并补测试。主要几项：
  - 回滚会丢掉安装后对 SOUL/USER 的修改。
  - 多次安装后回滚不彻底。
  - 回滚失败会残留一个指向已删脚本的 hook，导致之后每次编辑都被阻断。
  - YAML 自定义 tag 误报。
  - ESM `.js` 的语法错误漏报。
- hook 的安全设计：
  - 脚本或解释器缺失时 exit 0，不阻断。
  - 内部异常一律 exit 0。
  - 只有确定的问题才 exit 2 回传给模型。
  - 每次运行在 `~/.workbuddy-ai/hooks/post_edit_check.log` 记一行，作为生效证据。

## 运行时验收（需要你启动 WorkBuddy 跑一次）

静态检查只能证明文件装对了，不能证明 WorkBuddy 实际读取了它们。验收步骤见 README 的"验收任务"，跑完执行 `python scripts/verify.py --runtime`，判据为三条：
1. hook 运行日志里有记录。
2. trace 里的系统提示含 `<software_engineering>`。
3. 请求里含 CODEBUDDY.md 内容（"工程协议"）。

调用次数够多时，还会检查 prompt token 的 p90 是否 ≤ 200K。

## 待你拍板

1. **主力编码模型**：继续用 deepseek-v4.1-flash（免费），还是换成 GPT-6-Sol（×1.33）这类编码向模型？
   - 推荐：编码会话换 GPT-6-Sol。同时在 settings 里设 `"variantModels": {"lite": "deepseek-v4.1-flash"}`，让 Explore 这类轻量子代理继续走免费模型。
   - 依据：flash 推理深度太浅（中位 154 token）。
   - 未实测，建议同一任务两种模型各跑一次，用 `verify.py --runtime` 和 trace 对比。
2. **明文 API key**：`models.json` 里的自定义模型条目有两种处理。
   - 删除这个条目。
   - 或者把 `maxInputTokens`/`maxOutputTokens` 改成真实值：内置同名模型配置的是 1000000 / 128000。
   - 若这台机器或这个目录被同步或共享过，建议轮换该 key。
3. **压缩阈值**：当前 200K 窗口（约 180K 触发）。如果长任务压缩太频繁，可改为 300000。

## 观察到的异常（与本次改动无关，如实记录）

- 2026-10-06 10:30:22，有进程在 40ms 内删除了 `~/.workbuddy-ai/logs` 下几乎所有 `*.log`，包括 `main.log`、`daemon.log` 和 10-03~10-05 的会话日志。这些文件不在回收站；traces、Crash-Log、`*.jsonl` 未受影响。
- 这不是升级脚本删的：
  - 删除发生在我的集成测试结束 1.5 秒之后、审查子代理启动 15 秒之前。
  - 两者都只删各自临时目录下的文件。
  - 升级脚本只会删除 manifest 里列出的文件。
- 删除方是谁未查明，推测是某个日志清理程序。
- 影响：`verify.py --runtime` 不再依赖这些文本日志，改用 hook 运行日志和 traces 作为证据。
