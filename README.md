# workbuddy-to-claude-code

把 WorkBuddy 的编码体验调成 Claude Code —— 一条命令的配置层改造工具包。

WorkBuddy 的 Agent 内核（CodeBuddy Code CLI）与 Claude Code 同构：同名工具集、同款 hook 事件、同样的规则/子代理/自动压缩机制。默认体验差，差距几乎全在产品层配置。这个工具包把引擎里被压住的能力全部放出来，**只改用户配置目录 `~/.workbuddy-ai`，不碰安装文件，每一步可回滚**。

实测效果（431 条 trace 对比）：

| 指标 | 改造前 | 改造后 |
|---|---|---|
| 每次请求 prompt 中位数 | 24.8 万 token | **5.5 万 token** |
| code 模式系统提示 | 32K 字符（办公助手版） | **14.6K（精简编码版）** |
| 用户规则加载 | 0 条 | 全套 rules/ 自动注入 |
| 上下文压缩触发 | ~900K（等于不压） | **~800K @ 1M 窗口** |
| 工具清单 | 大量 0 调用工具 | 按 trace 统计精简 |

## 快速开始

```bash
python scripts/harness.py setup
```

一条命令跑完：安装 payload → 系统提示补丁 → 工具清单补丁 → 语气/插件修正 → MCP/hooks/记忆 → 静态校验。先加 `--dry-run` 可预览。

之后只剩 5 个界面动作（脚本碰不到 UI，图解见 [docs/MANUAL-STEPS.md](docs/MANUAL-STEPS.md)）：

1. 托盘**退出** WorkBuddy（所有脚本操作之前，不是关窗口）
2. 设置 → 打开「自定义 MCP」总开关
3. 连接器管理 → 对 context7 / agentmemory / headroom 各点「信任」
4. 模型设置 → 上下文下拉选 **1M**
5. 设置 → 关「本地技能与记忆沉淀」（防技能自动泛滥）

最后发一个验收任务，跑 `python scripts/harness.py verify --runtime` 取证。

## 命令一览

| 场景 | 命令 |
|---|---|
| 首次安装（一键） | `python scripts/harness.py setup` |
| WorkBuddy 升级后恢复 | `python scripts/harness.py post-update` |
| 验收取证 | `python scripts/harness.py verify --runtime` |
| 只看补丁状态 | `python scripts/harness.py status` |
| 技能审计（防自动沉淀） | `python scripts/harness.py skills-audit` |
| 一键回滚（字节级还原） | `python scripts/harness.py rollback` |

## 改造了什么

- **系统提示精简**：从插件缓存的原始模板*生成*精简编码版（跨版本存活），砍掉办公助手/连接器推荐/技能市场强推，保留安全规则与工具清单
- **规则全套移植**：`~/.claude/rules` → `rules/`，冲突优先级写明（working-style 为准）
- **子代理 50 个、技能、hooks**：编辑后语法检查、简洁输出、命令输出压缩（RTK）
- **MCP**：context7 / agentmemory / headroom（沙箱拦 `cmd.exe`，已改 node 直调 npx）
- **记忆与推理**：分类型自动记忆、思考强度 high、`autoCompactWindow` ≈ 888889
- **瘦身**：停用 0 调用插件、关 SkillManage、清一次性垃圾技能（`skills-audit` 只报告不删）

## WorkBuddy 升级后（必读）

产品自动升级会生成新插件缓存目录（补丁失效）、重置语气、复活停用插件。先退出 WorkBuddy，然后：

```bash
python scripts/harness.py post-update
```

再按 [手动清单](docs/MANUAL-STEPS.md) 复查 5 个界面开关。

## 仓库地图

```
scripts/harness.py       # 统一入口（setup / post-update / verify / status / skills-audit / rollback）
scripts/patch_*.py …     # 各司其职的补丁脚本，全部支持回滚
payload/                 # 装进 ~/.workbuddy-ai 的内容（rules / agents / hooks / 示例技能）
docs/TUTORIAL.md         # 完整改造教程（原理 + 十步 + 数据）
docs/MANUAL-STEPS.md     # 手动步骤图文手册（5 张示意图）
skill/workbuddy-harness/ # Claude Code skill：说「WorkBuddy 升级后恢复」即驱动全流程
tests/                   # 安装/回滚/hook 测试
```

## 安全边界

- 只改 `~/.workbuddy-ai/` 与插件缓存中的提示词模板；**不修改 `app.asar`**（完整性校验 + 数字签名，改了起不来）
- 本仓库不含产品代码与产品提示词原文；不提供任何绕过授权或破解能力
- 出库已过 gitleaks 全量扫描；敏感内容剔除记录见 [NOTICE.md](NOTICE.md)
- 一个真实风险提醒：bypass 模式下智能体可经 Bash 写文件绕过工具规则，常驻指令文件（CLAUDE.md 类）请定期 diff 备份

## 测试

```bash
python -m unittest discover tests -v
```

安装/回滚测试需自备 `tests/fixtures/code-prompt-*.tpl`（产品模板不分发，从本机插件缓存拷入；已被 gitignore）。其余测试不依赖它。

## License

[MIT](LICENSE)
