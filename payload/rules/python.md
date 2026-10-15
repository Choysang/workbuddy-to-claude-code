---
paths:
  - "**/*.py"
  - "**/*.ipynb"
  - "**/requirements*.txt"
  - "**/pyproject.toml"
---

# Python 规则（读写 Python 文件时生效）

- 改完的文件要能编译：`python -m py_compile <file>`（编辑 hook 会自动检查，报错先修）。
- 跑脚本优先用项目自带 venv；没有就用托管运行时。不要全局 `pip install`。
- pandas 读入 Excel/CSV 后，先看 `shape`、`columns`、`dtypes`、`head(3)`。列名从数据读，不凭记忆写。
- merge/concat/append 前后对账行数；merge 用 `validate=` 防止意外一对多；groupby 后检查是否丢行。
- 数值列里的 `#DIV/0!`、`#N/A`、空串转成 NaN，并统计数量告警。不得静默填 0。
- 单位换算只对明确字段做，并注明依据。
- 写出文件：先写临时文件，校验通过后用 `os.replace` 原子替换。目标 Excel 有 `~$` 锁文件时先报告，不要硬写。
- 路径用 `pathlib`。读 CSV 指定编码（先 `utf-8-sig`，失败再 `gbk`），写出指定 `encoding=`。
- 异常不吞：`except` 要记录上下文或重新抛出；禁止裸 `except: pass`。
- 有 `tests/` 就跑 `pytest -q`；没有就用最小样例跑主入口，并核对输出的行数和关键字段。
