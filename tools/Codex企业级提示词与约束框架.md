# Codex 企业级提示词与约束框架

> 目标：把企业级开源项目里常见的 AI 编码代理提示词结构，整理成一套可以直接放进代码仓库的长期规则、可复用工作流和执行约束。

这份文件适合拆成以下几类实际文件：

- 仓库根目录：`AGENTS.md`
- 子系统目录：`services/<name>/AGENTS.override.md` 或 `AGENTS.md`
- 可复用工作流：`.agents/skills/<skill-name>/SKILL.md`
- Codex 项目配置：`.codex/config.toml`
- 机械约束：CI、测试、lint、pre-commit、hooks

---

## 1. 总体原则

企业级 Codex 提示词不是“一段万能 prompt”，而是一套分层治理系统：

1. **长期规则放在 `AGENTS.md`**
   - 项目结构、架构边界、测试命令、代码风格、禁止事项。
   - 适合每次 Codex 进入仓库都必须知道的内容。

2. **复杂流程做成 Skill**
   - 比如：PR Review、估值模型更新、财务数据校验、后端变更流程、安全审计。
   - Skill 负责“什么时候触发、按什么步骤做、最终输出什么”。

3. **关键风险交给工具和自动化拦截**
   - 不能只靠模型记住。
   - 用测试、lint、类型检查、CI、hooks、权限审批、代码所有权规则做硬约束。

4. **提示词要短、具体、可验证**
   - 少写价值观口号，多写“做什么 / 不做什么 / 怎么验证”。
   - 每条规则最好能被检查：命令、文件、边界、验收标准。

---

## 2. 推荐目录结构

```text
repo/
├─ AGENTS.md                         # 仓库级 Codex / coding agent 指令
├─ .codex/
│  ├─ config.toml                    # Codex 项目配置，可放 trusted project、hooks 等
│  └─ hooks.json                     # 可选：工具调用前后检查
├─ .agents/
│  └─ skills/
│     ├─ code-review/
│     │  └─ SKILL.md
│     ├─ architecture-review/
│     │  └─ SKILL.md
│     └─ financial-model-review/
│        └─ SKILL.md
├─ docs/
│  └─ architecture.md                # 人类可读架构说明
├─ services/
│  └─ payments/
│     └─ AGENTS.override.md          # 子系统特殊规则
└─ .github/
   └─ workflows/
      └─ ci.yml                      # 真实执行约束
```

---

## 3. `AGENTS.md` 完整模板

把下面内容复制到仓库根目录的 `AGENTS.md`，再按你的项目替换方括号内容。

