<!--
name: 'Tool Description: PresentPlan'
description: Present a plan file for user approval
version: 1.0.0
-->

Present an existing plan file for user approval.

## How This Tool Works

- Takes the plan file path as a parameter
- Reads the plan content from the file
- Displays the plan to the user and opens an approval dialog
- Returns the user's decision: approve, modify, or reject

## When to Use This Tool

After a plan has been prepared and its path is known, call this tool to get user
sign-off before implementation.

## Flow

1. Prepare a plan file path
2. Call present_plan(plan_file_path="...") to show the plan
3. Handle the result:
   - **approved**: Proceed with implementation
   - **modify**: Revise the plan with the feedback, then call present_plan again
   - **rejected**: Ask the user how to proceed

## Important

- Do NOT use ask_user to ask "Is this plan okay?" — that's what this tool does
- The plan file must exist and be non-empty before calling this tool
