# v4 工程版验收

日期：2026-10-27。原厂版本：WorkBuddy AI 5.8.4，Windows。以下记录区分配置测试、程序生成、真实工具调用与尚未覆盖的能力。原始日志和任务记录只保存在本机，不随仓库公开。

## 最终产物

- 独立版本目录尾名：`5.8.4-9640fccbaaeccffa`；桌面和开始菜单的“WorkBuddy AI 工程版”均指向该副本。
- 原厂输入组合指纹（ASAR、EXE、CLI 字节串的 SHA256）：`ba6e1187e92d03e8bc63183a22d3b513b8d24c86c6138bdcbb164265d11909d1`。
- 工程版 ASAR SHA256：`73554a3da0f94301b7d4bef2cb5595c04f034d08b6503639934c671bfaebeabb`。
- 工程版 EXE SHA256：`04352b6f0dc9f753d8cd67b75d5933bcccf2409dd5d853364c3ca3ad210a33c6`。
- 原安装保留；ASAR 完整性摘要重算，未关闭 integrity fuses。
- 从原安装成功生成；重复运行 PowerShell 入口实际校验并复用同一版本，没有再次复制程序。以后更新原厂后运行一次生成器。

## 保留与新增

保留 v3 的单一规则文件、原九个代理、原五份命令、三个默认 hook；兼容新增 explorer/test-author 和 design/fix/audit/handoff/ship，共 11 个代理、10 份命令。UserPromptSubmit 默认关闭。原生 `/plan` 优先，工程规划使用 `/design`。

配置与工程副本共同关闭 47 个插件及 23 项内置技能；磁盘缓存和 schema 文字不是实际可用性的证据。启动偏好和产品迁移标记保留，已从初始备份一次性恢复旧安装误删的启动偏好；实测 `autoLaunchDesired=false`、`autoLaunchDefaultApplied=true`。

## 自动检查

| 检查 | 实际结果与范围 |
|---|---|
| `python -m unittest discover tests -q` | 69 项通过，20.808 秒；包含配置合并、非法输入、可选 hook、升级回滚、用户修改保护、程序生成、更新入口、运行证据范围等 |
| 最终副本 JavaScript | 实际修改的桌面、CLI、renderer 源码通过 Node 语法检查 |
| `verify --runtime --pid 26680` | 重启后 34/34，通过；包含 30 项静态检查和 4 项运行证据，无警告；重启前 PID 25560 也为 34/34 |
| 提示词证据 | PID 25560、26680 的 generation **system** 输入均包含 `workbuddy-engineering-v4`；不是用户或工具引用标记 |
| 记忆规则 | 两个 PID 的 MemoryLoader 日志均实际加载 `CODEBUDDY.md` |
| 生成边界 | 缺失/重复源码锚点、损坏摘要、运行中实例均拒绝；测试不使用完整厂商程序夹具 |

程序补丁及配置曾完成独立代码审查并修复发现的问题。最后加入的双层插件策略与一次性启动偏好恢复由本轮回归覆盖；后续独立复审因执行环境额度不足未完成，不将它写成已完成的独立审查。

## 原厂与工程版对照

| 场景 | 会话 / CLI PID | 观察 |
|---|---|---|
| 原厂重启，已有工作区覆盖 | `42156208-e06c-4f6a-84d1-8c9ae3f984ec` / 7564 | 14 个活动插件；sheet-agent 实际可派发，33 个技能可见 |
| 原厂启动后再次 apply | `ae70f25b-c9d1-4edc-8df3-efa0d4d02dd6` / 19416 | 缩到 6 个插件，但 tmeet 仍活动，生态技能仍注入 |
| 最终工程副本 | `c381cfa5-a543-479d-b2d7-eeee292c122b` / 25560，重启后 26680 | 5 个基础/工程插件；内置 MCP 仅 `present_files`；首次任务中 8 个技能可见 |

