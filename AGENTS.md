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

# [dify] recent context, 2026-06-09 10:50am GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (18,405t read) | 1,120,338t work | 98% savings

### Apr 29, 2026
821 11:31a 🔵 Asset Library Frontend Task 3-20 Kickoff: Session Context and Constraints
823 11:33a ✅ Asset Library i18n JSON Files: Flat Key Format Adopted
826 11:36a 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Context and Constraints
828 11:37a 🔵 Asset Library Frontend Task 3-20 Session Kickoff: Context and Constraints
830 11:39a 🔵 Asset Library Frontend Task Kickoff: Session Context and Task 3-20 Plan
832 11:40a 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Context and Constraints
835 11:45a 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Context and Constraints
838 " 🔵 Asset Library Frontend Task 3-20 Kickoff: Session Context and Constraints
845 11:49a 🔵 Asset Library Frontend Task 3-20 Kickoff: Session Context and Constraints
847 " 🔵 Asset Library Frontend Task 3-20 Session Kickoff: Full Context and Constraints
849 11:51a 🔵 Asset Tabs Test Fails: Implementation File Missing (TDD Red Phase)
851 " 🔵 Asset Library Frontend Task 3-20 Session Kickoff Context
853 11:52a 🟣 AssetFilterBar TDD Test Suite Written
856 11:53a 🔵 Asset Library Frontend Task 3-20 Session Kickoff Context
858 " 🔴 Asset Filter Bar: react/set-state-in-effect Lint Error
860 " 🔴 Asset Filter Bar: Fixed react/set-state-in-effect via Ref Guard Pattern
863 11:58a 🔵 Asset Library Frontend Task 3-20 Session Kickoff Context
866 " 🟣 Asset Library AssetFilterBar Component Committed
868 11:59a 🔵 Asset Library Frontend Task Kickoff: Task 3-20 Session Context
872 12:00p 🟣 Asset Library Pagination Component: Tests Passing
875 " 🔵 Asset Library Frontend Task 3-20 Session Kickoff Context
877 12:01p 🟣 Asset Library: AssetCard and AssetGrid Components Created
883 12:03p 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Handoff Context
887 " 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Implementation Starting
892 12:06p 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Implementation Starting
894 12:07p 🟣 UploadDropzone Test Suite Written: 7 Comprehensive Test Cases
897 2:31p 🔵 Asset Library Frontend Session Kickoff: Task 3-20 Context and Constraints
899 " 🔵 Celery SSL Unit Test: One Failure Detected
901 2:32p 🔵 Celery SSL Test Failure: PAYMENT_ORDER_EXPIRY_TASK_INTERVAL Not Mocked
905 " ⚖️ Asset Library Frontend: Session Restart with Same Task 3-20 Scope
906 2:33p 🟣 Added Celery Beat Test for Creator Task Timeout Schedule Registration
911 2:34p ⚖️ Asset Library Frontend: Third Session Restart, Tasks 3-20 Still Pending
912 2:35p 🔴 Celery SSL Tests Now All Pass After Adding Missing Mock Config Fields
915 2:36p 🔵 Asset Library Frontend: Fourth Session Start, Tasks 3-20 Still Not Begun
914 " 🟣 Creator Task Auto-Timeout + Configurable Concurrency Limit
920 2:39p 🔵 Dify API Backend Coding Standards Documented in api/AGENTS.md
923 2:41p 🔄 Workflow Persistence Layer Tests Refactored: Single Combined Billing Deduction
930 2:47p 🔵 Asset Library Frontend Plan Tasks 3-8: Full Code Specifications Confirmed
933 2:53p 🔵 Git Remote Push Status Check: dify-zd Repository
935 2:54p 🔵 Git Status: Large Number of Uncommitted Changes in dify-zd Repository
937 2:55p 🟣 LLM Node Billing Extraction: Per-Node Price Support Added to WorkflowPersistenceLayer
938 " 🟣 Creator Task: Configurable Concurrent Limit + Auto-Timeout via Celery Beat
939 " 🔴 BillingRecord.to_dict() Naive UTC Timestamp Bug: CST 8-Hour Shift Fixed
944 " 🔵 Git Diff Stat: 8 Files Changed, 421 Insertions, 138 Deletions — Pre-Commit Summary
946 2:56p 🟣 Git Selective Staging: Narrow Commit for Creator Task + Billing Fixes
### May 25, 2026
2084 9:43a 🔵 微信小程序真机白屏卡顿根因诊断请求
2086 9:44a 🔵 miniprogram-hsbst 真机白屏根因诊断 — setData + wx:for 全量 diff
2088 9:45a 🔵 miniprogram-hsbst 真机白屏根因诊断 — setData + wx:for 全量 diff
2090 9:48a 🔵 miniprogram-hsbst 真机白屏根因诊断 — setData + wx:for 全量 diff
### Jun 9, 2026
4562 10:49a 🔵 快手自运营项目本地与远程仓库一致性检查请求

Access 1120k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>