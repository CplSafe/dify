# AGENTS.md

## Project Overview

Dify is an open-source platform for developing LLM applications with an intuitive interface combining agentic AI workflows, RAG pipelines, agent capabilities, and model management.

The codebase is split into:

- **Backend API** (`/api`): Python Flask application organized with Domain-Driven Design
- **Frontend Web** (`/web`): Next.js application using TypeScript and React
- **Docker deployment** (`/docker`): Containerized deployment configurations

## Backend Workflow

- Read `api/AGENTS.md` for details
- Run backend CLI commands through `uv run --project api <command>`.
- Integration tests are CI-only and are not expected to run in the local environment.

## Frontend Workflow

- Read `web/AGENTS.md` for details

## Testing & Quality Practices

- Follow TDD: red → green → refactor.
- Use `pytest` for backend tests with Arrange-Act-Assert structure.
- Enforce strong typing; avoid `Any` and prefer explicit type annotations.
- Write self-documenting code; only add comments that explain intent.

## Language Style

- **Python**: Keep type hints on functions and attributes, and implement relevant special methods (e.g., `__repr__`, `__str__`). Prefer `TypedDict` over `dict` or `Mapping` for type safety and better code documentation.
- **TypeScript**: Use the strict config, rely on ESLint (`pnpm lint:fix` preferred) plus `pnpm type-check:tsgo`, and avoid `any` types.

## General Practices

- Prefer editing existing files; add new documentation only when requested.
- Inject dependencies through constructors and preserve clean architecture boundaries.
- Handle errors with domain-specific exceptions at the correct layer.

## Project Conventions

- Backend architecture adheres to DDD and Clean Architecture principles.
- Async work runs through Celery with Redis as the broker.
- Frontend user-facing strings must use `web/i18n/en-US/`; avoid hardcoded text.


<claude-mem-context>
# Memory Context

# [dify] recent context, 2026-04-25 7:47pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 41 obs (15,631t read) | 649,726t work | 98% savings

### Apr 18, 2026
28 4:57p 🔵 Code Review: Social Publish Frontend Integration (Dify)
31 4:58p 🔵 Dify Frontend Code Review Skill Structure
33 " 🔵 Social Publish P1 Frontend Plan: Architecture and API Contracts
35 4:59p 🔵 Backend P1 Commit ee32eb349: Social Publish Account Management API
88 7:45p 🔵 Social Publish Backend P2: Security & Correctness Review Findings
90 " 🔵 backend-code-review skill structure in dify project
92 7:46p 🔵 Dify P2 Social Publish Backend: Full 12-Question Security & Correctness Review Initiated
94 " 🔵 P2 Design Doc: Accepted Tech Debt and Security Model Documented
96 7:47p 🔵 Controller _to_http_error: RuntimeError from missing SAU_INTERNAL_TOKEN escapes mapping
100 8:45p 🔵 Social Publish Backend P3 Security and Correctness Review Findings
102 " 🔵 Social Publish P3 Staged Files Inventory Confirmed
### Apr 25, 2026
351 6:18p 🔵 Dify Web: Code Review Against Base Commit a2424e141
352 " 🔵 Dify Full Change Inventory: 26 Files, 2629 Insertions Since a2424e141
354 6:19p 🔵 Dify Project: Backend Code Review Skill and AGENTS.md Standards Loaded
356 " 🔵 Code Review Request: Git Diff Against Base Commit a2424e141
358 6:20p 🔵 Canvas Runtime Feature: canvas_id Usage Across API and Web
360 6:21p 🔵 WorkflowRerunService: Validation Guards for Run and Workflow Loading
362 " 🔵 UserCanvasService: Canvas Creation Validation Logic
363 " 🔵 Dify Web Canvas Runtime Feature Branch: Code Review Against Base Commit a2424e141
368 6:41p 🔵 Dify Canvas Runtime Feature Branch: Code Review Against Base Commit c3d437272
370 " 🔵 Canvas Runtime Feature Branch: Full Diff Stat Against Base c3d437272
373 6:42p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit c3d437272
375 6:43p 🔵 Dify Canvas Runtime: RuntimePauseActions Component Full Implementation
377 " 🔵 Dify Canvas Runtime Backend: WorkflowPauseEntity and enqueue_resume Architecture
379 6:44p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit c3d437272
381 7:03p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 25915f425
383 " 🔵 Dify Project: Backend Code Review Skill Structure and Checklist Rules
385 " 🔵 Dify Project: Frontend Code Review Skill Structure
387 7:04p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 25915f425
390 7:05p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 25915f425
392 7:06p 🔵 WorkflowPause Resume Flow: create_workflow_pause and resumed_at Field Locations Confirmed
397 7:07p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 25915f425
399 7:08p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 25915f425
401 7:38p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 379e81c23
403 " 🔵 Dify Project: Backend and Frontend Code Review SKILL.md Structures Confirmed
405 7:39p 🔵 Dify Canvas Runtime Feature Branch: Full Diff Against Base Commit 379e81c23
407 " 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 379e81c23
409 7:40p 🔵 HumanInputService: submit_form_by_token and enqueue_resume Full Implementation
411 7:41p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 379e81c23
412 " 🔵 Dify Canvas Runtime: resume_app_execution Celery Task and Full Pause/Resume Code Path Map
415 7:45p 🔵 Dify Canvas Runtime Feature Branch: Code Review Request Against Base Commit 95c98c4d3

Access 650k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>