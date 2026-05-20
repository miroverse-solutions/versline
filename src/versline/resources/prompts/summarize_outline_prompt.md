# Detailed Outline Prompt

You are an expert content analyst. Your task is to create a **detailed hierarchical outline** of the provided text.

Guidelines:
* Use Markdown heading hierarchy (##, ###, ####) to represent the structure
* Include ALL key topics, subtopics, and important points from the text
* Under each heading, add concise bullet points capturing key concepts, arguments, and details
* Preserve the logical flow and order of the original
* Be comprehensive — this is a reference outline, not a brief summary
* {language_instruction}
* {terms_instruction}
* Output ONLY the outline in valid Markdown, ready to be concatenated with adjacent sections
* Do not add preamble, closing remarks, or wrapping code fences

Text to outline:

"""
{text}
"""
