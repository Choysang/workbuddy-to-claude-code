# workbuddy-to-claude-code

把 WorkBuddy 的编码体验改造成 Claude Code 的形状——**只写 `~/.workbuddy-ai`，不碰安装文件，每一步字节级可回滚**。

WorkBuddy 的 Agent 内核（CodeBuddy Code CLI 2.161）与 Claude Code 同构：同名工具集（Read/Edit/MultiEdit/Write/Glob/Grep/Bash/PowerShell/Agent/TaskCreate/Skill/ToolSearch/WebFetch/WebSearch）、同款 29 事件 hook 机制、同样的 `CODEBUDDY.md` 常驻规则 + `agents/` 子代理 + `commands/` 斜杠命令 + 自动压缩。默认体验差不是引擎弱，而是产品层把能力压住并灌满了办公/设计/金融内容。这个仓库把那些内容卸掉，把引擎本来的编码面全部打开。

## 三条命令

```bash
python scripts/harness.py apply      # 安装 / 同步（幂等，可 --dry-run 预览）
python scripts/harness.py verify     # 静态校验，--runtime 追加运行时证据
python scripts/harness.py rollback   # 回到最近一次备份
```

`apply` 后重启 WorkBuddy 生效。升级产品后再跑一次 `apply`（新插件缓存目录里的 `prompt.tpl` 会被重新覆盖，停用的插件会被重新置 false）。

辅助命令：`status`（逐文件比对 profile 与已安装状态，列出缺失/偏离）、`doctor`（配置目录可写、python/node/git、提示词目标数、hooks 目录）。

## 改造后的形态

| 维度 | 内容 |
|---|---|
| 常驻记忆 | 单一 `CODEBUDDY.md`，832 字符（原 6504 字符 + `rules/engineering.md` 3037 字节两份重复注入） |
| 系统提示 | 编码版模板：保留产品必需骨架（模式分支、content_policy、response_language、binary context），删掉办公路由 / 连接器推销 / 技能市场 / 记忆系统长文 |
| 子代理 | 9 个：architect、code-reviewer、silent-failure-hunter、debugger、verifier、build-error-resolver、lane-worker、worktree-worker、docs-lookup |
| 斜杠命令 | 5 个：`/plan`、`/review`、`/verify`、`/lanes`、`/commit` |
| Hook | 3 个：SessionStart 注入 `<repo_state>`；PreToolUse 拦灾难性命令；PostToolUse 语法门禁（py/json/toml/yaml/sh/js） |
| 权限 | `defaultMode: acceptEdits`，子代理同模式 |
| 上下文 | `autoCompactWindow: auto`、`alwaysThinkingEnabled`、`reasoningEffort: high`、`fileCheckpointingEnabled`、`deferToolLoading` |
| 插件 | 45 个非工程插件置 `false`（office / 设计 / 金融 / 文档 / 连接器 / 支付 / 会议），提示词基础设施 `welcomemode-*` `interactionmode-*` `prompt-common` 保持启用 |

Hook 退出码按 Claude Code 语义：`0` 通过，`2` 阻塞并把 stderr 回传模型，其他非零只提示不阻塞。三个脚本内部异常一律 `exit 0`——门禁失效不该卡住工作。

## 设计取舍

