---
name: remote-long-job
description: Use when 需要在远程服务器（SSH）上启动、监控或清理耗时超过 5 分钟的训练/bakeoff/聚合/批处理任务，或此类任务卡死、CPU 打满、疑似重复启动、需要安全重启时。Also for nohup detached jobs, joblib parallel training on remote boxes.
---

# Remote Long Job — 远程长任务规范

Redcaps 服务器五周实战固化（8×24 bakeoff、5760 模型训练等）。

## 启动

```bash
# 1) 先查重 —— 历史翻车：同一 bakeoff 被重复启动过 3 次
ps aux | grep -E '[b]akeoff|[f]eature_pipeline|[t]rain'
# 2) 限线程再并行 —— 不限则 load 飙到 24+，比单线程还慢
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
nohup python3 job.py --n-jobs $(($(nproc)-1)) > job.log 2>&1 &
echo "pid $!"
```

- n_jobs ≤ 核数-1，永不满核。
- 重跑前 `rm -rf` 旧的半成品输出目录，防新旧混读。
- 密码/token 不进命令行与历史（用 ssh key / .env）。

## 监控

- **一个任务只挂一个监控**——历史一度同任务挂 8 个重复 Monitor，全是浪费。
- 完成判定用**产物文件落盘**（summary.txt / decision_matrix.csv 出现且 mtime 停止变化），不靠日志尾行猜。
- 长任务用 10 分钟级低频轮询，不要 1 分钟高频。
- grep 日志加 `-a`（日志常混二进制/中文，不加会输出 "binary file matches"）。

## 清理与重启

```bash
pkill -9 -f job.py; pkill -9 -f 'joblib.externals.loky'; pkill -9 -f resource_tracker
sleep 3; ps -C python3 -o pid,cmd | grep -iE 'loky|job' || echo ALL CLEAR
```

必须看到 ALL CLEAR 再重启，否则孤儿 loky worker 继续吃 CPU。

## 红线

- 生产 Web 机（如 AIWatch ECS 2C/4G）禁跑构建/训练——只 pull 镜像；重活回本地或计算服务器。
- 宿主机没有运行时（bun/node）的命令进容器跑：`docker compose -p <proj> run --rm worker <cmd>`。
- statsmodels ConvergenceWarning 刷屏是正常噪音，不代表失败；看最终产物。
