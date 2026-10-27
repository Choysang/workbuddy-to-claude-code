---
description: 审查当前改动：派 code-reviewer 独立审查未提交的 diff 或指定范围
argument-hint: "可选：指定文件或路径，留空则审查全部未提交改动"
---

<user_input>
$ARGUMENTS
</user_input>

1. 先取 diff：`git status --short` 与 `git diff`（含未跟踪文件的内容）。
2. 派 code-reviewer 子代理独立审查，把 diff 与相关上下文一起给它；不要自己替它下结论。
3. 汇总它报告的问题，按严重度排列，逐条判断是否真实成立；不成立的要说明为什么。
4. 对确认的缺陷直接修，修完重跑相关检查。

不要提交代码，除非用户明确要求。
