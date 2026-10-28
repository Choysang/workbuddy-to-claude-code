# 编码质量 A/B 基准：原厂 5.8.4 vs 工程版

固定模型（deepseek-v4.1-flash），比较原厂 WorkBuddy 与工程版在同一组编码任务上的结果。主指标是**隐藏验收测试通过率**；调用次数、token、工具使用、耗时与子代理派发作为辅助指标，均从 trace 读取。

已有证据只说明工程版每次请求的 prompt 更小（首个请求约 40K → 24–31K token）。编码质量是否提高，要靠这里的实测回答。

## 内容

| 路径 | 用途 |
|---|---|
| `tasks/<id>/seed/` | 每次运行的初始工作区，`prepare` 复制到独立目录 |
| `tasks/<id>/prompt.md` | 任务说明，`prepare` 打印完整的粘贴文本 |
| `tasks/<id>/hidden/` | 隐藏验收测试，评分时才放进工作区的**临时副本** |
| `tasks/<id>/reference/` | 参考解，只用于证明隐藏测试可通过（`tests/test_bench_score.py`） |
| `score.py` | `prepare` / `pids` / `score` / `summary` |
| `make_fixture.py` | 把真实 trace 缩成无敏感内容的测试夹具 |
| `fixtures/traces/` | 由 18504（工程版，派发子代理）和 12660（原厂）缩成的夹具 |

| 任务 | 类型 | 隐藏测试检查什么 |
|---|---|---|
| `t01_bugfix` | 缺陷修复 | Decimal 金额、半进位舍入、折扣越界报 `ValueError` |
| `t02_feature` | 多文件功能 | 优先级贯穿 model/storage/CLI、旧存储兼容、排序稳定、非法值退出码 2 |
| `t03_refactor` | 带测试重构 | 新函数契约、7 组边界输入与原实现逐字节一致、`generate_report` 变薄 |
| `t04_build_repair` | 构建修复 | 循环导入、Python 3.10+ 移除的 `collections.Iterable`、改名函数；不得修改 `tests/` |
| `t05_explore` | 需探索仓库 | 新 `tsv` 格式须沿用注册表、值转换与已有转义工具 |
| `t06_semver` | 规范实现 | SemVer 2.0.0 优先级、构建元数据、非法版本拒绝 |

每个 seed 都不能通过隐藏测试，而 seed 加参考解可以通过，单元测试持续检查这一点。

## 准备（一次）

1. 本机 Python 3.10+ 已安装 `pytest`。被测 agent 和 `score.py` 使用同一个 Python。
2. 运行目录默认 `D:\wb-bench-runs`（可用环境变量 `WB_BENCH_RUNS` 或 `--runs-root` 修改）。它必须在本仓库之外，避免 agent 搜到隐藏测试和参考解。
3. trace 默认读取 `D:\MovedFromC\.workbuddy-ai\traces`（可用 `WB_TRACES_ROOT` 或 `--traces-root` 修改）。
4. 两个版本使用相同设置：模型选 **deepseek-v4.1-flash**，权限/自动批准模式一致，其他设置不改。
5. 结果写入 `bench/results/results.jsonl`。该目录已加入 `.gitignore`，结果中有本机路径。

## 两个版本怎么启动

- **原厂（stock）**：开始菜单或桌面的原厂 “WorkBuddy AI” 入口，程序位于 `D:\Program Files\WorkBuddyAI`。
- **工程版（eng）**：桌面或开始菜单的 “WorkBuddy AI 工程版” 快捷方式，程序位于 `D:\MovedFromC\.workbuddy-ai\.harness\engineering\versions\5.8.4-9640fccbaaeccffa`。
- 同一时间只运行一个版本。切换前从托盘完全退出，否则单实例机制可能仍展示旧程序。
- 基准期间不要运行 `harness.py apply/build`。两版共用配置目录，配置变化会同时影响两组结果。

`score.py` 从首个系统提示中的 `<harness_profile>` 标签判断实际版本（工程版有，原厂没有），并打印模型名。实际版本与计划不符时，丢弃该次运行。

## 运行矩阵

6 个任务 × 2 个版本 × 每版本至少 N=2 次，共 24 次以上。要做决定建议 N=3（36 次）：N=2 时，每组相差一次通过不能说明差别。

交替顺序抵消时段和服务端波动：第 1 轮先 stock 再 eng，第 2 轮先 eng 再 stock，第 3 轮再先 stock。同一轮内按 t01→t06 依次跑。

## 每次运行的步骤

以 `t02_feature`、工程版、第 1 次为例。命令在仓库根目录执行。

1. 生成全新的工作区并获取粘贴文本：

   ```powershell
   python bench/score.py prepare t02_feature --build eng --run 1
   ```

   目录已存在时命令拒绝执行；每次运行使用新的 `--run` 编号。

2. 启动对应版本，**新建会话**。不要在已有会话里继续，不要复用其他运行的会话。界面能选会话工作目录时，选第 1 步打印的 `workspace:` 目录。
3. 记下开始时间，粘贴 `---- paste ... ----` 与 `---- end ----` 之间的全部文本，作为第一条也是唯一一条消息发送。文本格式固定：

   ```text
   Workspace: D:/wb-bench-runs/t02_feature-eng-r1

   <tasks/t02_feature/prompt.md 的内容>

   Work only inside the workspace folder above. Do not ask me questions; make reasonable assumptions and state them. Finish by running the tests.
   ```

