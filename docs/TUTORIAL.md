# 把 WorkBuddy 调成 Claude Code：配置层改造完全指南

> 适用版本：WorkBuddy AI 5.6.x – 5.7.x（Windows）。全程只改用户配置目录 `~/.workbuddy-ai`，不碰安装文件，每一步可回滚。
>
> **配套开源仓库：<https://github.com/Choysang/workbuddy-to-claude-code>** —— 脚本、图文手册、教程、Claude Code skill 全在里面，issue/PR 都欢迎。

## TL;DR

WorkBuddy 的 Agent 内核与 Claude Code 同构，体验差距全在产品层配置。改造后实测：每次请求 prompt 中位数 **24.8 万 → 5.5 万 token**，用户规则从 0 条变全量注入，压缩阈值从"等于不压"变 800K @ 1M。

上手就一条命令（退出 WorkBuddy 后）：

```bash
python scripts/harness.py setup
```

再做 5 个界面动作（MCP 信任、1M、沉淀开关等，见[图文手册](docs/MANUAL-STEPS.md)），发个验收任务就完成了。本文讲清每一步**为什么**这么做、坑在哪。

## 开篇：为什么这份指南存在

WorkBuddy 的 Agent 内核是 CodeBuddy Code CLI——它与 Claude Code 同构：同名的工具集（Read/Edit/Bash/Grep/Agent……）、同构的 11 种 hook 事件（PreToolUse、PostToolUse、SessionStart……）、同样以 `CODEBUDDY.md` + `rules/` 注入用户指令、同样的子代理与自动压缩机制。想验证的话，随便拿它的一个构建搜 `tengu_goal_set`、`/tmp/claude`、`--dangerously-skip-permissions` 这些指纹即可。

但默认体验和 Claude Code 差得很远。问题不在引擎，在产品层配置：系统提示是"办公助手版"、用户规则一条不加载、上下文涨到 50 万 token 才压缩、大量从未被调用过的工具塞满工具清单。

这份指南做的事：**把引擎里本来就有、但被产品配置压住的 Claude Code 式工作方式全部放出来。** 数据支撑来自 431 条真实 trace 的统计分析（约 6,700 次模型调用，deepseek-v4.1-flash），每条改动都有可验证的预期效果。

全程约定：`~/.workbuddy-ai` 是 WorkBuddy 的配置目录（等价 Claude Code 的 `~/.claude`）。动手前先退出 WorkBuddy——它运行时会把配置写回去，且脚本检测到进程会拒绝执行（托盘退出，不是关窗口）。

## 一、先认清两边的对应关系

| Claude Code | WorkBuddy | 说明 |
|---|---|---|
| `~/.claude/` | `~/.workbuddy-ai/`（`CODEBUDDY_CONFIG_DIR`） | 用户配置根目录 |
| `~/.claude/CLAUDE.md` | `CODEBUDDY.md` + `rules/` | 用户指令注入（注意坑，见 Step 4） |
| `~/.claude/rules/*.md` | `rules/*.md` | 常驻/按文件类型生效的规则 |
| `~/.claude/agents/*.md` | `agents/*.md` | 子代理定义，同一套 Markdown 格式 |
| `~/.claude/skills/` | `skills/` | 技能 |
| hooks + settings.json | `hooks/` + `settings.json` | 事件名一致（PreToolUse、PostToolUse 等） |
| `CLAUDE_CONFIG_DIR` | `CODEBUDDY_CONFIG_DIR` | 环境变量 |
| （无） | `SOUL.md` / `IDENTITY.md` / `USER.md` | 每轮注入的人设与行为准则文件 |

## 二、默认体验差在哪（诊断结论）

改造前，从 431 条 trace 里量出来的四个问题：

1. **系统提示是办公助手版。** code 模式的提示和办公模式几乎一样，32,091 字符里塞着连接器推荐、专家中心、技能市场强推、"说做不到之前必须先搜技能市场"、股票红绿约定——唯独没有编码规范。
2. **用户指令零加载。** 每个会话日志都是 `No memory rules loaded`。你在 Claude Code 里攒下的规则，WorkBuddy 一条都没读。
3. **上下文几乎从不压缩。** 模型默认 1M 窗口，压缩阈值高到 900K。实测每次请求 prompt 中位数 24.8 万 token，最大 87.4 万——上下文全被废话占了。
4. **工具清单臃肿 + 模型偏弱。** widget、图片/视频生成、微信企微回复、团队工具等从未被调用过；75% 的调用走免费的 flash 档模型，推理 token 中位只有 154。

