# Classify-First Todo Workflow — Design

Date: 2026-07-13
Status: Approved (design), pending implementation plan

## Goal

Make the main agent classify every incoming request as single-step or
multi-step before acting. When a request is multi-step, the agent must emit a
brief one-line preamble, create a full todo list with `write_todos` **before**
taking any action, and then execute strictly in todo order.

## Definitions

- **Multi-step** = a request requiring **2 or more distinct actions / tool-uses**.
  Examples: read + edit, an edit spanning two files, a build/test/fix cycle,
  feature work with several steps.
- **Single-step** = a request answerable in one shot: a plain answer, a greeting,
  a question, or a one-shot single-file edit. No todo list, no preamble.

## Behavior

1. **Classify first.** At the start of every request, decide single-step vs
   multi-step using the 2+-distinct-actions threshold.
2. **If multi-step:**
   - Emit one brief line signaling the classification (e.g. "This is
     multi-step — planning it out:").
   - Call `write_todos` to create the complete todo list before any
     state-changing action.
   - Execute strictly in todo order, keeping the existing discipline: exactly
     one todo `in_progress` at a time; `update_todo(id, status="in_progress")`
     on start; `complete_todo(id)` when done; never skip todos; `clear_todos`
     if the user abandons the work.
3. **If single-step:** do it directly — no todo, no preamble.

## Files Changed

1. `minder/core/agents/prompts/templates/system/main/main-task-tracking.md`
   - Add a "Classify First" instruction at the top of the workflow.
   - Change the threshold wording from "multi-file changes" to
     "2+ distinct actions" in the intro line and the "When to Use" list.
   - Add the one-line-preamble-then-`write_todos` requirement.
   - Bump the section `version` in the header comment.
2. `minder/core/agents/prompts/templates/system/main/main-interaction-pattern.md`
   - Add a one-line pointer in step 1 ("Understand first") so understanding
     flows into classification, cross-referencing task tracking.

## Non-Goals / Out of Scope

- No changes to tool logic. `write_todos`, `update_todo`, `complete_todo`,
  and `clear_todos` already exist and are unchanged.
- No new prompt section file — the rule lives in the existing task-tracking
  section to keep one source of truth.
- No changes to the planning agent or subagents.

## Success Criteria

- The composed main system prompt instructs the agent to classify first and to
  create todos before executing multi-step work.
- Threshold is stated as "2+ distinct actions" consistently in the section.
- Single-step requests remain todo-free and preamble-free.