```md
# AGENTS.md

This file defines durable instructions for Codex and other coding agents working in this repository.

## Project mission

- This repository is for [describe product / system].
- Primary users are [users].
- The most important quality goals are: correctness, maintainability, security, and explainability.

## Architecture overview

- [frontend/] contains [frontend responsibility].
- [backend/] contains [backend responsibility].
- [data/] contains [data models / pipeline responsibility].
- [docs/] contains architecture and operational documentation.
- [tests/] contains automated tests.

### Architectural boundaries

- UI code must not call external services directly; use the API/client layer.
- Business logic must live in services/domain modules, not controllers or UI components.
- Data validation must happen at system boundaries.
- Shared utilities must be small, documented, and covered by tests.
- Avoid broad refactors unless the user explicitly asks for them.

## Working agreements

- Start by inspecting the relevant files before editing.
- Make the smallest change that satisfies the request.
- Preserve existing user changes and unrelated work.
- If requirements are ambiguous and the choice materially changes the result, ask before implementing.
- Do not add production dependencies without explicit approval.
- Do not change public APIs, database schemas, authentication, permissions, or deployment behavior unless explicitly requested.

## Implementation rules

- Follow existing patterns in nearby files.
- Prefer boring, readable code over clever abstractions.
- Keep functions focused and easy to test.
- Add or update tests when behavior changes.
- Update documentation when public behavior, setup, or architecture changes.
- Use typed interfaces or schemas for data crossing module boundaries.

## Verification

Before finishing, run the narrowest relevant checks:

- For frontend changes: `[frontend test command]`
- For backend changes: `[backend test command]`
- For formatting/linting: `[lint command]`
- For type checks: `[typecheck command]`
- For docs-only changes: `[docs check command, if any]`

If a check cannot be run, report:

1. the exact command,
2. why it was not run,
3. what risk remains.

## Git and PR rules

- Never commit directly to `main`.
- Never force-push unless the user explicitly asks.
- Stage only files related to the task.
- Use clear commit messages.
- Summarize changed files and verification results in the final response.

## Security and privacy

- Never print secrets, tokens, private keys, or credentials.
- Do not log sensitive user, customer, financial, or authentication data.
- Do not weaken validation, authentication, authorization, rate limits, or audit logging.
- Treat destructive file operations, schema migrations, external API calls, and production-impacting changes as high-risk.

## Code Review Rules

When reviewing changes, flag:

- Missing tests for changed behavior.
- Business logic placed in the wrong architectural layer.
- Broad refactors bundled with small fixes.
- New dependencies without justification.
- Silent changes to public API behavior.
- Security-sensitive changes without validation or auditability.

For each issue, include:

- why it matters,
- exact file or module,
- safe fix path.

## Final response format

End with:

- Summary of what changed.
- Files changed.
- Verification run.
- Known risks or follow-ups.
```

---

## 4. 子系统覆盖模板：`AGENTS.override.md`

用于支付、权限、估值模型、数据管道等高风险目录。

```md
# AGENTS.override.md

## Scope

These rules apply to files under this directory.

## Local architecture

- This module owns [responsibility].
- Inputs come from [source].
- Outputs go to [destination].
- Critical invariants:
  - [invariant 1]
  - [invariant 2]

## Extra restrictions

- Do not change persisted data formats without explicit approval.
- Do not change calculations without adding before/after examples.
- Do not change external contracts without updating docs and tests.
- Preserve backward compatibility unless the user explicitly requests a breaking change.

## Required verification

- Run `[module-specific test command]`.
- Add regression tests for bug fixes.
- For financial or numerical logic, include sample input/output comparison.
```

---

## 5. Skill 模板：可复用工作流

适合放在 `.agents/skills/<skill-name>/SKILL.md`。

```md
---
name: architecture-review
description: Use this when asked to review architecture, large changes, module boundaries, technical design, or whether an implementation fits the repository structure.
---

# Architecture Review Skill

## Goal

Review whether the proposed or implemented change fits the repository architecture.

## Workflow

1. Inspect the relevant entry points and nearby modules.
2. Identify the intended layer for the change:
   - UI
   - API/controller
   - domain/service
   - persistence/data
   - infrastructure/integration
   - tests/docs
3. Check whether the change crosses architectural boundaries.
4. Look for unnecessary coupling, duplicated logic, missing validation, or hidden side effects.
5. Recommend the smallest safe change.

## Output

Return:

- Architecture fit: good / risky / incorrect
- Evidence: files or modules inspected
- Risks
- Recommended fix
- Required verification

## Rules

- Do not propose broad rewrites unless the current design blocks the requested outcome.
- Prefer incremental migration paths.
- Separate must-fix issues from nice-to-have improvements.
```

---

## 6. 从优秀项目里总结出来的提示词模式

### OpenHands 模式

- 用 `AGENTS.md` 写仓库级开发说明。
- 用 skills / microagents 放领域知识和任务流程。
- 常见内容：项目结构、测试命令、数据访问层规则、前端 hook 规则、PR 描述规则。

适合借鉴：

- 大型前后端混合项目。
- 希望 AI 按团队工程习惯改代码。

### Agent Zero 模式

- system prompt 拆成多个模块：
  - role
  - communication
  - solving
  - environment
  - tools
  - behavior
