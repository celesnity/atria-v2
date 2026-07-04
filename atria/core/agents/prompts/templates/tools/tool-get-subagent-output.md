<!--
name: 'Tool Description: get_subagent_output'
description: Collect the results of a subagent job
version: 3.0.0
-->

Collect the results of a `subagent` job by its `job_id`.

## Usage notes

- Pass the `job_id` returned by the `subagent` tool (not a tool_call_id).
- Returns each task's status (pending, claimed, done, failed) plus a digest of the
  notes the subagents wrote to the shared blackboard.
- By default blocks until every task finishes. Use `block=false` for a
  non-blocking status poll to see whether tasks are still running.
