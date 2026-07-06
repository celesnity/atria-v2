"""Built-in tool schemas: web tools.

Auto-grouped from the former monolithic `definitions.py`. Each module exports a
`SCHEMAS` list of OpenAI-style function tool schema dicts.
"""

from __future__ import annotations

from typing import Any

from atria.core.agents.prompts.loader import load_tool_description

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": load_tool_description("fetch_url"),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (must start with http:// or https://)",
                    },
                    "extract_text": {
                        "type": "boolean",
                        "description": "Whether to extract text from HTML (default: true)",
                        "default": True,
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum content length in characters (default: 50000)",
                        "default": 50000,
                    },
                    "deep_crawl": {
                        "type": "boolean",
                        "description": "Follow links and crawl multiple pages starting from the seed URL.",
                        "default": False,
                    },
                    "crawl_strategy": {
                        "type": "string",
                        "enum": ["bfs", "dfs", "best_first"],
                        "description": "Traversal strategy when deep_crawl is true. best_first (default) prioritizes relevance, bfs covers broadly, dfs follows a single branch.",
                        "default": "best_first",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth (beyond the seed page) to crawl when deep_crawl is enabled. Depth 0 is the starting page. Defaults to 1.",
                        "default": 1,
                    },
                    "include_external": {
                        "type": "boolean",
                        "description": "Allow crawling links that leave the starting domain when deep_crawl is enabled.",
                        "default": False,
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "Optional cap on the total number of pages to crawl when deep_crawl is enabled.",
                    },
                    "allowed_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional allow-list of domains to keep while deep crawling.",
                    },
                    "blocked_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional block-list of domains to skip while deep crawling.",
                    },
                    "url_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional glob-style URL patterns the crawler must match (e.g., '*docs*').",
                    },
                    "stream": {
                        "type": "boolean",
                        "description": "When true (and deep_crawl is enabled) stream pages as they are discovered before aggregation.",
                        "default": False,
                    },
                },
                "required": ["url"],
            },
        },
    },
    # ===== Web Search Tool =====
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": load_tool_description("web_search"),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to use. Be specific and include relevant keywords.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10,
                    },
                    "allowed_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only include search results from these domains (e.g., ['docs.python.org', 'stackoverflow.com'])",
                    },
                    "blocked_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Never include search results from these domains",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # ===== Send Image Tool (web UI) =====
    {
        "type": "function",
        "function": {
            "name": "send_image",
            "description": (
                "Send an image to the web UI chat as a standalone image bubble. "
                "Provide either a local server-side absolute path OR a remote http(s) URL — "
                "never both, never neither. Use for screenshots, generated charts, diagrams, "
                "or any visual the user should see. Only works in the web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute server-side path to a local image file "
                            "(PNG/JPEG/GIF/WebP/SVG, ≤10 MB)."
                        ),
                    },
                    "url": {
                        "type": "string",
                        "description": "Public http(s) URL of a remote image.",
                    },
                    "caption": {
                        "type": "string",
                        "description": "Optional caption shown below the image.",
                    },
                },
                "required": [],
            },
        },
    },
    # ===== Send Editable Table Tool (web UI) =====
    {
        "type": "function",
        "function": {
            "name": "send_editable_table",
            "description": (
                "Send a module dataset to the web UI as an INTERACTIVE, EDITABLE table. "
                "Use this (instead of send_data) when the user wants to view AND change "
                "data — edit cells, add or delete rows — and save it. The grid is bound to "
                "the module's CSV; when the user clicks Save, the edits are written back to "
                "the dataset and the module/dashboard refreshes. Provide `module` (the data "
                "module name) and `file` (the dataset path relative to the module's data/ "
                "dir, e.g. 'worldcups.csv'). Only works in the web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "Name of the data module that owns the dataset.",
                    },
                    "file": {
                        "type": "string",
                        "description": (
                            "Dataset path relative to the module's data/ dir "
                            "(e.g. 'worldcups.csv' or 'sub/dir/x.csv'). Must be a .csv."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Title shown above the editable table.",
                    },
                    "editable_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional whitelist of editable column names. Omit to make "
                            "every column editable."
                        ),
                    },
                },
                "required": ["module", "file", "title"],
            },
        },
    },
    # ===== Send Table Tool (web UI, read-only) =====
    {
        "type": "function",
        "function": {
            "name": "send_table",
            "description": (
                "Send a READ-ONLY result table to the web UI chat as an interactive "
                "table + chart. Provide `file` (absolute path to a CSV the analysis "
                "wrote — e.g. the `result_table` from data_copilot analyze — or a name "
                "relative to the session's data_copilot data/ dir) and a `title`. "
                "Optionally pass `suggestions` (chart specs) so the UI renders an "
                "interactive chart. If analyze already returned `suggestions`, forward "
                "them verbatim. Otherwise build them yourself — do NOT guess column "
                "names or reuse the same column for x and y.\n"
                "\n"
                "CHOOSING FEATURES (this matters — wrong x/y renders an empty or "
                "meaningless chart):\n"
                "- First inspect the CSV header + a few rows. `x` and `y` MUST be exact "
                "column names that exist in the data. `y` columns must hold numbers "
                "(measures like total_sales, quantity, profit); `x` is usually a "
                "dimension (a category, group, or date).\n"
                "- Pick charts that answer a real question and match the data shape. "
                "Emit 2–4 focused suggestions, not every column combination.\n"
                "\n"
                "PER CHART TYPE:\n"
                "- bar: x = a categorical dimension with a manageable number of groups "
                "(e.g. region, category, channel); y = one or more numeric measures. "
                "Rows are shown/grouped per x value.\n"
                "- line / area: x = a date or naturally ordered column; y = numeric "
                "measure(s) trended over that order. Use for time series.\n"
                "- pie / doughnut: x = a categorical column with FEW distinct values "
                "(≤ ~8, e.g. region, category); y = exactly ONE numeric measure. The UI "
                "auto-sums that measure per category and shows each category's share, so "
                "never put a high-cardinality or numeric column in x here.\n"
                "- scatter: BOTH x and y MUST be numeric measure columns, to show the "
                "relationship between them (e.g. x=quantity, y=total_sales, or "
                "x=unit_price, y=profit_margin). Never use a text/category column as the "
                "scatter x — the plot comes out empty.\n"
                "- radar: x = a categorical column with a few values; y = one or more "
                "numeric measures on comparable scales; set `normalized: true` when the "
                "measures span very different ranges.\n"
                "- combo: x = category or date; y = 2+ measures with a `combo` mapping "
                "(e.g. one series 'bar', another 'line'); put a very-different-scale "
                "measure on `secondaryAxis`.\n"
                "\n"
                "Other per-suggestion fields: `title`, `description` (one line under the "
                "chart), `labels` (series/column → display name), `units` (series → unit "
                "e.g. '%', 'USD'). Whenever the data is chartable (a dimension plus one "
                "or more numeric columns), include at least one suggestion so the user "
                "gets a chart, not just a table. This tool is NOT editable and only "
                "works in the web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": (
                            "CSV to display. May be: a name under the session "
                            "data_copilot data/ dir (e.g. 'result.csv'), any path "
                            "inside the workspace (e.g. 'modules/data_copilot/data/"
                            "sales_data.csv'), or an absolute path within the "
                            "workspace. Pass `module` instead for a module dataset."
                        ),
                    },
                    "module": {
                        "type": "string",
                        "description": (
                            "Optional module name to read the CSV from that module's "
                            "data/ dir (modules/<module>/data/<file>). When set, `file` "
                            "is relative to that module's data/ dir."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Title shown above the table.",
                    },
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "chart_type": {
                                    "type": "string",
                                    "enum": [
                                        "bar", "line", "area", "pie", "doughnut",
                                        "scatter", "combo", "radar",
                                    ],
                                    "description": (
                                        "Match to the data: bar=compare by category, "
                                        "line/area=trend over date/order, "
                                        "pie/doughnut=share of ONE measure across few "
                                        "categories, scatter=relationship between TWO "
                                        "numeric measures, radar=multi-measure by "
                                        "category, combo=mixed bar+line."
                                    ),
                                },
                                "x": {
                                    "type": "string",
                                    "description": (
                                        "Exact column name for the x axis / category. A "
                                        "dimension (category/group/date) for most charts; "
                                        "MUST be a numeric column for scatter."
                                    ),
                                },
                                "y": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Exact numeric column name(s) for the value axis. "
                                        "Use exactly one for pie/doughnut/scatter; may use "
                                        "several for bar/line/area/combo/radar. Never "
                                        "equal to x."
                                    ),
                                },
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "labels": {"type": "object"},
                                "units": {"type": "object"},
                                "combo": {"type": "object"},
                                "secondaryAxis": {
                                    "type": "array", "items": {"type": "string"},
                                },
                                "normalized": {"type": "boolean"},
                            },
                            "required": ["chart_type", "x", "y"],
                        },
                        "description": (
                            "Optional chart specs to render an interactive chart above "
                            "the table. Forward the `suggestions` from analyze verbatim "
                            "to keep their rich fields (description, labels, units, "
                            "combo, secondaryAxis, normalized)."
                        ),
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Optional cap on rows sent to the UI.",
                    },
                },
                "required": ["file", "title"],
            },
        },
    },
    # ===== Send Report Tool (web UI, read-only) =====
    {
        "type": "function",
        "function": {
            "name": "send_report",
            "description": (
                "Send a data_copilot run's generated report (markdown) to the web UI "
                "chat as a report bubble. Use this after `resume` returns "
                "{status: 'done', report: ...} to surface the finished report to the "
                "user. Provide `run_dir` (the run directory returned by data_copilot "
                "run/resume, e.g. 'runs/run-2026...'), relative to the session's "
                "data_copilot dir. Only works in the web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "run_dir": {
                        "type": "string",
                        "description": (
                            "Run directory (relative to the session's data_copilot "
                            "dir) whose report.md should be sent, e.g. 'runs/run-x'."
                        ),
                    },
                },
                "required": ["run_dir"],
            },
        },
    },
    # Skill-owned schemas live in their skill folders and are merged in via
    # ToolSchemaBuilder(extra_schemas=...).
    {
        "type": "function",
        "function": {
            "name": "md_to_pdf",
            "description": load_tool_description("md-to-pdf"),
            "parameters": {
                "type": "object",
                "properties": {
                    "md_path": {"type": "string"},
                    "pdf_path": {"type": "string"},
                },
                "required": ["md_path", "pdf_path"],
            },
        },
    },
]
