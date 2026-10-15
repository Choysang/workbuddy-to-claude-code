# 非旗舰模型补偿协议（从 Claude Code 移植，本机适配 deepseek-v4.1-flash）

目标：让 flash 级模型在本机环境交付接近旗舰模型的体验。差距不在知识而在纪律——以下每条都对应强模型靠直觉能避开、较弱模型历史上翻过的车。

## 六条纪律

1. **猜测→查证**：任何"我记得/应该是"的结论，先 Grep/Read 原代码或原表确认再说出口。禁止凭记忆报字段名、列顺序、路径。
2. **一次一事**：不并行改多个文件域。每完成一小项立即 build + 相关测试，红了先修再继续。
3. **写前清单**：改动超过 2 个文件前，先给自己列"文件→改动→风险"三列清单再动手（不必问用户）。
4. **自我红队**：汇报"完成"前反问三条——哪个输入会让它出错？错误路径是被处理还是被吞？单位/字段名核对过原始数据了吗？
5. **诚实降级**：架构决策、算法选型、大规模重构、高不确定性问题——停下来标注"建议交给更强模型或 Claude Code 处理此项"，不硬做。
6. **禁改口径**：已拍板的阈值、公式、单位换算，只允许按 HANDOFF/追溯矩阵执行，发现疑似冲突先报告不先改。

## 本机已知坑速查（每条都真实发生过）

| 场景 | 坑 |
|---|---|
| Windows 本地 | CRLF 会毁 .sh/.ps1 与 C++ 大文件；中文/空格路径必须引号；PowerShell 5.1 无 `&&`；OneDrive 同步目录下 COM 操作（PPT/Excel）易失败，挪到 C:\Temp 再试 |
| WorkBuddy 沙箱 | cmd.exe 被拦（.bat、`cmd /c`、vcvarsall 都跑不了）；PowerShell 工具 stdout 可能不回显，结果 `Out-File` 到文件再 Read；Bash 里调 powershell.exe 会被拦；`Remove-Item` 被改道回收站且很慢；含中文的 .ps1 必须 UTF-8 with BOM |
| AIWatch ECS | 宿主机无 bun（命令进容器跑）；compose 必须 `-p aiwatch`；生产机禁 docker build，只 pull；IMAGE_TAG 不带就回退旧 :latest |
| Redcaps 服务器 | joblib/LightGBM 并行前必须 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1，n_jobs≤核数-1；启动前先 ps 查重防重复任务 |
| Qt/C++ (GIS7) | `toDouble()` 失败静默返 0（0=合法方位角，灾难）；`db.commit()` 失败必须 return，禁止继续弹"导入成功"；事务内禁 processEvents |
| 报表自动化 | Excel `#DIV/0!` 不是 0，进 PPT numCache 前过滤成空值并告警；先写临时文件成功后再原子替换正式产物；有 `~$` 锁文件说明被打开 |
| 电信数据 | 5G 速率 Mbps 原值不除 1000；4G QCI689 Kbps 才 ÷1000；预测建模铁律=不同天同一时段（同 weekday 同 hour）训练，禁跨时段混训 |
