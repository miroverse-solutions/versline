# Discussion notes prompt (map step of the Telegram discussion taqrir)

You are an expert scholar and careful note-taker. Below is part {part} of {parts} of the message log of a chat ("{chat_title}", {date_range}). Messages are in chronological order. Each message starts with a header `[#id | date | participant | …]`; voice messages appear as transcripts, documents and images as their extracted text.

Write structured notes on THIS part that will later be merged with the notes of the other parts into a full taqrir. Notes must be complete and precise, because the final write-up will be based only on them.

For every topic or question discussed in this part, write:

### <topic or question>
* **Context:** what started the discussion [#id]
* **Positions:** each distinct claim or position, stated precisely, with who held it [#id]
* **Arguments and evidence:** under each position, every argument, proof, citation (verse, narration, book, scholar), example or analogy given for it [#id]
* **Objections and replies:** objections raised against a position and the replies to them, in order [#id]
* **Outcome:** what was agreed, conceded, or left in dispute (or "continues in a later part" if it seems to go on)

Rules:
* Stay strictly faithful to the messages: do not add claims, arguments, sources or judgements that are not in the log.
* Keep names of books, scholars, technical terms and quotations exactly as given.
* Cite the message(s) every point comes from as [#id] (several: [#12, #15]).
* Skip greetings, small talk, administrative messages and off-topic chatter.
* {attribution_instruction}
* {language_instruction}
{instruction}
* Output ONLY the notes.

Message log:

"""
{text}
"""
