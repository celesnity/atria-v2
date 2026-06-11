Convert a markdown file to a styled PDF using WeasyPrint. Embedded images referenced with relative paths in the markdown resolve against the markdown file's directory, so a `report.md` next to a `chart.png` can use `![](./chart.png)` and the image will appear in the PDF.

A default stylesheet ships with Atria (clean typography, table borders, A4 page margins). Pass `css_path` to override.

Both paths must be absolute. `pdf_path` must end in `.pdf`.