对应地，改造分十步，按收益从高到低排。仓库里的 `harness.py setup` 已把 Step 1–3、5–9 全自动化，下文保留原理与坑点供自查和二次开发。

## 三、改造十步

### Step 1：系统提示精简（收益最大）

写一个脚本，从插件缓存里的 code 模式提示词模板（`~/.workbuddy-ai/plugins/cache/` 下的 `prompt.tpl`，Nunjucks 格式）生成精简版并替换：

- **删**：办公助手能力介绍、Visualizer、自动化、连接器/专家推荐、"先搜技能市场"、"强制沉淀技能"、Office/建站路由、语气段（它要求"多方案只列利弊不给推荐"，和工程决策习惯冲突）。
- **留**：安全规则、各模式（Agent/Plan/Ask）的工具清单、记忆机制、运行时信息。

实测效果：32,091 → 14,620 字符（5.7.x 上 28,082 → 14,898），每次请求 prompt 中位数从 24.8 万降到 5.5 万 token。

**关键实现细节**（踩过坑才懂）：
- 模板每个版本都会换目录，**必须从原始模板生成而不是硬编码文本**，这样换版本后重新生成即可，不写死内容。
- 生成前校验模板标签配对，改完做字节级备份，支持一键回滚。
- 注意 WorkBuddy 的 CODEBUDDY.md 有**两个入口**：工程协议要放 `rules/` 下才注入（见 Step 4），别只写 CODEBUDDY.md。

### Step 2：工具与 MCP 瘦身

不要凭感觉关——**先统计实际调用**（翻 trace 数每个工具的出现次数），0 次调用的关掉。实测 6,700 次调用里的结论：

| 关掉 | 理由 |
|---|---|
| `show_widget` / `widget_guidelines` | 可视化卡片，0 调用 |
| `ImageGen` / `VideoGen` | 0 调用 |
| `WeChatReply` / `WeComReply` | 0 调用 |
| `TeamCreate` / `TeamDelete` | 团队模式，个人用不上 |
| `SkillManage` | 自动长技能的元凶（见 Step 10） |
| `DelegateTool` | 0 调用 |
| MCP：connector-proxy、miora、weixinpay、ardot、netdrive | 0 调用 |

| 留下 | 理由 |
|---|---|
| Read/Write/Edit/MultiEdit/Glob/Grep/Bash/PowerShell/LSP/Skill | 核心工具 |
| Agent、SendMessage、Task* 系列 | 子代理体系 |
| `sheetagent` | 读写 Excel 唯一真用过的 MCP，16 次调用 |
| **自定义 MCP 总开关** | 必须开，否则你自己加的 MCP 一个都起不来 |

### Step 3：规则全套移植

把 `~/.claude/rules/` 整套拷进 `~/.workbuddy-ai/rules/`：common 十二件（working-style、coding-style、testing、security、git-workflow、agents、code-review……）+ 各语言目录。本来就是按文件类型生效，不加日常开销。

**冲突要显式写优先级**，不然模型行为漂移：
- testing 的"TDD、80% 覆盖率" vs "每步 build + 相关测试"：按你的工作习惯定一条为准，在规则里写明覆盖关系。
- performance 里的 Haiku/Sonnet/Opus 模型分工不适用本机模型，删或改写。
- RTK 那种"Claude Code hook 自动改写命令"的规则**不要搬**——对应的 hook 在 WorkBuddy 里不存在，搬过去只会误导模型。

### Step 4：人设文件与 CODEBUDDY.md 的坑

- WorkBuddy 每轮注入 `SOUL.md` + `IDENTITY.md` + `USER.md`。你的核心工作准则（如 Agent Working Guidelines）**原文放进 SOUL.md**。
- 设置里"个性化 → 自定义指令"每轮也注入——和 SOUL.md 重复，**迁完清空一处**。
- **坑 1**：`CODEBUDDY.md` 会被 WorkBuddy 识别但**不注入给模型**。实测有效路径是把正文放 `rules/workbuddy-protocol.md`，CODEBUDDY.md 只留一行指引。
- **坑 2**：WorkBuddy 启动时会从云端恢复"自定义指令"并回写 SOUL.md，把你放的准则删掉。对策：把准则原文再抄一份进 rules/ 常驻规则，双保险。

### Step 5：子代理与技能移植

- `agents/*.md` 直接拷，**模型字段统一改成 inherit**（跟随主模型），48+ 个全搬只花几分钟。同名的 code-reviewer、build-error-resolver 保留 WorkBuddy 适配版。
- 技能同理拷 `skills/`。检查技能里写死的 Claude Code 路径（如 skill-router 里），改成目标机路径。

### Step 6：hooks

