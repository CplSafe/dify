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

# [dify] recent context, 2026-04-18 8:45pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 9 obs (4,457t read) | 118,779t work | 96% savings

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

Access 119k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>