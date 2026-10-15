---
name: skill-router
description: 技能预路由入口（preflight router）。当任务涉及构建/测试/评审/调试/规划/流程/文档/运维/CI，或用户输入 "/命令名" 形式（如 /cpp-build、/checkpoint、/prp-plan），或明确要求某技能时，先读 index.md 按关键词匹配，再只加载命中的那一个技能文件执行。不要把索引整体倒进对话。
---

# skill-router

磁盘技能库的唯一常驻入口。语料库在 `~/.claude/skill-library/`（工作流命令 + ECC 领域技能），路由表在同目录 `index.md`。

## 匹配算法（确定性，不调用其他模型）

1. **命令名直配**：用户输入 `/xxx` 或点名某技能 → 在 index.md「名称」列精确/前缀匹配 `xxx`，命中即加载。
2. **关键词匹配**：把用户任务拆成动词+对象（如 "跑 C++ 构建"、"代码评审"、"起 PR"），对「名称」列的 kebab-case 词和「用途」列做子串匹配；同义词对照动词：跑/构建/build→build，测/test→test，评/review→review，修/fix→fix，计划/plan→plan。
3. **唯一命中原则**：只 Read 命中的那个文件并按其执行。最多允许 2 个强相关命中（如 build-fix + cpp-build）；超过 2 个说明匹配太宽，回到第 2 步收窄。
4. **无命中**：不硬套技能，按常规能力处理，并明说"未命中专用技能"。

## 加载与执行语义

- 路径中 `~` 展开为 `C:\Users\<you>`。
- `commands/*.md` = 任务模板：读完直接照做（它是给本轮请求的指令）。
- `ecc/<name>/SKILL.md` = 程序规范：读完按其流程执行；若该技能目录下有 references/ 等附属文件，仅在正文明确要求时再读。
- 加载后不要复述技能全文，直接执行。

## 纪律

- 不要在回复里罗列索引内容或技能清单；只报告"命中了什么技能"。
- 已常驻在技能列表里的（业务专项 6 个、anthropic-skills、dataviz、caveman、claude-mem 系列）直接用 Skill 工具调用，不走本路由。
- 新增技能：放入 `~/.claude/skill-library/commands/`（命令模板）或 `~/.claude/skill-library/ecc/`（领域技能），并重跑索引生成（或手工在 index.md 加一行）。