- **只改配置层，不改二进制**。`app.asar` 有完整性校验与签名，改了就起不来；配置层已经足够放下整套 harness。
- **规则只留一份**。两处重复注入的规则文件合并成 `CODEBUDDY.md`，冲突时以它为准。
- **不做过度防护**。`pre_tool_guard` 只拦真正不可逆的命令（`rm -rf /`、`mkfs`、`dd of=/dev/sd*`、fork 炸弹、`format X:`、PowerShell 递归删 `C:\`），工作区内的普通删除、`git push --force` 一律放行——安全边界应该由权限模式和 review 承担，不是靠一堆正则制造摩擦。
- **失败要吵**。`verify` 实跑三个 hook 验证退出码，不看配置能否解析就算过。
- **子代理是输入不是证据**。`code-reviewer` / `verifier` 的结论需要自己核，关键路径跑真实验证。

## 验证

```bash
python -m unittest discover tests -q     # 28 项
python scripts/harness.py verify         # 24 项静态检查，含三个 hook 实跑
```

`verify` 覆盖：配置目录、`CODEBUDDY.md` 体量与结构、无重复 rules、agents ≥6 / commands ≥3 且 frontmatter 有 `description`、办公键已移除、权限模式、hooks 三脚本已注册且文件存在、坏 py → exit 2 / 好 py → exit 0 / `rm -rf /` → exit 2 / `ls -la` → exit 0 / SessionStart → exit 0、提示词已替换、办公插件已停用、解释器可用。

### 三态结果

`verify` 输出 `PASS / WARN / FAIL`，只有 `FAIL` 影响退出码。

原因：运行中的 WorkBuddy 把 `settings.json` 常驻内存并周期性回写磁盘，用它自己的模型覆盖文件，抹掉它不认识的键（`fileCheckpointingEnabled`、`alwaysThinkingEnabled`、部分 `enabledPlugins`）。实测 `apply` 于 `10:48:15` 写盘正确，`settings.json` 的 mtime 在 63 秒后变成 `10:49:18`——进程几乎实时回写。把这种偏差判成 harness 的缺陷会让人一直追一个不存在的 bug。

所以高波动检查（记忆与快照开关、办公插件已停用）在 `settings.json` 的 mtime 晚于 `state.json` 记录的 `applied` 时间戳时降级为 `WARN`，并附提示：关闭 WorkBuddy 后重跑 `apply` 与 `verify`。若 mtime 没有变晚（说明是 harness 自己写错了），仍然是 `FAIL`。

`verify --runtime` 追加读运行日志：`hooks/harness-hooks.log`、`logs/**/harness__*.log` 里的 `[MemoryLoader] Loaded N memory rules` 与是否含 `CODEBUDDY.md`、最近 6 个 trace 是否含编码版提示词标记。

## 回滚

每次 `apply` 前把将被覆盖或删除的每个文件 `copy2` 进 `~/.workbuddy-ai/.harness/backups/<时间戳>-apply/`，`manifest.json` 记录原路径与「是否原本存在」。`rollback` 按相反方向执行：原本存在的回写字节，原本不存在的 `unlink` 删除（安装新增的文件不会残留）。

```bash
python scripts/harness.py rollback --dry-run          # 看计划
python scripts/harness.py rollback --backup <目录>     # 指定某次
```

## 仓库地图

```
profile/
  CODEBUDDY.md           # 唯一常驻规则
  settings.json          # 权限 / 上下文 / hooks（{python} 与 {hook:name} 占位符在安装时展开为绝对路径）
  plugins.json           # disable / keep 两份插件清单
  prompt/prompt.tpl      # 编码版系统提示模板
  agents/*.md            # 9 个子代理
  commands/*.md          # 5 个斜杠命令
  hooks/*.py             # 3 个 hook
scripts/
  harness.py             # 入口：apply / status / verify / rollback / doctor
  install.py             # profile → 配置目录，含 settings 合并与 hook 命令渲染
  verify.py              # 静态 + 运行时校验
  rollback.py            # 备份恢复
  common.py              # 路径、原子写、备份、解释器探测
tests/                   # hook 行为 + 安装/回滚
docs/legacy-eval-5.6.2.md # 旧版（v2）实测数据存档
```

`settings.json` 里的 `{python}` 在安装时替换为当前解释器绝对路径（正斜杠），`{hook:session_start}` 等替换为 `~/.workbuddy-ai/hooks/*.py`。合并 `settings.json` 时会先剔除自身旧 hook 条目再写入，用户自己的 hook 原样保留。

## 安全边界

- 只写 `~/.workbuddy-ai/`；**不修改 `app.asar`**、不碰签名与完整性校验。
- 不绕过授权、不破解付费能力；停用插件只写 `enabledPlugins: false`，随时可改回。
- 不含产品代码与产品提示词原文；模板是从本机插件缓存读出的产品骨架 + 自写编码层。
- 敏感内容剔除记录见 [NOTICE.md](NOTICE.md)。

## License

[MIT](LICENSE)
