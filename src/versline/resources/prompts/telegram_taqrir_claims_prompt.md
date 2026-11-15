# Discussion taqrir prompt (claims and evidence)

You are an expert scholar and logician. Below is {input_kind} of a chat ("{chat_title}", {date_range}) in which one or more scholarly discussions took place. List the **points in dispute and the claims made, as precise propositions, each with its evidence**.

Use exactly this structure (the labels are shown in Persian; write them in the output language):

### محل بحث ۱: <short title of the question or point in dispute>
<one sentence stating the question precisely>

- **گزاره ۱.۱:** <one precise, self-contained proposition> — قائل: <who held it> [#id]
  - **دلیل:** <one argument or piece of evidence for it, formulated precisely: premises → conclusion, or the cited verse/narration/source> [#id]
  - **دلیل:** <next argument> [#id]
  - **اشکال:** <an objection raised against the proposition or its evidence> [#id]
    - **پاسخ:** <the reply given> [#id]
- **گزاره ۱.۲ (دیدگاه مقابل):** <the opposing or alternative proposition> — قائل: <…> [#id]
  - **دلیل:** …

**نتیجه:** <what was established, conceded, or left in dispute on this point>

Rules:
* Every proposition must be atomic (one claim), unambiguous and understandable on its own, without the surrounding conversation. Split compound claims into separate propositions.
* State exactly what was claimed, with its qualifications and scope; do not strengthen, weaken or generalise it.
* List under each proposition only the evidence that was actually given for it in the discussion. If none was given, write "- **دلیل:** (دلیلی ذکر نشد)".
* Objections and replies go under the proposition (or the specific evidence) they target, in the order they were raised.
* Keep quotations, citations (verses, narrations, books, scholars) and technical terms exactly as given.
* Number points in dispute and propositions as shown (۱، ۱.۱، ۱.۲، ۲، ۲.۱ …).
* Do not add claims, arguments or sources that are not in the input, and do not evaluate them. Skip greetings and off-topic chatter.
* Cite the message(s) each item comes from as [#id] (several: [#12, #15]), using the ids in the input.
* {attribution_instruction}
* {language_instruction}
{instruction}
* Output ONLY the list, with no top-level heading, preamble or closing remarks.

Input:

"""
{text}
"""
