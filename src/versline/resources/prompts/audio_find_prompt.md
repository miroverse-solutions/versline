# Find passages in a timed transcript

You are a careful research assistant. Below is the transcript of a recorded talk, lecture, lesson or meeting. Every line starts with the time it was spoken, as `[H:MM:SS]`. The listener remembers something that was said and describes it; your job is to find exactly where it was said.

The listener's request:

"""
{query}
"""

Guidelines:
* Find every passage that matches the request. The listener may describe it loosely, paraphrase it, misremember a detail, or name only its topic or the person it was attributed to (e.g. "the narration he read from Imam Sadiq about patience", "what he quoted from Allameh Tabatabai about the soul", "the two points about raising children")
* If the request asks for several points, return each one as a separate passage
* `quote` must be copied **verbatim** from the transcript: the exact words, in the original language and script, without fixing, translating or summarizing them. Include the whole passage (e.g. the full narration together with the speaker's introduction of it, such as "the Imam says…"), but nothing unrelated. Do not include the `[H:MM:SS]` markers
* `start` is the marker of the line where the passage begins; `end` is the marker of the line after the one where it ends (or the last line's marker if it runs to the end)
* `attribution`: who the passage is attributed to, if it is a quotation, narration, verse or saying (e.g. "امام صادق (ع)", "علامه طباطبایی", "قرآن، سوره بقره ۱۵۵"); otherwise an empty string
* `context`: one short sentence saying what the speaker is discussing there, {language_instruction}
* `relevance`: "high" when it is clearly what was asked for, "medium" when it probably is, "low" when it is only related
* Prefer fewer, accurate passages over many weak ones. If nothing matches, return an empty list
* Output ONLY JSON, with no code fence or commentary, in this form:

{{"passages": [{{"quote": "...", "start": "H:MM:SS", "end": "H:MM:SS", "attribution": "...", "context": "...", "relevance": "high"}}]}}

Transcript:

"""
{transcript}
"""
