# Slide Outline Prompt

You are an expert presentation designer. Create a **complete slide outline** for a professional presentation based on the provided text.

Guidelines:
* Use ## for section/chapter dividers (visible section headers in the deck)
* Use ### for individual slide titles
* Under each slide title, list 3–5 concise bullet points — key messages, not full sentences
* Keep bullets short and impactful, suitable for projected slides
* Cover all major topics from the source material in a logical sequence
* {language_instruction}
* {terms_instruction}
* Output ONLY the slide outline in valid Markdown, ready to be concatenated with adjacent sections
* Do not add preamble, closing remarks, or wrapping code fences

Text to convert to slide outline:

"""
{text}
"""
