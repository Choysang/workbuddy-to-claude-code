---
paths:
  - "**/*.js"
  - "**/*.mjs"
  - "**/*.cjs"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/package.json"
---

# JS/TS 规则（读写 JS/TS 文件时生效）

- 改完的 `.js/.mjs/.cjs` 要能通过 `node --check`（编辑 hook 会自动检查）。TS 项目有 `tsconfig.json` 时跑 `npx tsc --noEmit`。
- 用项目已有的包管理器：看 lock 文件（`package-lock.json`→npm，`pnpm-lock.yaml`→pnpm，`yarn.lock`→yarn），不要混用。
- 不新增依赖，除非确有必要；新增时说明理由。不要 `npm install -g`。
- 沿用项目已有的模块风格（ESM/CJS）、格式和命名，不顺手改。
- 前端改动：能启动 dev server 就启动并实际打开页面核对；做不到时列出需要人工目测的点。
