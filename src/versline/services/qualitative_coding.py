import json
import hashlib
import re
import time
import csv
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from loguru import logger

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import ai
from versline.services.pricing import TokenTracker


METHOD_PROMPTS = {
    "thematic": "qual_thematic_prompt.md",
    "grounded": "qual_grounded_prompt.md",
    "content": "qual_content_prompt.md",
    "framework": "qual_framework_prompt.md",
    "colaizzi": "qual_colaizzi_prompt.md",
}


class QualitativeCoder:
    def __init__(
        self,
        output_dir: str = "output",
        methods: Optional[List[str]] = None,
        output_formats: Optional[List[str]] = None,
        include_citation: bool = False,
        words_per_batch: int = 1200,
        codebook_codes: Optional[List[str]] = None,
        code_mode: str = "guided",
        analysis_language: str = "auto",
        fail_on_parse_error: bool = False,
        csv_fill_quotes_from_segments: bool = True,
        export_excel: bool = True,
        force: bool = False,
    ):
        self.tracker = TokenTracker()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.methods = self._normalize_methods(methods or ["thematic"])
        self.output_formats = self._normalize_formats(output_formats or ["json", "markdown"])
        self.include_citation = include_citation
        self.words_per_batch = words_per_batch
        self.codebook_codes = self._normalize_codebook_codes(codebook_codes or [])
        self.code_mode = self._normalize_code_mode(code_mode)
        self.analysis_language = self._normalize_analysis_language(analysis_language)
        self.fail_on_parse_error = fail_on_parse_error
        self.csv_fill_quotes_from_segments = csv_fill_quotes_from_segments
        self.export_excel = export_excel
        self.last_parse_failures = 0
        self.force = force

        self.provider = (settings.llm.provider or "openai").lower()
        if self.provider == "google":
            self.provider = "gemini"
        self.model = settings.llm.model

        self.schema_prompt = load_prompt("qual_schema_prompt.md")
        self.method_prompts = {
            method: load_prompt(METHOD_PROMPTS[method]) for method in self.methods
        }

    def _normalize_methods(self, methods: List[str]) -> List[str]:
        normalized = []
        for method in methods:
            m = method.strip().lower()
            if m in ("thematic", "grounded", "content", "framework", "colaizzi"):
                normalized.append(m)
            else:
                raise ValueError(
                    f"Unsupported method '{method}'. Supported methods: {', '.join(METHOD_PROMPTS.keys())}"
                )

        unique_methods = []
        seen = set()
        for method in normalized:
            if method not in seen:
                seen.add(method)
                unique_methods.append(method)
        return unique_methods

    def _normalize_formats(self, formats: List[str]) -> List[str]:
        aliases = {
            "md": "markdown",
            "json": "json",
            "markdown": "markdown",
            "csv": "csv",
            "segments-csv": "segments-csv",
            "segments_csv": "segments-csv",
            "detailed-csv": "detailed-csv",
            "detailed_csv": "detailed-csv",
        }
        normalized = []
        for fmt in formats:
            key = fmt.strip().lower()
            if key not in aliases:
                raise ValueError("Supported formats are: json, markdown, csv, segments-csv, detailed-csv")
            normalized.append(aliases[key])

        unique_formats = []
        seen = set()
        for fmt in normalized:
            if fmt not in seen:
                seen.add(fmt)
                unique_formats.append(fmt)
        return unique_formats

    def _normalize_codebook_codes(self, codebook_codes: List[str]) -> List[str]:
        normalized = []
        seen = set()
        for code in codebook_codes:
            cleaned = str(code).strip()
            if not cleaned:
                continue
            marker = cleaned.lower()
            if marker in seen:
                continue
            seen.add(marker)
            normalized.append(cleaned)
        return normalized

    def _normalize_code_mode(self, code_mode: str) -> str:
        mode = str(code_mode).strip().lower()
        if mode not in {"guided", "strict"}:
            raise ValueError("code_mode must be one of: guided, strict")
        return mode

    def _normalize_analysis_language(self, analysis_language: str) -> str:
        value = str(analysis_language).strip().lower()
        aliases = {
            "auto": "auto",
            "fa": "fa",
            "persian": "fa",
            "farsi": "fa",
            "en": "en",
            "english": "en",
        }
        if value not in aliases:
            raise ValueError("analysis_language must be one of: auto, fa, en")
        return aliases[value]

    def _infer_analysis_language(self, segments: List[Dict[str, Any]]) -> str:
        if self.analysis_language != "auto":
            return self.analysis_language

        sample_text = "\n".join(str(seg.get("text", "")) for seg in segments)
        fa_chars = re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", sample_text)
        latin_chars = re.findall(r"[A-Za-z]", sample_text)

        if len(fa_chars) >= max(30, int(0.25 * max(1, len(latin_chars)))):
            return "fa"
        return "en"

    def _normalize_text_key(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or ""))
        replacements = {
            "ي": "ی",
            "ى": "ی",
            "ك": "ک",
            "ۀ": "ه",
            "ة": "ه",
            "ؤ": "و",
            "إ": "ا",
            "أ": "ا",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)

        normalized = normalized.replace("\u200c", " ").replace("\u200d", " ")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        return normalized

    def _estimate_word_count(self, text: str) -> int:
        tokens = re.findall(r"[A-Za-z0-9_\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+", text or "")
        return len(tokens)

    def _segment_markdown(self, content: str) -> List[Dict[str, Any]]:
        lines = content.splitlines()
        segments: List[Dict[str, Any]] = []

        current_lines: List[str] = []
        start_line = 1

        def flush_segment(end_line: int):
            nonlocal current_lines, start_line
            if not current_lines:
                return
            text = "\n".join(current_lines).strip()
            current_lines = []
            if not text:
                return
            segment_id = f"S{len(segments) + 1}"
            segments.append(
                {
                    "id": segment_id,
                    "start_line": start_line,
                    "end_line": end_line,
                    "text": text,
                    "word_count": self._estimate_word_count(text),
                }
            )

        for index, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("#") and current_lines:
                flush_segment(index - 1)
                start_line = index
                current_lines = [line]
                continue

            if stripped == "":
                flush_segment(index - 1)
                start_line = index + 1
                continue

            if not current_lines:
                start_line = index
            current_lines.append(line)

        flush_segment(len(lines))
        return segments

    def _build_batches(self, segments: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        batches: List[List[Dict[str, Any]]] = []
        current_batch: List[Dict[str, Any]] = []
        current_words = 0

        for segment in segments:
            segment_words = int(segment.get("word_count", 0))
            if current_batch and current_words + segment_words > self.words_per_batch:
                batches.append(current_batch)
                current_batch = [segment]
                current_words = segment_words
            else:
                current_batch.append(segment)
                current_words += segment_words

        if current_batch:
            batches.append(current_batch)
        return batches

    def _progress_file(self, source_file: Path) -> Path:
        work_dir = Path("work_dir") / source_file.stem
        work_dir.mkdir(parents=True, exist_ok=True)
        signature_payload = {
            "methods": self.methods,
            "code_mode": self.code_mode,
            "codebook_codes": self.codebook_codes,
            "include_citation": self.include_citation,
            "words_per_batch": self.words_per_batch,
            "analysis_language": self.analysis_language,
            "provider": self.provider,
            "model": self.model,
        }
        raw = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return work_dir / f"qual_progress_{signature}.json"

    def _load_progress(self, progress_file: Path) -> Dict[str, Any]:
        if not progress_file.exists() or self.force:
            return {"methods": {}}

        try:
            with open(progress_file, "r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                return {"methods": {}}
            if "methods" not in data or not isinstance(data["methods"], dict):
                data["methods"] = {}
            return data
        except Exception as error:
            logger.warning(f"Unable to load qualitative progress: {error}")
            return {"methods": {}}

    def _save_progress(self, progress_file: Path, progress_data: Dict[str, Any]):
        with open(progress_file, "w", encoding="utf-8") as file:
            json.dump(progress_data, file, ensure_ascii=False, indent=2)

    def _build_prompt(self, method: str, batch_segments: List[Dict[str, Any]], batch_index: int, total_batches: int, target_language: str) -> str:
        method_prompt = self.method_prompts[method]
        citation_instruction = (
            "Citation mode is ENABLED. Fill quotes and segment_ids with exact grounded evidence."
            if self.include_citation
            else "Citation mode is DISABLED. Keep quotes as empty arrays, but keep segment_ids grounded."
        )
        if self.codebook_codes:
            if self.code_mode == "strict":
                codebook_instruction = (
                    "Codebook mode is STRICT. You MUST only use codes from the allowed codebook list. "
                    "Do not invent any new code names."
                )
            else:
                codebook_instruction = (
                    "Codebook mode is GUIDED. Prefer using allowed codebook codes when possible, "
                    "but you MAY add well-justified new codes if the data requires them."
                )
        else:
            codebook_instruction = "No codebook is provided. Build codes directly from the data."

        if target_language == "fa":
            language_instruction = (
                "Input may be Persian, English, or code-mixed. You MUST generate analytic fields in Persian "
                "(codes, descriptions, categories, themes, findings, memo). Keep quotes in original script exactly. "
                "Do not switch analytic labels to English unless it is an unavoidable proper noun."
            )
        else:
            language_instruction = (
                "Input may be Persian, English, or code-mixed. You MUST generate analytic fields in English "
                "(codes, descriptions, categories, themes, findings, memo). Keep quotes in original script exactly."
            )

        payload = {
            "method": method,
            "batch_index": batch_index,
            "total_batches": total_batches,
            "codebook": {
                "mode": self.code_mode,
                "allowed_codes": self.codebook_codes,
            },
            "analysis_language": target_language,
            "segments": [
                {
                    "id": segment["id"],
                    "start_line": segment["start_line"],
                    "end_line": segment["end_line"],
                    "text": segment["text"],
                }
                for segment in batch_segments
            ],
        }

        return (
            f"{method_prompt}\n\n"
            f"{self.schema_prompt}\n\n"
            f"{citation_instruction}\n\n"
            f"{codebook_instruction}\n\n"
            f"{language_instruction}\n\n"
            "Analyze the following input and return only a JSON object:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _enforce_codebook_on_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not self.codebook_codes:
            return result

        normalized_codebook = {self._normalize_text_key(code) for code in self.codebook_codes}

        codes = result.get("codes", [])
        if not isinstance(codes, list):
            return result

        normalized_codes = []
        for item in codes:
            if not isinstance(item, dict):
                continue
            code_name = str(item.get("code", "")).strip()
            if not code_name:
                continue

            is_known = self._normalize_text_key(code_name) in normalized_codebook
            if self.code_mode == "strict" and not is_known:
                continue

            item["in_codebook"] = is_known
            normalized_codes.append(item)

        result["codes"] = normalized_codes

        categories = result.get("categories", [])
        if isinstance(categories, list):
            valid_code_names = {str(item.get("code", "")).strip() for item in normalized_codes}
            for category in categories:
                if not isinstance(category, dict):
                    continue
                code_names = category.get("code_names", [])
                if not isinstance(code_names, list):
                    continue
                category["code_names"] = [
                    str(name).strip()
                    for name in code_names
                    if str(name).strip() in valid_code_names
                ]

        return result

    def _clean_json(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def _extract_first_json_object(self, text: str) -> Optional[str]:
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        return None

    def _parse_json_response(self, raw_text: str) -> Optional[Dict[str, Any]]:
        cleaned = self._clean_json(raw_text)

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        try:
            parsed, _ = json.JSONDecoder().raw_decode(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        extracted = self._extract_first_json_object(cleaned)
        if extracted:
            try:
                parsed = json.loads(extracted)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _get_openai_compatible_client(self):
        provider = self.provider
        endpoint = settings.llm.api_endpoint
        if provider == "avalai" and not endpoint:
            endpoint = "https://api.avalai.ir/v1"
        elif provider == "openrouter" and not endpoint:
            endpoint = "https://openrouter.ai/api/v1"

        llm_settings = ai.LLMSettings(
            provider=provider,
            model=self.model,
            api_key=settings.llm.api_key,
            api_endpoint=endpoint,
            proxy=settings.llm.proxy,
        )
        return ai.configure_openai(llm_settings)

    def _request_llm(self, prompt: str) -> Dict[str, Any]:
        if self.provider == "gemini":
            client = ai.configure_gemini(settings.llm)
            if client is None:
                raise RuntimeError("Failed to initialize Gemini client")
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                self.tracker.add_usage(
                    response.usage_metadata.prompt_token_count,
                    response.usage_metadata.candidates_token_count,
                )
            raw_text = response.text or "{}"
        else:
            client = self._get_openai_compatible_client()
            if client is None:
                raise RuntimeError("Failed to initialize OpenAI-compatible client")

            messages = [
                {"role": "system", "content": "You are a rigorous qualitative researcher."},
                {"role": "user", "content": prompt},
            ]

            is_avalai = (
                self.provider == "avalai"
                or (hasattr(client, "base_url") and "avalai.ir" in str(client.base_url))
            )

            if is_avalai and hasattr(client.chat.completions, "with_raw_response"):
                response_raw = client.chat.completions.with_raw_response.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                request_id = response_raw.headers.get("x-request-id")
                if request_id:
                    self.tracker.add_avalai_request(request_id)
                completion = response_raw.parse()
            else:
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )

            if completion.usage:
                self.tracker.add_usage(
                    completion.usage.prompt_tokens,
                    completion.usage.completion_tokens,
                )
            raw_text = completion.choices[0].message.content or "{}"

        parsed = self._parse_json_response(raw_text)
        if parsed is not None:
            return parsed

        logger.error("Failed to parse JSON response: unable to recover valid JSON object")
        return {
            "method": "unknown",
            "codes": [],
            "categories": [],
            "themes": [],
            "framework_matrix": [],
            "findings": ["Response parsing failed."],
            "memo": "",
            "_parse_failed": True,
        }

    def _merge_method_results(self, method: str, batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        merged = {
            "method": method,
            "codes": [],
            "categories": [],
            "themes": [],
            "framework_matrix": [],
            "findings": [],
            "memo": "",
        }

        for result in batch_results:
            merged["codes"].extend(result.get("codes", []))
            merged["categories"].extend(result.get("categories", []))
            merged["themes"].extend(result.get("themes", []))
            merged["framework_matrix"].extend(result.get("framework_matrix", []))
            merged["findings"].extend(result.get("findings", []))
            memo = result.get("memo", "")
            if memo:
                merged["memo"] += ("\n\n" if merged["memo"] else "") + memo

        merged["codes"] = self._dedupe_dict_items(merged["codes"], key="code")
        merged["categories"] = self._dedupe_dict_items(merged["categories"], key="name")
        merged["themes"] = self._dedupe_dict_items(merged["themes"], key="name")
        merged["framework_matrix"] = self._dedupe_dict_items(merged["framework_matrix"], key="dimension")
        merged["findings"] = self._dedupe_strings(merged["findings"])
        return merged

    def _dedupe_dict_items(self, items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        seen = set()
        for item in items:
            marker = str(item.get(key, "")).strip().lower()
            if not marker:
                unique.append(item)
                continue
            if marker in seen:
                continue
            seen.add(marker)
            unique.append(item)
        return unique

    def _dedupe_strings(self, values: List[str]) -> List[str]:
        unique = []
        seen = set()
        for value in values:
            marker = str(value).strip().lower()
            if not marker or marker in seen:
                continue
            seen.add(marker)
            unique.append(value)
        return unique

    def _to_markdown_report(self, data: Dict[str, Any]) -> str:
        lines: List[str] = []
        meta = data.get("meta", {})
        lines.append("# Qualitative Coding Report")
        lines.append("")
        lines.append(f"- Source: {meta.get('source_file', 'unknown')}")
        lines.append(f"- Provider: {meta.get('provider', 'unknown')}")
        lines.append(f"- Model: {meta.get('model', 'unknown')}")
        lines.append(f"- Citation mode: {meta.get('citation_enabled', False)}")
        lines.append("")

        methods_data: Dict[str, Dict[str, Any]] = data.get("methods", {})
        for method, result in methods_data.items():
            lines.append(f"## Method: {method}")
            lines.append("")

            themes = result.get("themes", [])
            if themes:
                lines.append("### Themes")
                for theme in themes:
                    lines.append(f"- **{theme.get('name', 'Unnamed Theme')}**: {theme.get('description', '')}")
                lines.append("")

            categories = result.get("categories", [])
            if categories:
                lines.append("### Categories")
                for category in categories:
                    lines.append(f"- **{category.get('name', 'Unnamed Category')}**: {category.get('description', '')}")
                lines.append("")

            codes = result.get("codes", [])
            if codes:
                lines.append("### Codes")
                for code in codes:
                    segment_ids = ", ".join(code.get("segment_ids", []))
                    lines.append(f"- **{code.get('code', 'Unnamed Code')}** ({segment_ids}): {code.get('description', '')}")
                lines.append("")

            findings = result.get("findings", [])
            if findings:
                lines.append("### Findings")
                for finding in findings:
                    lines.append(f"- {finding}")
                lines.append("")

        return "\n".join(lines).strip() + "\n"

    def _build_code_quotes_rows(self, data: Dict[str, Any], segment_text_by_id: Dict[str, str]) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        methods_data: Dict[str, Dict[str, Any]] = data.get("methods", {})

        aggregated: Dict[str, Dict[str, Any]] = {}
        for method, result in methods_data.items():
            codes = result.get("codes", [])
            if not isinstance(codes, list):
                continue

            for code_obj in codes:
                if not isinstance(code_obj, dict):
                    continue
                code_name = str(code_obj.get("code", "")).strip()
                if not code_name:
                    continue

                marker = self._normalize_text_key(code_name)
                if marker not in aggregated:
                    aggregated[marker] = {
                        "code": code_name,
                        "quotes": [],
                        "segment_ids": [],
                        "methods": set(),
                    }

                aggregated[marker]["methods"].add(method)
                quotes = code_obj.get("quotes", [])
                if isinstance(quotes, list):
                    for quote in quotes:
                        quote_text = str(quote).strip()
                        if quote_text and quote_text not in aggregated[marker]["quotes"]:
                            aggregated[marker]["quotes"].append(quote_text)

                segment_ids = code_obj.get("segment_ids", [])
                if isinstance(segment_ids, list):
                    for seg_id in segment_ids:
                        seg_id_text = str(seg_id).strip()
                        if seg_id_text and seg_id_text not in aggregated[marker]["segment_ids"]:
                            aggregated[marker]["segment_ids"].append(seg_id_text)

                if (
                    self.csv_fill_quotes_from_segments
                    and not aggregated[marker]["quotes"]
                ):
                    segment_ids = code_obj.get("segment_ids", [])
                    if isinstance(segment_ids, list):
                        for seg_id in segment_ids:
                            seg_text = segment_text_by_id.get(str(seg_id).strip(), "").strip()
                            if not seg_text:
                                continue
                            compact = re.sub(r"\s+", " ", seg_text)
                            snippet = compact[:220] + ("..." if len(compact) > 220 else "")
                            if snippet and snippet not in aggregated[marker]["quotes"]:
                                aggregated[marker]["quotes"].append(snippet)

        for item in aggregated.values():
            rows.append(
                {
                    "code": item["code"],
                    "quotes": " | ".join(item["quotes"]),
                    "segment_ids": ", ".join(item["segment_ids"]),
                    "method": ", ".join(sorted(item["methods"])),
                }
            )

        rows.sort(key=lambda x: self._normalize_text_key(x["code"]))
        return rows

    def _build_segments_rows(self, source_path: Path, segments: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for segment in segments:
            rows.append(
                {
                    "source_file": str(source_path),
                    "segment_id": str(segment.get("id", "")),
                    "start_line": str(segment.get("start_line", "")),
                    "end_line": str(segment.get("end_line", "")),
                    "word_count": str(segment.get("word_count", "")),
                    "text": str(segment.get("text", "")),
                }
            )
        return rows

    def _build_detailed_code_segments_rows(self, data: Dict[str, Any], segment_text_by_id: Dict[str, str]) -> List[Dict[str, str]]:
        methods_data: Dict[str, Dict[str, Any]] = data.get("methods", {})
        aggregated: Dict[str, Dict[str, Any]] = {}

        for method, result in methods_data.items():
            codes = result.get("codes", [])
            if not isinstance(codes, list):
                continue

            for code_obj in codes:
                if not isinstance(code_obj, dict):
                    continue

                code_name = str(code_obj.get("code", "")).strip()
                if not code_name:
                    continue

                marker = self._normalize_text_key(code_name)
                if marker not in aggregated:
                    aggregated[marker] = {
                        "code": code_name,
                        "methods": set(),
                        "segment_ids": [],
                        "segments": [],
                    }

                aggregated[marker]["methods"].add(method)

                segment_ids = code_obj.get("segment_ids", [])
                if isinstance(segment_ids, list):
                    for seg_id in segment_ids:
                        seg_id_text = str(seg_id).strip()
                        if not seg_id_text:
                            continue
                        if seg_id_text not in aggregated[marker]["segment_ids"]:
                            aggregated[marker]["segment_ids"].append(seg_id_text)

                        seg_text = segment_text_by_id.get(seg_id_text, "").strip()
                        if seg_text and seg_text not in aggregated[marker]["segments"]:
                            aggregated[marker]["segments"].append(seg_text)

        max_segments = 0
        for item in aggregated.values():
            if len(item["segments"]) > max_segments:
                max_segments = len(item["segments"])

        rows: List[Dict[str, str]] = []
        for item in aggregated.values():
            row = {
                "code": item["code"],
                "method": ", ".join(sorted(item["methods"])),
                "segment_ids": ", ".join(item["segment_ids"]),
            }
            for index in range(max_segments):
                key = f"segment_{index + 1}"
                row[key] = item["segments"][index] if index < len(item["segments"]) else ""
            rows.append(row)

        rows.sort(key=lambda x: self._normalize_text_key(x["code"]))
        return rows

    def _export_excel_from_csv(self, csv_path: Path) -> Optional[Path]:
        if not self.export_excel:
            return None
        try:
            frame = pd.read_csv(csv_path)
            xlsx_path = csv_path.with_suffix(".xlsx")
            frame.to_excel(xlsx_path, index=False)
            return xlsx_path
        except Exception as error:
            logger.warning(f"Failed to export Excel from CSV ({csv_path.name}): {error}")
            return None

    def process_file(self, file_path: str, progress_callback=None) -> Dict[str, Path]:
        source_path = Path(file_path).resolve()
        if source_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
            raise ValueError("Only markdown/text files are supported for qualitative coding")

        content = source_path.read_text(encoding="utf-8")
        segments = self._segment_markdown(content)
        if not segments:
            raise ValueError("No content found for analysis")

        batches = self._build_batches(segments)
        total_batches = len(batches)
        target_language = self._infer_analysis_language(segments)
        logger.info(f"Prepared {len(segments)} segments in {total_batches} batch(es)")

        progress_file = self._progress_file(source_path)
        if self.force and progress_file.exists():
            progress_file.unlink(missing_ok=True)

        progress_state = self._load_progress(progress_file)
        methods_progress = progress_state.get("methods", {})

        method_results: Dict[str, Dict[str, Any]] = {}
        parse_failures = 0

        for method in self.methods:
            method_state = methods_progress.get(method, {"completed_batches": 0, "batch_results": []})
            completed_batches = int(method_state.get("completed_batches", 0))
            batch_results = deepcopy(method_state.get("batch_results", []))

            if progress_callback:
                progress_callback(0, total_batches, f"Method {method}: starting")

            for batch_index in range(completed_batches, total_batches):
                prompt = self._build_prompt(method, batches[batch_index], batch_index + 1, total_batches, target_language)
                logger.info(
                    f"Analyzing {source_path.name} | method={method} | batch={batch_index + 1}/{total_batches}"
                )
                result = self._request_llm(prompt)
                if result.get("_parse_failed"):
                    parse_failures += 1
                result = self._enforce_codebook_on_result(result)
                result["method"] = method
                batch_results.append(result)

                methods_progress[method] = {
                    "completed_batches": batch_index + 1,
                    "batch_results": batch_results,
                }
                progress_state["methods"] = methods_progress
                self._save_progress(progress_file, progress_state)

                if progress_callback:
                    progress_callback(batch_index + 1, total_batches, f"Method {method}: batch {batch_index + 1}")

                time.sleep(0.1)

            method_results[method] = self._merge_method_results(method, batch_results)

        self.last_parse_failures = parse_failures
        if self.fail_on_parse_error and parse_failures > 0:
            raise RuntimeError(
                f"Detected {parse_failures} parse failure(s) while processing batches. "
                "Rerun with different chunking/model or disable --fail-on-parse-error."
            )

        segment_text_by_id = {
            str(segment["id"]): str(segment.get("text", ""))
            for segment in segments
        }

        data = {
            "meta": {
                "source_file": str(source_path),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "provider": self.provider,
                "model": self.model,
                "granularity": "line_paragraph",
                "analysis_language": target_language,
                "citation_enabled": self.include_citation,
                "code_mode": self.code_mode,
                "codebook_codes": self.codebook_codes,
                "batch_count": total_batches,
                "parse_failures": parse_failures,
            },
            "segments": [
                {
                    "id": segment["id"],
                    "start_line": segment["start_line"],
                    "end_line": segment["end_line"],
                }
                for segment in segments
            ],
            "methods": method_results,
            "maxqda_hint": {
                "schema": "structured-json",
                "notes": "Use methods/method-name/codes with segment_ids as mapping references.",
            },
        }

        stem = source_path.stem
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        outputs: Dict[str, Path] = {}

        if "json" in self.output_formats:
            json_path = self.output_dir / f"{stem}_qual_{timestamp}.json"
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs["json"] = json_path

        if "markdown" in self.output_formats:
            md_path = self.output_dir / f"{stem}_qual_{timestamp}.md"
            md_path.write_text(self._to_markdown_report(data), encoding="utf-8")
            outputs["markdown"] = md_path

        if "csv" in self.output_formats:
            csv_path = self.output_dir / f"{stem}_qual_{timestamp}.csv"
            rows = self._build_code_quotes_rows(data, segment_text_by_id)
            with open(csv_path, "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["code", "quotes", "segment_ids", "method"])
                writer.writeheader()
                writer.writerows(rows)
            outputs["csv"] = csv_path
            xlsx_path = self._export_excel_from_csv(csv_path)
            if xlsx_path:
                outputs["csv-xlsx"] = xlsx_path

        if "segments-csv" in self.output_formats:
            segments_csv_path = self.output_dir / f"{stem}_segments_{timestamp}.csv"
            segment_rows = self._build_segments_rows(source_path, segments)
            with open(segments_csv_path, "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["source_file", "segment_id", "start_line", "end_line", "word_count", "text"],
                )
                writer.writeheader()
                writer.writerows(segment_rows)
            outputs["segments-csv"] = segments_csv_path
            xlsx_path = self._export_excel_from_csv(segments_csv_path)
            if xlsx_path:
                outputs["segments-csv-xlsx"] = xlsx_path

        if "detailed-csv" in self.output_formats:
            detailed_csv_path = self.output_dir / f"{stem}_detailed_{timestamp}.csv"
            detailed_rows = self._build_detailed_code_segments_rows(data, segment_text_by_id)
            segment_columns = 0
            if detailed_rows:
                segment_columns = sum(1 for key in detailed_rows[0].keys() if key.startswith("segment_"))
            fieldnames = ["code", "method", "segment_ids"] + [f"segment_{index + 1}" for index in range(segment_columns)]

            with open(detailed_csv_path, "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(detailed_rows)
            outputs["detailed-csv"] = detailed_csv_path
            xlsx_path = self._export_excel_from_csv(detailed_csv_path)
            if xlsx_path:
                outputs["detailed-csv-xlsx"] = xlsx_path

        return outputs
