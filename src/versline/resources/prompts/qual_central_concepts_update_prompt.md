You are updating a qualitative-research central-concepts map based on completed coding results.

Goal:
- Read the original central-concepts structure carefully.
- Revise it conservatively and academically based on grounded evidence from coded findings.
- Preserve continuity with original conceptual framing unless evidence strongly supports change.

Scientific and methodological rules:
1. Do not remove a concept unless evidence clearly contradicts or invalidates it.
2. Prefer refinement (rename, merge, split) over arbitrary replacement.
3. Add a new concept only when it is clearly supported by multiple coded indicators.
4. Keep section-level logic coherent and non-overlapping.
5. Keep concept labels concise, interpretable, and suitable for qualitative reporting.
6. `evidence_refs` should remain short and traceable to participant/source references when available.
7. Avoid speculative claims that are not supported by coding outputs.
8. Keep the output language aligned with `analysis_language`.

Return JSON only in this exact schema:
{
  "title": "string",
  "sections": [
    {
      "section": "string",
      "concepts": [
        {
          "concept": "string",
          "evidence_refs": "string"
        }
      ]
    }
  ],
  "update_memo": "short methodological note explaining major revisions"
}

Output constraints:
- Return only valid JSON object.
- Keep hierarchy compatible with Markdown export using headings: #, ##, ###, ####.
- Do not include markdown fences.