最终活动插件为 `subscription-gate@workbuddy-builtin`、`agent-browser@codebuddy-plugins-official`、`welcomemode-code@workbuddy-builtin`、`interactionmode-craft@workbuddy-builtin`、`prompt-common@workbuddy-builtin`。保留账号订阅检查、编码模式和浏览器能力。用户自定义 MCP 和用户技能继续保留。

## 真实代码任务与反向探测

代码任务会话 `fa908073-ced7-4a8f-a3c7-4d45aaf8d794` 使用上一轮工程候选 `5.8.4-3639216da968ebec`。最终副本随后加上插件禁用清单的解析时覆盖，核心工具和 hook 协议未变。

1. Write 故意漏掉 Python 函数冒号；真实工具结果追加 `Syntax check failed` 和 `unique.py:4`，随后 Edit 修复。
2. explorer 与 test-author 同批派发，各自拥有明确读写范围；test-author 生成四条标准库 unittest，主代理运行全部通过。
3. verifier 独立读取实现、重跑测试和额外断言，确认保序去重、返回新列表且不修改输入。
4. sheet-agent 和 doc-writer 实际派发均返回 `Task agent ... is not available`。
5. library、发布为应用实际调用返回 skillOverrides 禁用；tmeet-skill 返回未找到。
6. 最终副本会话 `c381cfa5-a543-479d-b2d7-eeee292c122b` 又真实派发 code-reviewer，返回具体文件行号和边界问题；主代理独立复现其关键断言，四条测试仍通过。

四个生态工具查询 `search_plugins`、`workbuddy_cloud_service`、`show_widget`、`automation_update` 均未返回同名标识符。ToolSearch 会模糊回落到其他工具，所以 `Found N` 不算目标可用证据。未执行这些生态工具；最终日志另确认内置 MCP 实际只匹配 `present_files`。

本机证据位置：`runtime-probe/engineering/report.md`、`runtime-probe/final/report.md`、`runtime-probe/policy/report.md`，以及 `<config>/projects/d-zuomian-idea-harness/<session>.jsonl`、对应 PID 的日志和 trace。

## 重启续用

最终副本主进程 PID 21588 于 22:00:53 启动。配置最后一次 apply 为 22:00:25，工程生成状态最后写入 22:00:27，均早于启动；本次启动后没有再次 apply/build。

用户亲自处理系统防火墙提示后，22:16:06 在原会话提交只读任务。CLI PID 26680 于 22:16:21 实际调用 Read，读取 `runtime-probe/final/unique.py`，22:16:24 完成并返回函数名 `stable_unique`。该段 transcript 只有一次 Read 调用，结果为 completed；sessionId 始终为 `c381cfa5-a543-479d-b2d7-eeee292c122b`，当前检查点共 56 条记录。

同一新 PID 的日志显示活动插件仍为上述 5 个；22:15:40、22:16:18、22:16:21 的内置 MCP 记录均为 `declared=[present_files] matched=[present_files] missing=[]`。generation trace `trace_d305a8e5d5f7448abfcba24608e74567.jsonl` 确认工程 system 提示继续生效；重启后的完整校验再次 34/34 通过。

本机结构化收据：`runtime-probe/restart-v4.json`，包含会话检查点摘要、调用、插件、PID 与四项运行证据。原厂输入组合指纹仍与构建记录相同，最终工程副本 7/7 个受跟踪文件摘要匹配。由此证明当前 5.8.4 工程副本在不重新应用补丁的情况下重启并续用原会话。

## 验收边界

- 11 个自定义代理中，explorer、test-author、verifier、code-reviewer 已在上述任务实际调用；其余角色及十份斜杠命令未逐个端到端运行。
- 8 个可见技能是会话注入清单；不等于八个技能全部运行通过。已禁用的技能保持禁用，不以解除后执行作为验收。
- 已修复频繁压缩的配置根因，实测 64 次预算检查、7 分多钟、0 次压缩启动；详见 [COMPACTION-INCIDENT.md](COMPACTION-INCIDENT.md)。未覆盖所有模型的长时间压缩路径。
- 尚未有原厂未来版本的适配结果，也没有同模型、同预算的 Claude Code 对比基准；不由这些探针推导普遍性能优势。