- 支持不同 agent profile 覆盖局部 prompt。

适合借鉴：

- 多角色 agent。
- 需要可维护、可替换的提示词系统。

### Dify 模式

- 项目本身是生产级 LLM workflow / RAG / agent 平台。
- 仓库里同时有 `AGENTS.md`、`CLAUDE.md`、skills。
- 重点不是写“人格”，而是写工程规范、测试规则、类型规则、目录边界。

适合借鉴：

- AI 平台、SaaS、复杂 monorepo。

### AutoGen / AutoGPT Code Ability 模式

- 多 agent 分工：
  - Product Owner
  - Architect
  - Developer
  - Reviewer
  - Deploy Agent
- 每个角色有自己的 system message 或 prompt。

适合借鉴：

- 从需求到架构再到代码实现的自动化流程。
- 复杂任务拆分。

### Helius Core AI 模式

- 三层结构：
  - Harness：不同运行环境的适配规则。
  - Skills：领域知识和流程。
  - Task：用户当次请求。

适合借鉴：

- 同一套 prompt 要适配 Codex、Claude Code、Cursor、API 等多个工具。

---

## 7. 为什么 Codex 有时不完全按 prompt 行事

这是正常现象，原因通常不是“模型坏了”，而是约束层级不够硬。

常见原因：

1. **提示词太长，被截断或被稀释**
   - Codex 对项目说明有大小限制。
   - 太多低优先级规则会淹没真正关键的规则。

2. **规则不可验证**
   - “写高质量代码”太抽象。
   - “修改 API 层后必须运行 `npm run test:api`”更有效。

3. **规则互相冲突**
   - 一边说“主动完成”，一边说“任何不确定都要问”。
   - 模型会在冲突中选择它认为更符合当前任务的路径。

4. **缺少硬约束**
   - prompt 是软约束。
   - 如果没有测试、lint、CI、hooks、权限审批，模型犯错后没人拦。

5. **上下文层级不对**
   - 当前聊天里的一次性要求，不一定适合写进长期规则。
   - 仓库规则、子目录规则、skill、hook、CI 应该各司其职。

6. **启动位置不对**
   - Codex 会按当前工作目录向上/向下发现 `AGENTS.md`。
   - 如果从错误目录启动，可能没有加载你以为它加载的文件。

7. **改了规则但没有重启 / 新会话**
   - 很多长期指令是在会话开始时读取。
   - 修改后应开启新任务或重启相关 Codex session。

---

## 8. 怎么提高 Codex 遵守率

### 8.1 把规则写成“触发条件 + 行为 + 验证”

不好：

```md
- Be careful with database changes.
```

更好：

```md
- If changing database schema files, stop and ask for approval before editing.
- After approved schema changes, update migration docs and run `[migration test command]`.
- In the final response, include old schema, new schema, and backward-compatibility impact.
```

### 8.2 把高风险规则放近一点

根目录 `AGENTS.md` 写通用规则。

高风险模块写自己的 `AGENTS.override.md`：

```text
services/payments/AGENTS.override.md
models/valuation/AGENTS.override.md
infra/AGENTS.override.md
```

越靠近工作目录的规则，越适合写具体约束。

### 8.3 用验收清单结束任务

在 `AGENTS.md` 里要求 Codex 最后必须输出：

```md
## Completion checklist

Before final response, confirm:

- [ ] Changed only files relevant to the request.
- [ ] Preserved public behavior unless requested.
- [ ] Added or updated tests if behavior changed.
- [ ] Ran relevant checks or explained why not.
- [ ] Listed known risks.
```

### 8.4 用 hooks / CI 做硬拦截

prompt 无法 100% 保证行为。要让它更可靠，需要硬机制：

