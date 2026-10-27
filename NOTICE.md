# 开源整理说明（Sanitization Notice）

本仓库从一份私有改造包整理而来。开源时做了如下处理，接手维护请保持同样标准：

**已剔除（不随仓库分发）**
- `backups/`、`analysis/`——本地备份与 trace 分析产物，含个人信息。
- `payload/SOUL.md`、`payload/USER.md` 与对应测试夹具——个人工作准则与环境信息（内网服务器、端口等）。测试夹具已换成中性占位文本。
- 内部业务技能（周报类）——**含明文主机口令与内网拓扑**。提醒：任何技能/文档在入库前先扫口令与内网 IP。
- 第三方技能（mattpocock / karpathy / caveman 等来源）——许可归属不同，不随本仓库再分发；请自行从原渠道安装。
- `tests/fixtures/code-prompt-*.tpl`——完整产品提示词不分发。当前安装测试使用中性合成文本，无需自备厂商夹具。

**已替换**
- 绝对路径与用户名 → 相对路径 / `<you>` 占位。
- skills-audit 的归档路径改为动态取仓库相对路径。

**审查基线**
- 出库前全量 grep：`api[_-]?key|token|secret|password|Bearer|sk-|内网 IP|用户名|邮箱|微信 ID`。
- 20+ 出厂检测请再跑一遍你环境里的 secret scanner（gitleaks / trufflehog）。

本仓库不分发 WorkBuddy / CodeBuddy 程序包和完整原始提示词。工程模板由保留的产品骨架与自写工程指令组成；本地补丁包含定位所需的少量源码匹配片段。`apply` 修改配置；用户明确选择 `build` 时，从本机原厂安装生成独立程序副本并修改其中的 ASAR/CLI，原安装保留。生成程序、凭据、完整日志及备份不提交。

**2026-10-15 追加（gitleaks 复检）**
- gitleaks 8.30.1 全量扫描发现 `tests/fixtures/settings.json` 内含微信渠道绑定（明文 userId + 加密 botToken 信封），已整字段剔除；工作区复扫 0 泄漏。
- 注意：首次提交的 git 历史仍留有该脱敏前快照（字段已加密或属账号标识，非明文口令）。如需连历史一并清除，需重写历史 + force push，维护者自行执行 `git filter-repo` 或重建仓库。
