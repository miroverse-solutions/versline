# Document page reading prompt (Telegram archive, --ocr)

This image is one page of a document (a scanned book or booklet page, a handout, a photographed sheet, a slide). Its text will be stored as a Markdown note in an Obsidian vault, so it must be complete and exact.

* Transcribe ALL of the text on the page faithfully, in its original language, spelling and reading order (right-to-left for Persian and Arabic). Do not translate, correct, summarize or modernize anything.
* Keep Quranic verses, narrations, quotations, footnote numbers, references and page headers/footers exactly as written. Keep Arabic diacritics where they are printed.
* Mark words you cannot read as […].
* Use Markdown only for structure that is visible on the page: `#`/`##` for headings, lists for lists, Markdown tables for tables, `>` for set-off quotations. Put footnotes at the end of the page, each on its own line, with its number.
* If the page has a figure, chart or diagram, describe it in one short line in square brackets, e.g. [نمودار: …].
* If the page has no text at all, output exactly: [صفحه بدون متن]
* Output ONLY the page content, with no preamble or closing remarks.
