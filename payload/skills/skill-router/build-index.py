#!/usr/bin/env python3
"""Rebuild skill-router/index.md from ~/.claude/skill-library/{commands,ecc}.
Usage: python build-index.py   (run after adding/removing library entries)
"""
import os, re

HOME = os.path.expanduser('~')
LIB = os.path.join(HOME, '.claude', 'skill-library')
OUT = os.path.join(HOME, '.claude', 'skills', 'skill-router', 'index.md')

def fm_desc(path, fallback):
    try:
        txt = open(path, encoding='utf-8', errors='replace').read(2000)
    except Exception:
        return fallback, ''
    m = re.match(r'^---\n(.*?)\n---', txt, re.S)
    body = m.group(1) if m else txt[:400]
    name_m = re.search(r'^name:\s*(.+)$', body, re.M)
    desc_m = re.search(r'^description:\s*(.+)$', body, re.M)
    desc = re.sub(r'\s+', ' ', desc_m.group(1)).strip().strip('"\'') if desc_m else ''
    return (name_m.group(1).strip() if name_m else fallback), desc

def trunc(s, n=120):
    return (s[:n] + '…') if len(s) > n else s

rows_cmd, rows_ecc = [], []
for f in sorted(os.listdir(os.path.join(LIB, 'commands'))):
    if f.endswith('.md'):
        _, desc = fm_desc(os.path.join(LIB, 'commands', f), f[:-3])
        rows_cmd.append((f[:-3], desc))
for d in sorted(os.listdir(os.path.join(LIB, 'ecc'))):
    p = os.path.join(LIB, 'ecc', d, 'SKILL.md')
    if os.path.isfile(p):
        name, desc = fm_desc(p, d)
        rows_ecc.append((name or d, desc))

out = ['# skill-router 路由索引', '',
       '用法见同目录 SKILL.md。匹配顺序：用户措辞/命令名 → 下表「名称」关键词命中 → 读取对应路径的文件执行。',
       '', '## A. 工作流命令（~/.claude/skill-library/commands）', '',
       '| 名称 | 用途 | 路径 |', '|---|---|---|']
for n, d in rows_cmd:
    out.append(f'| {n} | {trunc(d)} | ~/.claude/skill-library/commands/{n}.md |')
out += ['', '## B. ECC 领域技能（~/.claude/skill-library/ecc）', '',
        '| 名称 | 用途 | 路径 |', '|---|---|---|']
for n, d in rows_ecc:
    out.append(f'| {n} | {trunc(d)} | ~/.claude/skill-library/ecc/{n}/SKILL.md |')
out.append('')
open(OUT, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
print(f'index rebuilt: {len(rows_cmd)} commands + {len(rows_ecc)} ecc skills -> {os.path.getsize(OUT)} bytes')
