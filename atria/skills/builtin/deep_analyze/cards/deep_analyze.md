Start a background data-analysis pipeline on a CSV or XLSX file. Returns a
`job_id` immediately; poll with `get_analyze_status`. The pipeline loads the
file into SQLite, plans sub-tables and charts, renders charts, derives
vision-based insights per chart, and produces a PDF report. Each chart and the
final PDF are streamed to the chat as artifacts.

Use when the user asks to "analyze", "summarize", or "profile" a tabular data
file. Prefer this over ad-hoc bash + python.
