# Deep Research

You have access to a `deep_research` tool that conducts comprehensive, multi-source research on complex topics.

## Flow (important — do NOT skip steps)

1. Call `deep_research(topic, depth)`.
2. The tool generates a MECE taxonomy and **completely stops** — it will NOT proceed until the user reviews it in the UI.
3. The UI presents the user with the generated taxonomy. The user can:
   - Type modification instructions in the **Request changes** box (translated, restructured, etc.)
   - Click **Regenerate** to fully rebuild the taxonomy with a new prompt
   - Click **Start Research** to accept and start the pipeline
4. Once the user accepts, the research runs **as a background task**. The tool returns immediately.
5. **STOP HERE.** Do NOT call any other tools. Do NOT search the web. Do NOT do anything else. The loop ends automatically.
6. When complete, the full report is saved as a `.md` file in the working directory.

The loop breaks automatically when `deep_research` returns — you cannot and should not take further actions.

## When to use deep_research

- In-depth analysis of a broad topic (market analysis, technology overview, scientific field survey)
- Comparative research across multiple dimensions
- Research reports, white papers, or comprehensive summaries
- Multi-faceted questions requiring several angles simultaneously
- Historical + current + future trend analysis
- Phrases like: "nghiên cứu sâu", "báo cáo chi tiết", "phân tích toàn diện", "deep research", "research report", "comprehensive analysis", "tổng quan về"

## When NOT to use deep_research

- Simple factual lookups → use `web_search`
- Single-source questions: "what is X", "how do I Y"
- Coding tasks, debugging, file operations
- Quick questions expecting a fast answer

## Depth levels

- `"shallow"` — quick overview, fewer queries
- `"standard"` — balanced coverage (default)
- `"deep"` — comprehensive, more queries

## After calling deep_research

Tell the user concisely that the taxonomy is being generated and they will see a review panel shortly. Example:

> "Đang tạo taxonomy cho **[topic]** — bạn sẽ thấy bảng review xuất hiện ngay để xem xét và chỉnh sửa trước khi bắt đầu nghiên cứu."

Do not fabricate or guess results — the research pipeline produces the actual content.
