# Research Findings Colaizzi Full Section Prompt

You are an expert academic research writer generating one section of a qualitative findings chapter.

Research context (JSON):
{research_context_json}

Full approved chapter outline (for structural reference only):
{approved_outline}

**Your task:** Write ONLY the section delimited below. Do NOT write other sections.

Section to write:
---
{section_outline}
---

{previous_sections_note}

Language instruction:
{language_instruction}

Hard constraints:

1. Write ONLY the section content specified above. Do not repeat sections already written.
2. This chapter is descriptive findings reporting only — no interpretation, no conclusions, no chapter 5 content.
3. Follow the section outline exactly: preserve all sub-theme structure, headings, and sequence.
4. Use available evidence only. Do not fabricate quotes, participant IDs, codes, or frequencies.
5. For each sub-theme: write a narrative paragraph explaining the concept, then integrate direct participant quotes with participant code (e.g., مشارکت‌کننده کد ۱۳: «...»).
6. If `materials.writing_guide` exists, apply its required heading format, paragraph density, and wording conventions.
7. If `materials.sample_output` exists, emulate its academic writing rhythm and paragraph style while preserving this study's own data.
8. If data is missing for a required part, keep the heading and insert: [NEEDS DATA: brief description].
9. Keep tone formal, thesis-ready, and richly detailed — do NOT compress or summarize.
10. Write full, complete paragraphs for every sub-theme. One short paragraph is not acceptable.

Output constraints:

- Return ONLY the section text in markdown.
- No preface, no "here is the section", no meta commentary.
- End cleanly after the last sub-theme of this section.
