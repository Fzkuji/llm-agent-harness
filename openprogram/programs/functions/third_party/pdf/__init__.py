"""third_party/pdf — LLM-driven PDF extraction agentic functions.

Grouping folder for PDF agentic functions and their shared helpers.
Discovered recursively by the function loader (see
``openprogram.programs.functions.iter_function_files``).

* ``extract_pdf_tables``  — tables out of any PDF as Markdown.
* ``extract_pdf_figures`` — figures cropped out of any PDF as PNGs.
* ``_layout``             — private helper: positioned-text rendering.
"""
