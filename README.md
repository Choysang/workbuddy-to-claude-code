# workbuddy-to-claude-code

把本机 WorkBuddy 收敛为编码智能体：精简生态插件、办公技能、推广入口与工具注入，保留文件读写、终端、搜索、代码代理、浏览器测试及项目上下文。

沿用 v3 的配置 profile；v4 增加兼容能力和独立工程版生成器。本仓库只发布自写配置、补丁逻辑与测试；工程版程序由你本机的原厂安装生成。

## 2026-10-27 实测更新

程序与配置改动已合入 [1c8b6ef](https://github.com/Choysang/workbuddy-to-claude-code/commit/1c8b6ef395cb15de044f91e3b56f2326dc095941)，重启验收记录已合入 [8f10198](https://github.com/Choysang/workbuddy-to-claude-code/commit/8f101982ddd6d9ff6b766c374ead569d5bf07be9)。以下结果来自 **Windows / WorkBuddy AI 5.8.4** 的本机运行。

| 问题 | 已落地的更新 | 实测结果 |
|---|---|---|
| 原厂启动、账号合并重新启用生态插件 | 独立副本在桌面与 CLI 两层执行禁用策略；关闭 47 个插件、23 项内置技能 | 活动插件从 14 个缩到 5 个，技能可见清单从 33 个缩到 8 个；sheet-agent / doc-writer 实际拒绝，library / 发布为应用实际禁用 |
| ToolSearch 又带回生态工具 | 内置 MCP 只暴露 `present_files`，保留用户自定义 MCP | 新进程日志的声明和匹配均仅为 `present_files`；四个生态目标查询均未返回同名标识符，搜索仍可能模糊回落到其他工具 |
| 低上下文用量下频繁压缩 | 安装器把 `autoCompactWindow: "auto"` 转为删除运行字段，拒绝非法数值 | 修正后观察 7 分多钟，输入量从 35,241 增长至 166,833 token，64 次预算检查、0 次压缩启动 |
| Write/Edit 检出的语法错误没回到模型 | PostToolUse 改用宿主实际支持的 `additionalContext` 协议 | 故意漏写冒号 → 真实工具结果反馈错误 → Edit 修复 → 四条行为测试通过 |
| 编码任务需要分工与复核 | 保留原角色，增加 explorer、test-author 及兼容命令 | explorer 与 test-author 实际并行；verifier 独立核查；code-reviewer 实际返回具体文件行号及边界问题 |
| 每次启动是否都要重打补丁 | 原厂更新后运行一次生成器，同一版本直接使用工程版快捷方式 | 相同指纹实际校验并复用产物；重启后未再 apply/build，原 sessionId 继续追加，Read 成功返回 `stable_unique` |
| 修改是否有可复核的验证 | 补齐配置、回滚、hook 协议、程序生成和运行证据校验 | 69 项回归通过；重启前后分别 34/34 检查通过；原厂输入指纹未变，工程副本 7/7 个受跟踪文件摘要匹配 |

资源现为 **11 个代理、10 份命令、3 个默认 hooks**；保留 `/plan`，UserPromptSubmit 可选且默认关闭。实际派发验证覆盖上述四个代理，其余角色和命令尚未逐个端到端运行。完整证据与范围见 [v4 验收记录](docs/V4-ACCEPTANCE.md)、[压缩故障对照](docs/COMPACTION-INCIDENT.md)；尚未做同模型、同预算的 Claude Code 性能比较。

## 更新后运行一次

Windows，当前实测 WorkBuddy AI **5.8.4**。需要 Python 和 Node.js 在 PATH 中。先退出原厂及工程版 WorkBuddy，再首次指定原厂目录：

```powershell
python scripts/harness.py build --app-dir "D:/Program Files/WorkBuddyAI"
```

之后更新原厂 WorkBuddy，退出旧实例，再运行：

```powershell
python scripts/harness.py build
# 或
.\update-engineering.ps1
```

也可双击 `update-engineering.cmd`。首次安装在其他位置时先用上面的 `--app-dir`，脚本会记住路径。

脚本读取当前原厂版本与内容指纹，生成独立目录，应用补丁、检查 JavaScript 语法、同步配置，最后更新桌面和开始菜单中的 **WorkBuddy AI 工程版** 快捷方式。相同程序、profile 和生成器再次运行会校验并复用产物。本版本以后直接从工程版快捷方式启动，无需每次重打补丁。

工程副本自身的启动静默更新、后台下载和安装入口关闭；原厂安装保持原有更新能力。更新原厂后重新生成下一版。版本目录和原安装独立，旧版本保留供回退。

新版本必须通过源码锚点、完整性和语法检查。若厂商改变内部结构，脚本会指出需要适配的位置，不承诺未知版本自动兼容。不需要下载或提交厂商程序文件。

可选参数：

```powershell
python scripts/harness.py build --output "D:/WorkBuddy-Engineering/versions"
python scripts/harness.py build --workspace "D:/path/to/project" --launch
python scripts/harness.py build --no-shortcuts
```

`--launch` 前请退出旧 WorkBuddy，避免单实例机制仍展示旧程序。首次运行新程序副本时，系统提示由用户自行处理。

## 工程版修改了什么

| 层面 | 实际改动 |
|---|---|
| 启动 | 保留显式插件禁用和内置技能 off；桌面与 CLI 插件解析均执行 profile 禁用清单，抵御界面/账号状态重新启用 |
| 账号合并 | 用户明确的 false 优先，避免账号启用项重新打开插件 |
| 工具 | 编码工具清单；内置 MCP 只暴露文件展示，停止 ToolSearch 纳入整个生态工具集；保留用户自定义 MCP |
| 技能 | 关闭内置办公、金融、支付、推广、云应用发布与无关多媒体技能；插件技能也遵守 off |
| 界面 | 默认开发模式；导航保留新任务、项目与历史任务；移除办公模式、生态导航、推广和小程序入口 |
| 后台 | 停止工程副本的 Claw 频道启动和推送监听；保留现有用户数据 |
| 提示词 | 工程执行与验证模板，去掉办公路由、市场推荐、连接器推销等长段注入 |
| 更新 | 副本不自行被原厂安装器覆盖；原厂更新后运行一次生成器 |

程序修改限于独立副本。生成器重算 ASAR 条目/分块及 EXE 资源中的 ASAR 摘要，保持完整性校验开启。修改后的副本不再是未经修改的原厂签名文件。

独立工程版把 `profile/plugins.json` 的禁用项作为该版本的本地策略；界面切换不能解除这些禁用。修改清单后重新生成，用户自定义插件状态保留。

**界面隐藏、磁盘缓存存在、运行时注册、实际派发是不同事实。** 旧插件缓存可能还在磁盘；验收以真实加载及工具调用为准。一次探针通过不代表代码质量已经超过 Claude Code，也不证明所有模型或工作负载的性能。

## 保留的配置方案

仅应用配置时：

```powershell
python scripts/harness.py apply --workspace "D:/path/to/project"
python scripts/harness.py status
python scripts/harness.py verify
```

`apply` 保留 v3 的配置层路线，并添加指定工作区的 `.codebuddy/settings.local.json`。项目目录是当前打包 CLI 的 `.codebuddy`，用户目录仍为 `.workbuddy-ai`，工作区覆盖不向父目录继承。

原厂 5.8.4 启动会清除全局禁用项，桌面传入的 CLI 设置又高于工作区设置。因此 **工作区覆盖本身不能保证原厂桌面重启后的生态禁用**。配置路线存在此限制，完整精简使用上面的 `build`。真实对照见 [CODING-ONLY-DECISION.md](docs/CODING-ONLY-DECISION.md)。

| 资源 | 内容 |
|---|---|
| 常驻规则 | 单一 `CODEBUDDY.md`，尊重既有设计与授权，保存交接及验证结果 |
| 代码代理 | 原九个角色，加 explorer、test-author，共 11 个；按委派加载 |
| 命令 | 保留 plan/review/verify/lanes/commit，增加 design/fix/audit/handoff/ship |
| Hook | 默认 SessionStart、PreToolUse、PostToolUse 三个；UserPromptSubmit 可选且默认关闭 |
| 输出风格 | engineer、terse 两个可选资源，不强制切换当前风格 |
| 设置 | acceptEdits、思考、检查点、按需工具加载；保留用户模型与凭据 |

CLI 原生 `/plan` 有优先级；保留原命令文件供兼容，工程规划用 `/design`。

```powershell
python scripts/harness.py apply --prompt-context       # 开启可选提问 hook
python scripts/harness.py apply --no-prompt-context    # 关闭；仍为三个默认 hooks
python scripts/harness.py apply --dry-run              # 预览，不写文件
```

未传开关会沿用上次选择。用户自己的 hooks、项目设置和工具禁用项合并保留。应用前拒绝损坏 JSON 和不支持的工具控制版本，避免半安装。启动偏好与文件关联修复标记保留，防止重复执行产品默认设置；旧安装误删的启动偏好仅从初始备份补回一次，不覆盖现有选择。

## 两个已修复的运行缺陷

**频繁压缩：** profile 的 `autoCompactWindow: "auto"` 是安装指令，安装器将其转换为删除运行配置字段。原厂引擎把字符串代入数值计算会产生 NaN，在低用量下反复压缩；原生 `/autocompact auto` 本来也删除字段。验证接受缺省或正的 JS 安全整数，非法值始终失败。运行对照见 [COMPACTION-INCIDENT.md](docs/COMPACTION-INCIDENT.md)。

**语法错误没有回到模型：** 5.8.4 的 PostToolUse 只记录 exit-2 的 stderr。现改为它支持的 `hookSpecificOutput.additionalContext`，错误随真实 Write/Edit 结果回传；PreToolUse 的不可逆命令检查仍用 exit 2。正常编辑不增加反馈。实测证明模型收到错误后能够 Edit 修复，再运行断言。

## 验证

```powershell
python -m unittest discover tests -q
python scripts/harness.py verify
python scripts/harness.py verify --runtime --pid <真实CLI进程ID>
```

静态校验检查资源、合并设置、hook 真实协议、插件与技能开关。运行时校验读取指定进程的记忆加载日志和 JSON/JSONL trace 的 generation system 输入；用户或工具引用标记不算提示词生效。不传 PID 时选择最近 trace 的进程，结果注明范围。

PASS/WARN/FAIL 三态中 FAIL 影响退出码。设置漂移的 WARN 只提示差异，不证明某能力已关闭。实际验收须检查重启、工具反馈、子代理派发及技能反向调用。本轮结果见 [V4-ACCEPTANCE.md](docs/V4-ACCEPTANCE.md)；[EXPLORATION-CANDIDATES.md](docs/EXPLORATION-CANDIDATES.md) 保留历史探索与用户决定。

## 回滚

配置备份包含原始字节和安装后摘要；默认从最新快照逐次撤销到初始快照，升级新增文件也会撤销。安装后用户修改的文件保留并报告；若保留 settings.json 或其备份缺失，也保留仍被引用的 hook 依赖。缺失备份返回失败，状态保留供重试。

```powershell
python scripts/harness.py rollback --dry-run
python scripts/harness.py rollback
python scripts/harness.py rollback --backup <目录>
```

回到原厂程序时退出工程版，再从原厂入口启动。工程版生成不覆盖原厂快捷方式；工程版旧快捷方式另有备份。不自动删除历史版本和用户任务。

## 仓库地图

- `profile/`：规则、11 个代理、10 个命令、默认与可选 hooks、提示词、插件/技能/工具清单。
- `scripts/engineering.py`：本机程序副本、补丁、ASAR/PE 摘要、版本指纹与快捷方式。
- `scripts/harness.py`：build / apply / status / verify / rollback / doctor 入口。
- `scripts/install.py`、`workspace.py`、`rollback.py`：配置合并、工作区覆盖和回滚。
- `tests/`：行为、协议、回滚、证据范围及程序生成边界。
- `docs/`：运行证据、设计决定与历史记录。

不绕过账号权限或付费能力；不发布程序包、产品密钥或完整运行日志。来源与剔除记录见 [NOTICE.md](NOTICE.md)。

## License

[MIT](LICENSE)
