Render a single chart from a tabular dataset (CSV or Excel) to a PNG file using matplotlib. Use this for the `analyze` skill or any time you need a chart on disk that you (or the user) will look at.

The tool picks a fixed style — 10x6 inches, dpi 150, default palette. You do not control styling; you only choose what to plot.

Pick `chart_type` to match the shape of the data:
- `bar` — one categorical x with one or more numeric y (set `agg` to sum/mean/count when x has duplicates)
- `line` — datetime or ordered x with one or more numeric y
- `scatter` — two numeric columns
- `hist` — distribution of a single numeric column (x is ignored)
- `pie` — share of one numeric column across a categorical x (uses agg=sum unless overridden)

All paths must be absolute. `out_path` must end in `.png`. Datasets up to 10 MB and 100 000 rows are accepted.
