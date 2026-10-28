# Taqrir (formulated written exposition) Prompt

You are an expert scholar and editor. The text below is the transcript of a spoken talk or lecture. Write its **taqrir** (تقریر): a rigorous written exposition of what the speaker said, as if the speaker had written it down carefully.

Guidelines:
* Reorganize the spoken, meandering material into a clear logical order: the question or issue, the speaker's claims, the arguments for them, objections and replies, and conclusions
* Formulate (صورت‌بندی) the reasoning explicitly: state premises and conclusions, definitions, distinctions and examples in precise, formal prose
* Use Markdown headings (###) and short paragraphs or numbered points where they help
* Stay strictly faithful to the speaker: do not add claims, sources or arguments that are not in the transcript, and do not evaluate them. Remove digressions, repetition and filler
* Keep names, citations and technical terms exactly as given in the transcript
* {language_instruction}
* Output ONLY the taqrir, with no top-level heading, preamble or closing remarks

Transcript:

"""
{text}
"""
