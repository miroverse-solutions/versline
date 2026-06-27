# Research Findings Colaizzi Full Prompt

You are an expert academic research writer.

Task:
Write the FULL chapter 4 findings text for a qualitative thematic analysis study based on Colaizzi, strictly following an already approved outline.

Research context (JSON):
{research_context_json}

Approved outline (must be followed exactly in structure):
{approved_outline}

Language instruction:
{language_instruction}

Hard constraints:

1. This chapter is descriptive findings reporting only.
2. Do NOT add interpretation, theory discussion, implications, conclusion, or chapter 5 content.
3. Follow the approved outline section order and scope.
4. Use available evidence only. Do not fabricate quotes, participant IDs, or frequencies.
5. If `materials.writing_guide` exists, apply its required chapter headings, subsection sequence, and wording conventions unless they conflict with these hard constraints.
6. If `materials.sample_output` exists, emulate its academic writing rhythm, paragraph density, and table presentation style while preserving the current study's own data.
7. If data is missing for a required part, keep the section and insert: [NEEDS DATA: ...].
8. For each main theme, report sub-themes, evidence frequency if available, narrative explanation, and quote integration.
9. Keep tone formal, thesis-ready, and coherent.

Expected output:

- Complete markdown chapter text.
- Include table(s) in markdown format where the outline indicates tables.
- Include smooth transitions between theme sections.
- End the chapter without conclusion/interpretation.

Output constraints:

- Return ONLY final chapter text in markdown.
- No preface, no meta commentary.
