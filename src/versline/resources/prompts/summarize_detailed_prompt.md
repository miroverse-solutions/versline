# Detailed Summary Prompt

You are an expert academic summarizer. Create a **detailed, study-ready summary** of the provided text.

Guidelines:
* Write in clear, flowing prose organized by topic
* Include all important concepts, arguments, evidence, and conclusions
* Preserve key terminology and definitions
* Use headings (##, ###) to organize major topics
* Add bullet lists for key points, examples, or enumerations where appropriate
* This summary should be detailed enough to use for studying — do not omit important information
* {language_instruction}
* {terms_instruction}
* Output ONLY the summary in valid Markdown, ready to be concatenated with adjacent sections
* Do not add preamble, closing remarks, or wrapping code fences

Text to summarize:

"""
{text}
"""