- **CI**：不通过测试不能合并。
- **pre-commit**：格式、lint、类型检查。
- **hooks**：工具调用前后检查，比如禁止危险 shell 命令、检查是否遗漏测试。
- **权限审批**：删除文件、改依赖、联网、写外部系统前必须确认。
- **CODEOWNERS / PR review**：关键目录必须人工审核。

### 8.5 把“不要做什么”变成可执行规则

不好：

```md
- Don't over-engineer.
```

更好：

```md
- Do not introduce new abstraction layers unless at least three existing call sites need the same behavior.
- Do not rename public functions unless the user explicitly requests a rename.
- Do not modify unrelated files for formatting-only changes.
```

### 8.6 每次开始时让 Codex 自检加载了什么

你可以在重要任务开头这样说：

```text
Before editing, list the active instruction files you are using and summarize the rules that affect this task.
Then inspect relevant files and propose a short plan.
Do not edit until the plan is clear.
```

这不能保证 100%，但能显著减少“它根本没读到规则”的问题。

### 8.7 把复杂任务拆成模式

对高风险任务使用两阶段：

```text
Phase 1: read-only architecture investigation. Do not edit files.
Phase 2: after I approve the plan, implement the smallest safe change.
```

适合：

- 大重构
- 数据库迁移
- 权限 / 安全
- 财务计算
- 生产部署

---

## 9. 推荐落地方案

### 最小版

适合个人项目或小团队：

1. 根目录加 `AGENTS.md`。
2. 写清项目结构、禁止事项、测试命令。
3. 让 Codex final response 必须汇报验证。

### 标准版

适合正式团队：

1. 根目录 `AGENTS.md`。
2. 高风险目录加 `AGENTS.override.md`。
3. `.agents/skills/` 放 code review、architecture review、release checklist。
4. CI 强制 test / lint / typecheck。
5. PR 模板要求列出 AI 修改范围和验证结果。

### 企业版

适合多团队、多服务、生产系统：

1. 全局 Codex 指令：个人或组织默认规则。
2. 仓库级 `AGENTS.md`：项目工程规则。
3. 子目录覆盖：服务级规则。
4. Skills：标准化复杂流程。
5. Hooks：危险操作拦截、工具调用审计、停止前检查。
6. CI / CODEOWNERS / 分支保护：最终硬约束。
7. 定期 review prompt：删除过期规则，压缩到关键规则。

---

## 10. 用于当前项目的精简 `AGENTS.md` 示例

如果这是估值 / 财务分析项目，可以这样起步：

```md
# AGENTS.md

## Project context

This repository contains valuation, financial analysis, and investment research materials.

## Critical rules

- Preserve source figures exactly unless the user explicitly asks to adjust them.
- Do not invent financial data, transaction values, company metrics, dates, or assumptions.
- If a number comes from a file, cite the file and location when possible.
- If a calculation changes, show the formula, old value, new value, and reason.
- Keep assumptions separate from facts.
- For market/current/company facts that may have changed, verify with current sources before answering.

## File handling

- Do not overwrite original source files.
- Create revised outputs as new files unless the user explicitly asks to edit in place.
- Keep filenames descriptive and dated when producing reports.

## Analysis standards

- Separate:
  - source data,
  - assumptions,
  - calculations,
  - conclusions.
- Flag missing data instead of guessing.
- Use tables for comparable companies, scenarios, and sensitivity analysis.

## Verification

- Check formulas for consistency.
- Cross-check totals and subtotals.
- Report any unresolved data gaps.

## Final response

Include:

- What changed or was created.
- Key assumptions.
- Verification performed.
- Open questions or risks.
```

---

## 11. 结论

有办法让 Codex 更稳定，但不要指望只靠一段 prompt。

更可靠的做法是：

```text
清晰 AGENTS.md
  + 子目录覆盖
  + 可复用 skills
  + 明确验收清单
  + hooks / CI / tests 硬约束
  + 人工审批高风险动作
```

prompt 负责“告诉 Codex 正确方向”。

测试、hooks、CI 和权限负责“它偏离时把它拦住”。

