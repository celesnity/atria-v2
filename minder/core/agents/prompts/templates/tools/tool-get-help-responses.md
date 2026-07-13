<!--
name: 'Tool Description: get_help_responses'
description: Collect volunteers' answers to a help request
version: 4.0.0
-->

Collect the answers to a `request_help` request by its `request_id`.

## Usage notes

- Pass the `request_id` returned by `request_help` (not a tool_call_id).
- Returns each volunteer's response from the response board, the bid roster (which
  helpers volunteered or declined, and why), and a digest of the notes helpers
  wrote to the shared blackboard.
- If no helper volunteered, the response set is empty — plan, run code yourself, or
  re-request differently.