WorkBuddy 引擎支持与 Claude Code 同名的 hook 事件。三件值得装：

1. **编辑后语法检查**（PostToolUse）：每次 Edit/Write 后跑语法/格式检查，问题回传给模型自纠。实测一个验收任务里跑 6 次、0 报错，性价比极高。
2. **简洁输出 hook**（SessionStart + UserPromptSubmit）：每轮强制简短。
3. **命令输出压缩**（PreToolUse → Bash）：把命令改写成输出压缩代理。**坑**：会话沙箱的 PATH 里找不到该二进制，改写时用绝对路径。

### Step 7：MCP 接入

把 context7（文档查询）、agentmemory（记忆）、headroom（上下文压缩）写进 `~/.workbuddy-ai/mcp.json`。

**两个坑**：
- 会话沙箱拦 `cmd.exe`，`cmd /c npx ...` 起不来，改成**直接用 node 调 npx**。
- 新 MCP 默认停用：设置里打开「自定义 MCP」总开关，再到「连接器管理」对每个新加的 MCP 各点一次「信任」，否则日志里连启动记录都没有。

### Step 8：记忆、推理、压缩阈值

- 开启引擎自带的**分类型自动记忆**（user/feedback/project/reference，和 Claude Code 同款机制），有禁用开关的话用环境变量压掉。
- 思考强度设 high、始终开启思考（对应 Claude Code 的 `effortLevel: high`）。
- 上下文窗口在模型下拉里选 1M（一次性），settings.json 里设 `autoCompactWindow` 约 888889——1M 窗口下约 800K 触发压缩。对比默认的"900K 不压缩"，prompt 占用立降一个量级。

### Step 9：语气与插件

- `toneStyle` 清空。默认的 professional 语气段要求"多方案只列利弊不给推荐"，与工程决策习惯冲突。
- 停用 0 使用记录的插件（实测：微信支付、A 股专家团、金融数据、find-skills、document-skills、playwright-cli）。注意**每次产品升级可能把停用插件翻回来**（5.7.6 实测如此），升级后复查。

### Step 10：关掉「本地技能与记忆沉淀」

这个开关默认开着，实际做三件事：每轮插一段 `<memory_and_skills_reminder>` 催模型写日志存技能；开放 `SkillManage` 让模型自己建改技能；注入工作区记忆。后果是**技能自动泛滥**——实测 20 个自动沉淀技能里大多是一次性任务（`gis7-cpp-build-test-verify`、`monthly-report-docx-build`……），还有敏感的 `chrome-localstorage-token-extract`（从 Chrome 本地存储提取 token），这种能力不该让模型随手创建。

关法：设置里关开关 + 界面关 `SkillManage` 工具 + 把已长出来的垃圾技能移走（**移动备份而非直接删**，留恢复余地）。留 `skill-library-manager` 这类你自己接的。仓库的 `harness.py skills-audit` 可列出可疑技能（只报告不删）。

## 四、验收：怎么证明改到位了

**第一层：静态检查。** `python scripts/harness.py verify` 对 `~/.workbuddy-ai/` 全量核对（规则、agents、skills、hooks、settings、mcp.json），全绿才算装好。

**第二层：运行时验收任务。** WorkBuddy 编码模式，空工作目录，发送：

> 写一个 Python 模块 speed.py，函数 parse_speed(value: str) -> float | None：把 "12.5 Mbps"、"800 Kbps"、"#DIV/0!"、"" 转成 Mbps 数值，无效输入返回 None。写 pytest 测试覆盖这四种输入并运行。完成后让 code-reviewer 子代理审查，再汇报。

期望行为：先列任务清单 → 写代码 → 每步跑测试并贴结果 → 派 code-reviewer → 汇报改动文件、验证命令与结果。

**第三层：trace 取证。** 跑完 `python scripts/harness.py verify --runtime`，确认五件事：
1. 系统提示是精简版（不再有办公助手内容）；
2. rules/ 规则已注入请求；
3. 编辑后检查 hook 有运行日志；
4. 子代理真的被派了；
5. prompt 中位数应在 5–6 万 token 量级（改造前 24.8 万）。

实测结果参考：验收任务 11 次模型调用约 98 秒，hook 跑 6 次 0 报错，全流程符合预期；复验 306/306 项全过。

## 五、升级生存指南（必读）

WorkBuddy 自动升级（实测 5.6.2 → 5.7.6）会：

- 生成新的插件缓存目录 → **系统提示补丁和工具清单补丁全部失效**；
- 把 toneStyle 重置回 professional；
- 重新启用你停用过的插件（weixinpay 复活）。