4. 不干预。工具审批弹窗一律同意（两版相同）。agent 仍然提问时，只回复 `Proceed with your best judgment.`，`score.py` 会记录多出的回合并警告。
5. agent 结束回复后停止。超过 20 分钟未结束，手动停止，照常评分并在 `--label` 写 `timeout`。
6. 找到这次运行的 CLI PID：

   ```powershell
   python bench/score.py pids --minutes 30 --workspace D:/wb-bench-runs/t02_feature-eng-r1
   ```

   选择开始时间匹配、`build` 正确、`ws_hits` 大于 0 的那一行。

7. 评分并追加结果：

   ```powershell
   python bench/score.py score --workspace D:/wb-bench-runs/t02_feature-eng-r1 --pid 12345 --append bench/results/results.jsonl
   ```

   一个 PID 目录同时含其他会话的 trace 时，加 `--since 2026-10-28T03:00:00Z`（trace 时间为 UTC）缩小范围。出现 `WARNING` 时先核对 PID 再保留结果。

8. 关闭会话，进入下一次运行。

全部完成后汇总：

```powershell
python bench/score.py summary bench/results/results.jsonl
```

## 指标口径

| 指标 | 来源 |
|---|---|
| hidden PASS/FAIL | 工作区复制到临时目录，加入 `hidden/`，`python -m pytest`；原工作区不改动 |
| visible | 同一副本中除隐藏测试外的测试（含 agent 自己写的），只作参考 |
| main calls | 主代理（根 `cli` agent span 下）的 generation span 数 |
| first / main_total tokens | 第一个主代理 generation 和全部主代理 generation 的 `usage.prompt_tokens`；`main_cached` 为其中缓存命中部分 |
| all_agents_total | 主代理加子代理的 prompt tokens |
| tools | 按工具名统计 function span，主代理与子代理分开 |
| subagents | 子 agent span 名称；`Agent calls` 为主代理调用 Agent 工具次数（含失败） |
| wall | 每回合根 `cli` span 的起止时间之和；span 未结束时用最早开始到最晚结束 |

标题生成（`terminalTitleGenerator`）的 trace 不计入。trace 的 toolInput 被截断到 2 万字符，不影响以上指标：用量在 toolOutput 中，版本标签在系统提示开头。

## 局限

- 对比的是整套产品行为（系统提示、工具清单、插件、hooks）。结果不能归因到单项改动。
- 两版共用用户配置目录。已安装到共享目录的用户规则、技能等会同时作用于两版。
- 每组样本很少。通过率差 1–2 次时，先加跑再下结论。
- 子代理派发多少不是越多越好，只用来解释通过率与成本差异。

## 开发

```powershell
python -m unittest discover tests -q
python bench/make_fixture.py D:/MovedFromC/.workbuddy-ai/traces/<pid>/trace_<id>.jsonl bench/fixtures/traces/<pid>/trace_<id>.jsonl
```

夹具只保留 span 结构、时间、状态、模型名、`harness_profile` 标签、用量和 Agent 的 `subagent_type`；工具输入替换为占位路径 `D:/bench/ws`。

## 跨 harness 对照：Claude Code + DeepSeek

公开基准里没有 deepseek-v4.1-flash 在 WorkBuddy、Claude Code、pi、DeepSeek Harness 上的同模型对比。Terminal-Bench 从 3.0 起每个模型只列一个 harness；Composio 的五 harness 对比用的是 V4 Pro 和非公开的 SaaS 任务。本机没有 Docker，WorkBuddy 也不能无界面运行，官方 Terminal-Bench 跑不了。所以对照用本目录的 6 个隐藏验收任务，记录的指标和 Classmethod 的同模型对比一致：请求数、工具调用、首个请求输入、含缓存的总输入、输出、测试结果。

`run_claude.py` 自动完成一次 Claude Code 运行：
- 用与 WorkBuddy 相同的种子和第一条消息，`claude -p` 无界面执行。
- 配置目录为空：没有用户的 CLAUDE.md、hooks、插件和 MCP，即原版 Claude Code。
- 模型走 DeepSeek 的 Anthropic 兼容接口 `https://api.deepseek.com/anthropic`，所有档位（含子代理）都用 `deepseek-flash`（官方文档说明由 DeepSeek-V4.1-Flash 提供）。
- 结果以 `build=claude-code` 写进同一个 results.jsonl，`score.py summary` 直接并列比较。原始事件流保存在工作区旁的 `<run>.stream.jsonl`。

```powershell
$env:DEEPSEEK_API_KEY = "<your key>"
python bench/run_claude.py t01_bugfix --run 1 --append bench/results/results.jsonl
```

注意：WorkBuddy 托管的 deepseek-v4.1-flash 与 DeepSeek 官方 API 的 `deepseek-flash` 未必是同一个服务端版本，对比结论要写明这一点。
