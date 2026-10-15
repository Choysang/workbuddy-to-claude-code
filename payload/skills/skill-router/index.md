# skill-router 路由索引

用法见同目录 SKILL.md。匹配顺序：用户措辞/命令名 → 下表「名称」关键词命中 → 读取对应路径的文件执行。

## A. 工作流命令（~/.claude/skill-library/commands）

| 名称 | 用途 | 路径 |
|---|---|---|
| aside | Answer a quick side question without interrupting or losing context from the current task. Resume work automatically aft… | ~/.claude/skill-library/commands/aside.md |
| auto-update | Pull the latest ECC repo changes and reinstall the current managed targets. | ~/.claude/skill-library/commands/auto-update.md |
| build-fix | Detect the project build system and incrementally fix build/type errors with minimal safe changes. | ~/.claude/skill-library/commands/build-fix.md |
| checkpoint | Create, verify, or list workflow checkpoints after running verification checks. | ~/.claude/skill-library/commands/checkpoint.md |
| cpp-build | Fix C++ build errors, CMake issues, and linker problems incrementally. Invokes the cpp-build-resolver agent for minimal,… | ~/.claude/skill-library/commands/cpp-build.md |
| cpp-review | Comprehensive C++ code review for memory safety, modern C++ idioms, concurrency, and security. Invokes the cpp-reviewer … | ~/.claude/skill-library/commands/cpp-review.md |
| cpp-test | Enforce TDD workflow for C++. Write GoogleTest tests first, then implement. Verify coverage with gcov/lcov. | ~/.claude/skill-library/commands/cpp-test.md |
| evolve | Analyze instincts and suggest or generate evolved structures | ~/.claude/skill-library/commands/evolve.md |
| feature-dev | Guided feature development with codebase understanding and architecture focus | ~/.claude/skill-library/commands/feature-dev.md |
| harness-audit | Run a deterministic repository harness audit and return a prioritized scorecard. | ~/.claude/skill-library/commands/harness-audit.md |
| hookify-configure | Enable or disable hookify rules interactively | ~/.claude/skill-library/commands/hookify-configure.md |
| hookify-help | Get help with the hookify system | ~/.claude/skill-library/commands/hookify-help.md |
| hookify-list | List all configured hookify rules | ~/.claude/skill-library/commands/hookify-list.md |
| hookify | Create hooks to prevent unwanted behaviors from conversation analysis or explicit instructions | ~/.claude/skill-library/commands/hookify.md |
| instinct-export | Export instincts from project/global scope to a file | ~/.claude/skill-library/commands/instinct-export.md |
| instinct-import | Import instincts from file or URL into project/global scope | ~/.claude/skill-library/commands/instinct-import.md |
| instinct-status | Show learned instincts (project + global) with confidence | ~/.claude/skill-library/commands/instinct-status.md |
| learn-eval | Extract reusable patterns from the session, self-evaluate quality before saving, and determine the right save location (… | ~/.claude/skill-library/commands/learn-eval.md |
| learn | Extract reusable patterns from the current session and save them as candidate skills or guidance. | ~/.claude/skill-library/commands/learn.md |
| loop-start | Start a managed autonomous loop pattern with safety defaults and explicit stop conditions. | ~/.claude/skill-library/commands/loop-start.md |
| loop-status | Inspect active loop state, progress, failure signals, and recommended intervention. | ~/.claude/skill-library/commands/loop-status.md |
| model-route | Recommend the best model tier for the current task based on complexity, risk, and budget. | ~/.claude/skill-library/commands/model-route.md |
| multi-backend | Run a backend-focused multi-model workflow for APIs, algorithms, data, and business logic. | ~/.claude/skill-library/commands/multi-backend.md |
| multi-execute | Execute a multi-model implementation plan while preserving Claude as the only filesystem writer. | ~/.claude/skill-library/commands/multi-execute.md |
| multi-plan | Create a multi-model implementation plan without modifying production code. | ~/.claude/skill-library/commands/multi-plan.md |
| multi-workflow | Run a full multi-model development workflow with research, planning, execution, optimization, and review. | ~/.claude/skill-library/commands/multi-workflow.md |
| plan | Restate requirements, assess risks, and create step-by-step implementation plan. WAIT for user CONFIRM before touching a… | ~/.claude/skill-library/commands/plan.md |
| projects | List known projects and their instinct statistics | ~/.claude/skill-library/commands/projects.md |
| promote | Promote project-scoped instincts to global scope | ~/.claude/skill-library/commands/promote.md |
| prp-commit | Quick commit with natural language file targeting — describe what to commit in plain English | ~/.claude/skill-library/commands/prp-commit.md |
| prp-implement | Execute an implementation plan with rigorous validation loops | ~/.claude/skill-library/commands/prp-implement.md |
| prp-plan | Create comprehensive feature implementation plan with codebase analysis and pattern extraction | ~/.claude/skill-library/commands/prp-plan.md |
| prp-pr | Create a GitHub PR from current branch with unpushed commits — discovers templates, analyzes changes, pushes | ~/.claude/skill-library/commands/prp-pr.md |
| prp-prd | Interactive PRD generator - problem-first, hypothesis-driven product spec with back-and-forth questioning | ~/.claude/skill-library/commands/prp-prd.md |
| prune | Delete pending instincts older than 30 days that were never promoted | ~/.claude/skill-library/commands/prune.md |
| python-review | Comprehensive Python code review for PEP 8 compliance, type hints, security, and Pythonic idioms. Invokes the python-rev… | ~/.claude/skill-library/commands/python-review.md |
| quality-gate | Run the ECC quality pipeline for a file or project scope and report remediation steps. | ~/.claude/skill-library/commands/quality-gate.md |
| refactor-clean | Safely identify and remove dead code with verification after each change. | ~/.claude/skill-library/commands/refactor-clean.md |
| resume-session | Load the most recent session file from ~/.claude/session-data/ and resume work with full context from where the last ses… | ~/.claude/skill-library/commands/resume-session.md |
| review-pr | Comprehensive PR review using specialized agents | ~/.claude/skill-library/commands/review-pr.md |
| save-session | Save current session state to a dated file in ~/.claude/session-data/ so work can be resumed in a future session with fu… | ~/.claude/skill-library/commands/save-session.md |
| sessions | Manage Claude Code session history, aliases, and session metadata. | ~/.claude/skill-library/commands/sessions.md |
| skill-create | Analyze local git history to extract coding patterns and generate SKILL.md files. Local version of the Skill Creator Git… | ~/.claude/skill-library/commands/skill-create.md |
| skill-health | Show skill portfolio health dashboard with charts and analytics | ~/.claude/skill-library/commands/skill-health.md |
| test-coverage | Analyze coverage, identify gaps, and generate missing tests toward the target threshold. | ~/.claude/skill-library/commands/test-coverage.md |
| update-codemaps | Scan project structure and generate token-lean architecture codemaps. | ~/.claude/skill-library/commands/update-codemaps.md |
| update-docs | Sync documentation from source-of-truth files such as scripts, schemas, routes, and exports. | ~/.claude/skill-library/commands/update-docs.md |

## B. ECC 领域技能（~/.claude/skill-library/ecc）

| 名称 | 用途 | 路径 |
|---|---|---|
| configure-ecc | Interactive installer for Everything Claude Code — guides users through selecting and installing skills and rules to use… | ~/.claude/skill-library/ecc/configure-ecc/SKILL.md |
| continuous-learning-v2 | Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence scoring, and e… | ~/.claude/skill-library/ecc/continuous-learning-v2/SKILL.md |
| cpp-coding-standards | C++ coding standards based on the C++ Core Guidelines (isocpp.github.io). Use when writing, reviewing, or refactoring C+… | ~/.claude/skill-library/ecc/cpp-coding-standards/SKILL.md |
| cpp-testing | Use only when writing/updating/fixing C++ tests, configuring GoogleTest/CTest, diagnosing failing or flaky tests, or add… | ~/.claude/skill-library/ecc/cpp-testing/SKILL.md |
| database-migrations | Database migration best practices for schema changes, data migrations, rollbacks, and zero-downtime deployments across P… | ~/.claude/skill-library/ecc/database-migrations/SKILL.md |
| deep-research | Multi-source deep research using firecrawl and exa MCPs. Searches the web, synthesizes findings, and delivers cited repo… | ~/.claude/skill-library/ecc/deep-research/SKILL.md |
| deployment-patterns | Deployment workflows, CI/CD pipeline patterns, Docker containerization, health checks, rollback strategies, and producti… | ~/.claude/skill-library/ecc/deployment-patterns/SKILL.md |
| docker-patterns | Docker and Docker Compose patterns for local development, container security, networking, volume strategies, and multi-s… | ~/.claude/skill-library/ecc/docker-patterns/SKILL.md |
| eval-harness | Formal evaluation framework for Claude Code sessions implementing eval-driven development (EDD) principles | ~/.claude/skill-library/ecc/eval-harness/SKILL.md |
| hookify-rules | This skill should be used when the user asks to create a hookify rule, write a hook rule, configure hookify, add a hooki… | ~/.claude/skill-library/ecc/hookify-rules/SKILL.md |
| mcp-server-patterns | Build MCP servers with Node/TypeScript SDK — tools, resources, prompts, Zod validation, stdio vs Streamable HTTP. Use Co… | ~/.claude/skill-library/ecc/mcp-server-patterns/SKILL.md |
| python-patterns | Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python… | ~/.claude/skill-library/ecc/python-patterns/SKILL.md |
| python-testing | Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements. | ~/.claude/skill-library/ecc/python-testing/SKILL.md |
| security-scan | Scan your Claude Code configuration (.claude/ directory) for security vulnerabilities, misconfigurations, and injection … | ~/.claude/skill-library/ecc/security-scan/SKILL.md |
| strategic-compact | Suggests manual context compaction at logical intervals to preserve context through task phases rather than arbitrary au… | ~/.claude/skill-library/ecc/strategic-compact/SKILL.md |
| token-budget-advisor | >- | ~/.claude/skill-library/ecc/token-budget-advisor/SKILL.md |
