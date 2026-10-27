---
description: 把当前改动提交成一个干净的 commit（自动分组、生成信息、跑相关检查）
argument-hint: "[附加说明或范围，可留空]"
allowed-tools: Bash, PowerShell, Read, Grep, Glob
---

# /commit

目标：把工作区改动变成一个**可审查、可回滚**的提交。$ARGUMENTS

## 步骤

1. 并行执行：`git status --short`、`git diff --stat`、`git log --oneline -10`。看清改了什么、仓库提交信息风格是什么。
2. 排除不该提交的内容：`.env`、密钥、证书、构建产物、大二进制、本地配置、`.harness/` 运行日志。命中了先报告，不要擅自加进提交。
3. 按主题分组。一组改动能独立回滚就拆成多个 commit；同一逻辑的代码+测试+文档放同一个 commit。
4. 提交前先跑与改动相关的检查（测试/构建/lint）。失败就停止，不创建提交。通过后逐个提交：`git add <明确路径>`（不用 `git add -A`、不用 `git add .`），然后提交。
5. 提交信息：第一行 ≤ 72 字符，说清"做了什么"而不是"改了哪些文件"；正文写动机与影响面；沿用仓库已有的语言与格式。
6. 报告提交前验证结果。提交过程中若自动修改了文件，再跑受影响的检查。

## 禁止

- `--no-verify`、`--no-gpg-sign`、`git push --force`、`git reset --hard`。
- 不读 diff 就写提交信息。
- 把不相关的改动塞进同一个 commit 来"顺手清理"。

## 返回

每个 commit 的哈希与标题 → 跑了什么检查、结果 → 未提交的遗留文件及原因。