`~/.workbuddy-ai/` 下的 rules、agents、skills、hooks、MCP 配置不受影响。

**升级后的固定动作**（先退出 WorkBuddy，脚本有进程保护）：

```bash
python scripts/harness.py post-update
```

一条命令按序重打全部补丁（系统提示 → 工具清单 → 语气/插件 → MCP/hooks/记忆 → 校验），任何一步失败会点名失败项。等价分步：`patch_code_prompt.py apply` → `patch_tools.py apply` → `tune.py` → `extras.py` → `verify.py`。

新版本模板可能有变化（5.7.6 多了 `<agent_mail>` 段、删了 `<examples>`），从原始模板重新生成的脚本天然适配；硬编码文本的做法每次升级都得手改。升级后界面开关（MCP 信任、1M、技能沉淀）可能被翻回，按[图文手册](docs/MANUAL-STEPS.md)的复查清单过一遍。

## 六、边界：哪些改不了、哪些别碰

**产品写死、改不了的：**
- 系统提示里的合规条款、个人文件安全规则；每轮强制注入 SOUL/IDENTITY/USER。
- `present_files`、团队工具、连接器代理 MCP——只能在提示词里叫模型别用，删不掉。
- 权限模型：Claude Code 是逐项授权 + 白名单；WorkBuddy 是全权限 + 沙箱（cmd.exe 拦截、PowerShell 不回显、删除进回收站）。
- 默认模型档位（flash 档）由套餐决定。

**别碰的：`app.asar`。** exe 里写死了 app.asar 的 SHA256 完整性校验，改一个字节就启动失败；改 exe 里的哈希则数字签名失效，SmartScreen 和杀软开始拦截。用户配置目录留了足够的改造空间，不值得动安装文件。

**一个安全提醒。** 全权限 + bypass 模式下，智能体可以经 Bash 里的 Python 直接写文件，绕过 Edit/Write 的规则限制——`~/.claude/CLAUDE.md` 这类每个会话自动注入的"常驻系统提示"被静默改写是真实发生过的风险场景（所幸那次是正常会话所为，但机制上拦不住恶意诱导）。对策：常驻指令文件定期 diff 备份，全局规则变更只经人工确认。

## 七、工具包结构

```
workbuddy-to-claude-code/
├── README.md            # 快速开始 + 命令速查
├── HARNESS-EVAL.md      # 评估报告（trace 数据与结论）
├── NOTICE.md            # 开源脱敏记录
├── payload/             # 装进 ~/.workbuddy-ai 的内容
│   ├── rules/  agents/  hooks/  skills/
├── docs/
│   ├── TUTORIAL.md      # 本文
│   ├── MANUAL-STEPS.md  # 手动步骤图文手册（MCP 信任、1M、沉淀开关…）
│   └── images/          # 界面示意图
├── skill/workbuddy-harness/  # Claude Code skill
├── scripts/
│   ├── harness.py               # 统一入口：setup / post-update / verify / status / skills-audit / rollback
│   ├── install.py / rollback.py      # 安装/回滚（字节级还原）
│   ├── patch_code_prompt.py          # 系统提示：diff / apply
│   ├── patch_tools.py                # 工具清单精简
│   ├── tune.py                       # 语气/插件/模型上限
│   ├── extras.py                     # MCP / hooks / 记忆 / 推理
│   └── verify.py [--runtime]         # 静态 300+ 项 + 运行时取证
└── tests/               # 安装/回滚/hook 测试
```

一条龙命令：`python scripts/harness.py setup`（首装）/ `post-update`（升级后）。还封装成了 Claude Code skill（`workbuddy-harness`）：说「WorkBuddy 升级后恢复」就会驱动 post-update → 手动复查 → 验收取证。

核心设计原则三条：**一切可回滚**（改动前备份，回滚字节级还原）、**从原始模板生成而非硬编码**（跨版本存活）、**先退出 WorkBuddy 再改**（进程保护 + 避免被写回）。

## 结语

WorkBuddy 的引擎就是 Claude Code 的同构体，体验差距几乎全部来自产品层配置。十步改造后：prompt 占用从 25 万降到 5.5 万 token，规则/子代理/技能/hooks/MCP 全套对齐 Claude Code 工作流，静态 300+ 项、运行时 306 项验收全绿。改的全是用户配置目录，一步可回滚。剩下的差距（合规注入、沙箱权限模型、工具删不掉）是产品写死的——认清边界，别碰 app.asar。

工具箱在 **<https://github.com/Choysang/workbuddy-to-claude-code>**，一条命令试起。踩到新坑欢迎开 issue，改进欢迎 PR。
