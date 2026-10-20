import os
import time
import json
import base64
import mimetypes
import re
from pathlib import Path
from loguru import logger
from versline.config import settings
from versline.services import ai
from versline.services.ai import track_openai_usage
from versline.services import media
from versline.core.prompts import load_prompt
from versline.utils.common import find_best_text_overlap_point
from versline.services.pricing import TokenTracker


class ContentBlockedError(RuntimeError):
    """Provider refused the content (policy block); retries are pointless."""

class AudioTranscriber:
    def __init__(self, user_note: str | None = None):
        self.tracker = TokenTracker()
        self.user_note = user_note
        try:
            self.transcription_prompt = load_prompt("transcription_prompt.md")
        except FileNotFoundError:
            logger.warning("Default prompt file not found. Using empty prompt.")
            self.transcription_prompt = ""
        # self.json_prompt = ... # handled if needed

    def _resolve_provider_name(self) -> str:
        raw_provider = (
            settings.llm.provider
            or os.getenv("VERSLINE_LLM_PROVIDER")
            or "google"
        )
        normalized = str(raw_provider).strip().lower()
        aliases = {
            "google": "gemini",
            "openai-compatible": "openaicompatible",
            "openai_compatible": "openaicompatible",
            "custom": "openaicompatible",
        }
        return aliases.get(normalized, normalized)

    def _build_avalai_extra_body(self, model_name: str) -> dict | None:
        explicit_provider = (
            (settings.llm.avalai_provider if hasattr(settings.llm, "avalai_provider") else None)
            or os.getenv("VERSLINE_LLM_AVALAI_PROVIDER")
            or os.getenv("VERSLINE_AVALAI_PROVIDER")
        )
        if explicit_provider:
            return {"provider": str(explicit_provider).strip().lower()}

        model = str(model_name or "").strip().lower()
        if model.startswith("gemini"):
            return {"provider": "google"}
        if model.startswith("claude"):
            return {"provider": "anthropic"}
        if model.startswith(("gpt", "o1", "o3", "text-embedding", "whisper")):
            return {"provider": "openai"}
        return None

    def extract_speaker_samples(self, text, sample_length=200):
        if not text:
            return {}
        
        pattern = r'\*\*([^*]+?):\*\*'
        parts = re.split(pattern, text)
        
        speakers = {}
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                speaker_name = parts[i].strip()
                speaker_text = parts[i + 1].strip()
                if speaker_text:
                    sample = speaker_text[-sample_length:].strip()
                    speakers[speaker_name] = sample
        return speakers

    def extract_all_speaker_samples_from_all_chunks(self, transcriptions):
        all_speakers = {}
        for transcription in transcriptions:
            chunk_speakers = self.extract_speaker_samples(transcription, sample_length=300)
            all_speakers.update(chunk_speakers)
        return all_speakers

    def build_prompt_with_context(self, base_prompt, chunk_index, speaker_samples=None):
        if chunk_index == 0 or not speaker_samples:
            prompt = base_prompt
        else:
            speaker_examples = []
            for speaker_name, sample in speaker_samples.items():
                speaker_examples.append(f"- **{speaker_name}:** «{sample}»")
            
            speaker_list_text = "\n".join(speaker_examples)
            
            context_instruction = f"""
[بخش ۳: زمینه و نمونه صدای گویندگان از چانک‌های قبلی]
⚠️ این چانک ادامه چانک‌های قبلی است. تاکنون، گویندگان زیر شناسایی شده‌اند و نمونه‌ای از آخرین صحبت‌های هرکدام را در زیر می‌بینی:

{speaker_list_text}

**دستورالعمل مهم برای شناسایی گویندگان در این چانک:**
1. با شنیدن صدا در این چانک، آن را با نمونه‌های بالا مقایسه کن
2. اگر صدایی شبیه به یکی از گویندگان بالا بود، حتماً از همان نام استفاده کن (مثلاً اگر صدا شبیه گوینده اول است، باز هم بنویس "گوینده اول")
3. **فقط در صورتی** که صدای کاملاً جدید و متفاوتی شنیدی که با هیچ‌کدام از بالا مطابقت ندارد، گوینده جدید اضافه کن
4. ترتیب صحبت کردن در این چانک ممکن است متفاوت باشد؛ مهم این است که صدا را تشخیص دهی نه ترتیب

مثال: اگر در این چانک ابتدا گوینده دوم صحبت کند و بعد گوینده اول، باید بنویسی:
**گوینده دوم:** ...
**گوینده اول:** ...
"""
            parts = base_prompt.split('[بخش ۴:', 1)
            if len(parts) == 2:
                prompt = parts[0] + context_instruction + '\n[بخش ۴:' + parts[1]
            else:
                parts2 = base_prompt.split('[بخش ۴', 1)
                if len(parts2) == 2:
                    prompt = parts2[0] + context_instruction + '\n[بخش ۴' + parts2[1]
                else:
                    prompt = base_prompt + '\n' + context_instruction

        if self.user_note:
            prompt = prompt + f"\n\n---\n\n**Additional instructions from user:**\n{self.user_note}"

        return prompt

    def save_progress(self, progress_file: str, chunk_index: int, transcriptions: list, chunk_meta: dict | None = None, speaker_samples: dict | None = None):
        data = {
            "last_chunk_index": chunk_index,
            "transcriptions": transcriptions
        }
        if speaker_samples is not None:
            data["speaker_samples"] = speaker_samples
        if chunk_meta is not None:
            data["chunk_meta"] = chunk_meta
        else:
             if os.path.exists(progress_file):
                try:
                    with open(progress_file, "r", encoding="utf-8") as f:
                        old = json.load(f)
                        if "chunk_meta" in old:
                            data["chunk_meta"] = old["chunk_meta"]
                except Exception:
                    pass
        
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"💾 Progress saved at chunk {chunk_index}")

    def load_progress(self, progress_file: str):
        if not os.path.exists(progress_file):
            return 0, [], None, None
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            last_index = data.get("last_chunk_index", 0)
            transcriptions = data.get("transcriptions", [])
            chunk_meta = data.get("chunk_meta", None)
            speaker_samples = data.get("speaker_samples", None)
            logger.info(f"📥 Resumed from chunk {last_index}, {len(transcriptions)} chunks already transcribed")
            return last_index, transcriptions, chunk_meta, speaker_samples
        except Exception as e:
            logger.error(f"⚠️ Error loading progress: {e}")
            return 0, [], None, None

    def transcribe_chunk_with_retry(self, model_name, audio_path, prompt, max_retries=3):
        chunk_name = Path(audio_path).name
        for attempt in range(max_retries):
            try:
                provider = self._resolve_provider_name()

                logger.info(f"[{chunk_name}] attempt {attempt+1}/{max_retries} — provider={provider}, model={model_name}")
                
                result = None
                if provider == "gemini":
                    client = ai.configure_gemini(settings.llm)
                    result = self.transcribe_audio_chunk_by_gemini(client, model_name, audio_path, prompt)
                elif provider == "openai": # OpenAI
                    client = ai.configure_openai(settings.llm)
                    result = self.transcribe_audio_chunk_by_openaicompatible(client, model_name, audio_path, prompt, provider=provider)
                elif provider == "avalai":
                    # Temporarily set endpoint for AvalAI, respecting user-configured endpoint
                    original_endpoint = settings.llm.api_endpoint
                    effective_endpoint = original_endpoint or "https://api.avalai.ir/v1"
                    if original_endpoint and original_endpoint != "https://api.avalai.ir/v1":
                        logger.debug(f"[avalai] Using custom endpoint from config: {original_endpoint}")
                    settings.llm.api_endpoint = effective_endpoint
                    try:
                        client = ai.configure_openai(settings.llm)
                        result = self.transcribe_audio_chunk_by_openaicompatible(client, model_name, audio_path, prompt, provider=provider)
                    finally:
                        settings.llm.api_endpoint = original_endpoint
                elif provider == "openaicompatible":
                    client = ai.configure_openai(settings.llm)
                    result = self.transcribe_audio_chunk_by_openaicompatible(client, model_name, audio_path, prompt, provider=provider)
                elif provider == "openrouter":
                    original_endpoint = settings.llm.api_endpoint
                    settings.llm.api_endpoint = "https://openrouter.ai/api/v1"
                    try:
                        client = ai.configure_openai(settings.llm)
                        result = self.transcribe_audio_chunk_by_openaicompatible(client, model_name, audio_path, prompt, provider=provider, mode="responses") # OpenRouter often supports standard chat
                    finally:
                        settings.llm.api_endpoint = original_endpoint
                else:
                     logger.warning(f"Unknown provider {provider}, trying OpenAI Compatible default")
                     client = ai.configure_openai(settings.llm)
                     result = self.transcribe_audio_chunk_by_openaicompatible(client, model_name, audio_path, prompt, provider=provider)

                if result and result.strip():
                    return result
                raise RuntimeError("Empty transcription result (model returned blank response)")
            except ContentBlockedError as e:
                logger.error(
                    f"[{chunk_name}] {e}. Try a different model/provider for this file "
                    f"(e.g. a non-Gemini model); progress up to the previous chunk is saved."
                )
                raise
            except Exception as e:
                endpoint_hint = getattr(settings.llm, "api_endpoint", None) or "(default)"
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(
                        f"[{chunk_name}] attempt {attempt+1} failed — {type(e).__name__}: {e} "
                        f"(endpoint={endpoint_hint}, model={model_name}). Retrying in {wait_time}s…"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[{chunk_name}] all {max_retries} attempts failed — "
                        f"{type(e).__name__}: {e} (endpoint={endpoint_hint}, model={model_name})"
                    )
                    raise

    def transcribe_audio_chunk_by_gemini(self, client, model_name, audio_path, prompt):
        if client is None:
            return None
        try:
            # Upload logic ... 
            # Simplified for brevity, assume updated library logic
            uploaded_file = client.files.upload(file=audio_path)
            
            # Wait for processing
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = client.files.get(name=uploaded_file.name)
                
            if uploaded_file.state.name == "FAILED":
                 raise ValueError("File processing failed")

            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, uploaded_file]
            )
            
            # Cleanup
            client.files.delete(name=uploaded_file.name)
            
            if response.usage_metadata:
                self.tracker.add_usage(
                    response.usage_metadata.prompt_token_count,
                    response.usage_metadata.candidates_token_count
                )
            
            return response.text
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            raise

    def _normalize_native_segments(self, segments):
        normalized = []
        for seg in segments or []:
            try:
                start = float(seg.get("start"))
                end = float(seg.get("end"))
            except Exception:
                continue
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            normalized.append({"start": start, "end": end, "text": text})
        return normalized

    @staticmethod
    def _is_degenerate_segments(segments, max_single_span: float = 60.0) -> bool:
        """A single segment spanning a long stretch means the API ignored segmentation."""
        return len(segments) == 1 and (segments[0]["end"] - segments[0]["start"]) > max_single_span

    def _words_to_segments(self, words, max_gap: float = 0.8, max_len: float = 12.0):
        """Group word-level timestamps (e.g. ElevenLabs Scribe) into sentence-like segments."""
        segments = []
        cur = None
        for w in words or []:
            if (w.get("type") or "word") != "word":
                continue
            try:
                start = float(w.get("start"))
                end = float(w.get("end"))
            except Exception:
                continue
            token = str(w.get("word", "")).strip()
            if not token:
                continue
            if cur and (start - cur["end"] > max_gap or end - cur["start"] > max_len):
                segments.append(cur)
                cur = None
            if cur is None:
                cur = {"start": start, "end": end, "text": token}
            else:
                cur["end"] = end
                cur["text"] += " " + token
            if token[-1] in ".!?؟…":
                segments.append(cur)
                cur = None
        if cur:
            segments.append(cur)
        return segments

    def _srt_timestamp_to_seconds(self, value: str) -> float:
        value = value.strip().replace(",", ".")
        hh, mm, ss = value.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)

    def _parse_srt_segments(self, srt_text: str):
        segments = []
        blocks = re.split(r"\r?\n\r?\n+", (srt_text or "").strip())
        for block in blocks:
            lines = [ln.strip().lstrip("\ufeff") for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue

            # Optional cue index line.
            if re.fullmatch(r"\d+", lines[0]):
                lines = lines[1:]
            if not lines or "-->" not in lines[0]:
                continue

            timing = lines[0]
            left, right = timing.split("-->", 1)
            start_token = left.strip().split()[0]
            end_token = right.strip().split()[0]
            try:
                start = self._srt_timestamp_to_seconds(start_token)
                end = self._srt_timestamp_to_seconds(end_token)
            except Exception:
                continue

            text = " ".join(lines[1:]).strip()
            if not text:
                continue
            segments.append({"start": start, "end": end, "text": text})
        return segments

    _STT_PROVIDER_ENDPOINTS = {
        "openai": "https://api.openai.com/v1",
        "avalai": "https://api.avalai.ir/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    def _resolve_stt_config(self) -> dict:
        """Resolve STT endpoint/key/proxy/language; each STT setting falls back to the LLM one."""
        t = settings.transcription
        llm = settings.llm
        provider = (t.timestamp_provider or "").strip().lower()
        if provider:
            endpoint = t.timestamp_api_endpoint or self._STT_PROVIDER_ENDPOINTS.get(provider)
            if not endpoint and provider in ("openaicompatible", "custom"):
                endpoint = llm.api_endpoint
        else:
            endpoint = t.timestamp_api_endpoint or llm.api_endpoint
        return {
            "endpoint": (endpoint or "https://api.avalai.ir/v1").rstrip("/"),
            "api_key": t.timestamp_api_key or llm.api_key,
            "proxy": t.timestamp_proxy or llm.proxy,
            "language": (t.timestamp_language or "").strip() or None,
        }

    def _post_stt_request(self, url: str, api_key: str | None, audio_path: str, data_params: dict, timeout_seconds: int, proxy: str | None = None):
        import requests
        mime = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"
        data_params = {k: v for k, v in data_params.items() if v is not None}
        with open(audio_path, "rb") as f:
            return requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (Path(audio_path).name, f, mime)},
                data=data_params,
                timeout=timeout_seconds,
                proxies={"http": proxy, "https": proxy} if proxy else None,
            )

    def _post_stt_logged(self, label: str, url: str, api_key: str | None, audio_path: str, data_params: dict, timeout_seconds: int, proxy: str | None = None, net_attempts: int = 2):
        """POST to the STT endpoint with timing logs; retries only on timeout/connection errors."""
        import requests
        size_mb = os.path.getsize(audio_path) / 1e6
        shown = {k: v for k, v in data_params.items() if v is not None}
        last_exc = None
        for n in range(1, net_attempts + 1):
            logger.info(
                f"🌐 STT [{label}] attempt {n}/{net_attempts}: POST {url} file={Path(audio_path).name} "
                f"({size_mb:.1f} MB) timeout={timeout_seconds}s proxy={'yes' if proxy else 'no'} params={shown}"
            )
            t0 = time.monotonic()
            try:
                resp = self._post_stt_request(url, api_key, audio_path, data_params, timeout_seconds, proxy=proxy)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exc = e
                logger.warning(f"🌐 STT [{label}] attempt {n} network error after {time.monotonic() - t0:.1f}s: {type(e).__name__}: {e}")
                continue
            logger.info(
                f"🌐 STT [{label}] HTTP {resp.status_code} in {time.monotonic() - t0:.1f}s, "
                f"content-type={resp.headers.get('content-type')}, body={len(getattr(resp, 'content', None) or resp.text or '')} bytes"
            )
            return resp
        raise last_exc

    def transcribe_chunk_via_stt_api(self, model_name: str, audio_path: str, max_retries: int = 2, with_timestamps: bool = False):
        """Transcribe using the /v1/audio/transcriptions endpoint (STT API).
        If with_timestamps=True, tries native timestamps first, falls back to chunk-based."""
        stt = self._resolve_stt_config()
        api_key = stt["api_key"]
        timestamp_proxy = stt["proxy"]
        timestamp_language = stt["language"]
        url = f"{stt['endpoint']}/audio/transcriptions"
        timeout_seconds = max(10, int(getattr(settings.transcription, "timestamp_timeout_seconds", 120) or 120))

        for attempt in range(max_retries):
            try:
                if with_timestamps:
                    verbose_error = None
                    # OpenRouter only supports json/verbose_json, so srt can't rescue a failed verbose_json.
                    no_srt = "openrouter.ai" in url
                    try:
                        verbose_params = {
                            "model": model_name,
                            "language": timestamp_language,
                            "response_format": "verbose_json",
                            "timestamp_granularities[]": ["word", "segment"],
                        }
                        verbose_resp = self._post_stt_logged(
                            "verbose_json", url, api_key, audio_path, verbose_params, timeout_seconds,
                            proxy=timestamp_proxy, net_attempts=2 if no_srt else 1,
                        )
                        if verbose_resp.status_code == 200:
                            data = verbose_resp.json()
                            logger.info(
                                f"📋 verbose_json keys={sorted(data.keys())} raw_segments={len(data.get('segments') or [])} "
                                f"raw_words={len(data.get('words') or [])} duration={data.get('duration')} language={data.get('language')}"
                            )
                            segments = self._normalize_native_segments(data.get("segments"))
                            stt_words = [
                                w for w in (data.get("words") or [])
                                if isinstance(w, dict) and (w.get("type") or "word") == "word"
                            ]
                            # True when the model itself segmented the audio (not rebuilt from words).
                            segments_native = bool(segments) and not self._is_degenerate_segments(segments)
                            if not segments_native:
                                # Some providers (e.g. OpenRouter/ElevenLabs Scribe) return one
                                # giant segment but real word-level timestamps.
                                word_segments = self._words_to_segments(data.get("words"))
                                if word_segments:
                                    segments = word_segments
                            if segments and self._is_degenerate_segments(segments):
                                logger.info("⚠️ verbose_json returned a single long segment (no real segmentation), trying srt fallback")
                            elif segments:
                                logger.info(
                                    f"✅ Native timestamps (verbose_json): {len(segments)} segments, duration={data.get('duration')}s"
                                )
                                return {
                                    "text": str(data.get("text", "")).strip(),
                                    "segments": segments,
                                    "duration": data.get("duration"),
                                    "language": data.get("language"),
                                    "words": stt_words,
                                    "segments_native": segments_native,
                                    "source": "api_native_verbose_json",
                                }
                            else:
                                logger.info("⚠️ verbose_json returned no usable segments, trying srt fallback")
                        else:
                            verbose_error = RuntimeError(
                                f"verbose_json HTTP {verbose_resp.status_code}: {verbose_resp.text[:200]}"
                            )
                            logger.warning(f"{verbose_error}; trying srt fallback")
                    except Exception as e:
                        import requests
                        if no_srt and isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                            raise RuntimeError(
                                f"verbose_json failed (timeout={timeout_seconds}s; consider raising "
                                f"VERSLINE_TRANSCRIPTION_TIMESTAMP_TIMEOUT_SECONDS): {type(e).__name__}: {e}"
                            ) from e
                        verbose_error = e
                        logger.warning(f"verbose_json request failed: {e}; trying srt fallback")

                    srt_params = {
                        "model": model_name,
                        "language": timestamp_language,
                        "response_format": "srt",
                    }
                    try:
                        srt_resp = self._post_stt_logged(
                            "srt", url, api_key, audio_path, srt_params, timeout_seconds, proxy=timestamp_proxy
                        )
                    except Exception as srt_error:
                        if verbose_error is not None:
                            raise RuntimeError(
                                f"verbose_json failed: {verbose_error}; srt fallback failed: {srt_error}"
                            ) from srt_error
                        raise

                    if srt_resp.status_code != 200:
                        msg = f"srt HTTP {srt_resp.status_code}: {srt_resp.text[:200]}"
                        if verbose_error is not None:
                            msg = f"verbose_json failed: {verbose_error}; {msg}"
                        raise RuntimeError(msg)

                    srt_segments = self._parse_srt_segments(srt_resp.text)
                    if srt_segments and self._is_degenerate_segments(srt_segments):
                        logger.info("⚠️ srt returned a single long segment (no real segmentation)")
                        return {"text": " ".join(seg["text"] for seg in srt_segments).strip(), "segments": None, "source": "api_text_only"}
                    if srt_segments:
                        logger.info(f"✅ Native timestamps (srt): {len(srt_segments)} segments")
                        return {
                            "text": " ".join(seg["text"] for seg in srt_segments).strip(),
                            "segments": srt_segments,
                            "duration": srt_segments[-1]["end"],
                            "language": timestamp_language,
                            "source": "api_native_srt",
                        }

                    logger.info("⚠️ srt fallback returned no parseable segments")
                    return {"text": (srt_resp.text or "").strip(), "segments": None, "source": "api_text_only"}

                data_params = {"model": model_name, "language": timestamp_language}
                resp = self._post_stt_request(
                    url, api_key, audio_path, data_params, timeout_seconds, proxy=timestamp_proxy
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

                content_type = (resp.headers.get("content-type") or "").lower()
                if "application/json" in content_type:
                    data = resp.json()
                    return str(data.get("text", "")).strip()
                return (resp.text or "").strip()
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 3)
                else:
                    raise
        return ""

    def transcribe_audio_chunk_by_openaicompatible(self, client, model_name, audio_path, prompt, provider="openai", mode="input_audio"):
        # Implementation of OpenAI Audio/Multimodal
        # ... (Refer to old code logic)
        try:
            ext = Path(audio_path).suffix.lower().lstrip(".") or "wav"
            mime = f"audio/{'wav' if ext not in ('mp3', 'm4a', 'ogg', 'webm') else ext}"
            audio_bytes = Path(audio_path).read_bytes()
            b64 = base64.b64encode(audio_bytes).decode("ascii")
            
            sys_prompt = prompt or "Transcribe audio."
            user_msg = "Please transcribe this audio."
            
            # Simplified "input_audio" structure for GPT-4o-audio
            messages = [
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_msg},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": b64,
                                "format": ext if ext in ("wav", "mp3") else "wav" 
                            }
                        }
                    ]
                }
            ]
            
            is_avalai = (
                provider == "avalai"
                or (hasattr(client, "base_url") and ("avalai.ir" in str(client.base_url) or "avalapis.ir" in str(client.base_url)))
            )

            create_kwargs = {
                "model": model_name,
                "messages": messages,
            }
            if is_avalai:
                avalai_extra_body = self._build_avalai_extra_body(model_name)
                if avalai_extra_body:
                    create_kwargs["extra_body"] = avalai_extra_body
            
            if is_avalai and hasattr(client.chat.completions, 'with_raw_response'):
                response_raw = client.chat.completions.with_raw_response.create(**create_kwargs)
                request_id = response_raw.headers.get("x-request-id")
                if request_id:
                    self.tracker.add_avalai_request(request_id)
                completion = response_raw.parse()
            else:
                completion = client.chat.completions.create(**create_kwargs)
            
            if completion.usage:
                track_openai_usage(self.tracker, completion.usage)

            choices = getattr(completion, "choices", None)
            if not choices:
                # OpenRouter may return HTTP 200 with an error payload (e.g. upstream
                # failure / flex-tier capacity) and no `choices`.
                err = getattr(completion, "error", None)
                if err is None:
                    err = (getattr(completion, "model_extra", None) or {}).get("error")
                err_text = str(err or completion)
                if "PROHIBITED_CONTENT" in err_text or "content_policy_violation" in err_text:
                    raise ContentBlockedError(
                        f"Request blocked by provider content policy (retrying will not help): {err_text}"
                    )
                raise RuntimeError(f"Provider returned no choices: {err_text}")
            content = choices[0].message.content
            if content is None:
                raise RuntimeError(
                    f"Provider returned empty content (finish_reason={choices[0].finish_reason})"
                )
            return content
        except Exception as e:
            endpoint = getattr(client, "base_url", "unknown")
            logger.error(f"API call failed — {type(e).__name__}: {e} (endpoint={endpoint}, model={model_name})")
            raise

    def process_file(self, file_path: str, chunk_length=900, overlap=180, progress_callback=None, force=False):
        import shutil
        file_path = str(Path(file_path).resolve())
        work_dir = Path("work_dir") / Path(file_path).stem
        work_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = work_dir / "temp_chunks"
        progress_file = work_dir / "progress.json"
        
        if reuse_only:
            force = False
        if force:
            if progress_file.exists():
                logger.warning("Force mode enabled: Deleting previous progress.")
                try:
                    progress_file.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete progress file: {e}")
            if temp_dir.exists():
                logger.warning("Force mode enabled: Deleting cached audio chunks.")
                try:
                    shutil.rmtree(str(temp_dir))
                except OSError as e:
                    logger.warning(f"Failed to delete temp chunks: {e}")
        
        last_index, transcriptions, _, speaker_samples = self.load_progress(str(progress_file))
        if speaker_samples is None:
            speaker_samples = {}

        existing_chunks = sorted(temp_dir.glob("chunk_*.*")) if temp_dir.exists() else []
        if existing_chunks:
            logger.info(f"📂 Using {len(existing_chunks)} cached audio chunks (skipping re-split).")
            chunks = [str(p) for p in existing_chunks]
        else:
            chunks = media.split_audio_with_ffmpeg(
                file_path, chunk_length, overlap, str(temp_dir)
            )
        
        total_chunks = len(chunks)
        if reuse_only:
            if not transcriptions or last_index < total_chunks:
                raise RuntimeError(
                    f"--reuse-transcript: cached transcript is incomplete ({last_index}/{total_chunks} chunks) in {progress_file}"
                )
            logger.info(f"♻️ Reusing cached transcript ({total_chunks} chunks), skipping main transcription.")
            return self.merge_transcriptions(transcriptions[:], overlap)
        if progress_callback:
            progress_callback(0, total_chunks, "Starting transcription...")
        
        if last_index > 0:
            logger.info(f"▶ Resuming from chunk {last_index + 1}/{total_chunks} ({last_index} already done).")
            if progress_callback:
                progress_callback(last_index, total_chunks, f"Resuming from chunk {last_index+1}/{total_chunks}…")
            
        final_text_blocks = transcriptions[:] # Copy existing
        
        for i, chunk_path in enumerate(chunks):
            if i < last_index:
                continue
                
            chunk_name = Path(chunk_path).name
            logger.info(f"[{i+1}/{total_chunks}] Transcribing {chunk_name}…")
            if progress_callback:
                progress_callback(i, total_chunks, f"Transcribing chunk {i+1}/{total_chunks}...")
            
            current_prompt = self.build_prompt_with_context(
                self.transcription_prompt, i, speaker_samples
            )
            
            model = settings.llm.model
            text = self.transcribe_chunk_with_retry(model, chunk_path, current_prompt)
            
            # Extract speakers for next context
            new_speakers = self.extract_speaker_samples(text)
            speaker_samples.update(new_speakers)
            
            final_text_blocks.append(text)
            
            self.save_progress(str(progress_file), i + 1, final_text_blocks, speaker_samples=speaker_samples)
            if progress_callback:
                progress_callback(i + 1, total_chunks, f"Completed chunk {i+1}")
            
        
        # Merge results
            
        
        # Merge results
        full_text = self.merge_transcriptions(final_text_blocks, overlap)
        return full_text

    def _native_timestamps_chunked(self, tm: str, file_path: str, ts_dir: Path, chunk_sec: int = 600, force: bool = False):
        """Run the native STT timestamp API on fixed-length slices and stitch results with time offsets.

        Uploading a multi-hundred-MB file in one request times out; slices stay small and each
        result is cached in ts_dir so a failed run resumes where it stopped.
        """
        import json
        import shutil
        slices_dir = ts_dir / "native_slices"
        cache_dir = ts_dir / "native_cache"
        if force:
            shutil.rmtree(slices_dir, ignore_errors=True)
            shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(slices_dir.glob("chunk_*.*")) if slices_dir.exists() else []
        slices = [str(p) for p in existing] or media.split_audio_with_ffmpeg(file_path, chunk_sec, 0, str(slices_dir))
        if not slices:
            raise RuntimeError("Could not split audio for native timestamping")

        segments, words, native_flags = [], [], []
        language = None
        for i, sp in enumerate(slices):
            offset = i * chunk_sec
            cache_file = cache_dir / f"{i:03d}.json"
            if cache_file.exists():
                logger.info(f"📂 [{i+1}/{len(slices)}] native timestamps cached")
                res = json.loads(cache_file.read_text(encoding="utf-8"))
            else:
                logger.info(f"⏱ [{i+1}/{len(slices)}] native timestamps for {Path(sp).name} (offset {offset}s)")
                res = self.transcribe_chunk_via_stt_api(tm, sp, max_retries=2, with_timestamps=True)
                if not isinstance(res, dict) or not str(res.get("source", "")).startswith("api_native"):
                    raise RuntimeError(f"Native timestamps unavailable for slice {i+1}/{len(slices)}")
                cache_file.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            for sg in res["segments"]:
                segments.append({**sg, "start": sg["start"] + offset, "end": sg["end"] + offset})
            for w in res.get("words") or []:
                words.append({**w, "start": float(w["start"]) + offset, "end": float(w["end"]) + offset})
            native_flags.append(res.get("segments_native", True))
            language = language or res.get("language")

        return {
            "text": " ".join(sg["text"] for sg in segments),
            "segments": segments,
            "words": words,
            "duration": (media.get_audio_duration(file_path) or (segments[-1]["end"] if segments else None)),
            "language": language,
            "segments_native": all(native_flags),
            "source": "api_native_verbose_json",
        }

    def process_file(self, file_path: str, chunk_length=900, overlap=180, progress_callback=None, force=False, timestamped: bool = False, timestamp_model: str | None = None, chunk_minutes: int | None = None, native_timestamps_only: bool = False, reuse_transcript: bool = False, force_timestamps: bool = False):
        """Transcribe audio file. If timestamped=True, also produce timestamp-aligned segments.
        
        Returns:
            If timestamped=False: str (the full transcription text)
            If timestamped=True: dict with {text, segments} where segments is list of {start, end, text}
        
        If native_timestamps_only=True, only the native STT API (verbose_json) is used;
        chunk-based fallback is skipped entirely and an error is raised on failure.
        """
        # --- Phase 1: Primary transcription with main model ---
        full_text = self._process_file_internal(file_path, chunk_length, overlap, progress_callback, force, reuse_only=reuse_transcript)
        
        if not timestamped:
            return full_text
        
        # --- Phase 2: Timestamp strategy (native API first, chunk-based fallback) ---
        tm = timestamp_model or settings.transcription.timestamp_model
        ts_chunk_sec = 30
        ts_overlap = 3
        
        use_stt = any(k in tm.lower() for k in ('whisper', 'transcribe', 'groq', 'scribe', 'asr'))
        logger.info(f"⏱️ Timestamped: model={tm}, method={'STT' if use_stt else 'LLM'}")
        if progress_callback:
            progress_callback(0, 1, "⏱️ Timestamp annotation...")
        
        from versline.utils.common import align_cheap_to_good_text, align_words_to_good_text
        ts_dir = Path("work_dir") / Path(file_path).stem / "timestamp_chunks"
        ts_dir.mkdir(parents=True, exist_ok=True)
        
        # Strategy 1: Try native segmentation via STT API with verbose_json
        if use_stt:
            logger.info("🔍 Trying native timestamp API (verbose_json + timestamp_granularities)...")
            try:
                native_result = self._native_timestamps_chunked(
                    tm, file_path, ts_dir, force=force or force_timestamps
                )
                source = str(native_result.get("source", "")) if isinstance(native_result, dict) else ""
                if isinstance(native_result, dict) and source.startswith("api_native"):
                    # Native timestamps available — use them directly
                    api_segments = native_result["segments"]
                    logger.info(f"✅ Using native segments: {len(api_segments)} segments")
                    # Align good text with native segments
                    # Segments from the model itself take priority; word-level alignment is used
                    # when the model returned no real segments (segments rebuilt from words).
                    def _align_by_segments():
                        api_chunks = [(s["start"], s["end"], s["text"]) for s in api_segments]
                        return align_cheap_to_good_text(full_text, api_chunks)

                    def _align_by_words():
                        if not native_result.get("words"):
                            return []
                        return align_words_to_good_text(
                            full_text, native_result["words"], total_duration=native_result.get("duration")
                        )

                    if native_result.get("segments_native", True):
                        order = [("segments", _align_by_segments), ("words", _align_by_words)]
                    else:
                        order = [("words", _align_by_words), ("segments", _align_by_segments)]
                    segments = []
                    for name, align in order:
                        segments = align()
                        if segments:
                            logger.info(f"🧩 Aligned good text using model {name}: {len(segments)} segments")
                            break
                    result = {
                        "text": full_text,
                        "segments": segments,
                        "segments_count": len(segments),
                        "timestamp_method": source or "api_native",
                        "native_duration": native_result.get("duration"),
                        "native_language": native_result.get("language"),
                    }
                    if progress_callback:
                        progress_callback(1, 1, f"✅ Native timestamp: {len(segments)} segments")
                    return result
                else:
                    if native_timestamps_only:
                        raise RuntimeError("Native timestamps not available and native_timestamps_only is set")
                    logger.info("⚠️ Native timestamps not available, using chunk-based fallback")
            except Exception as e:
                if native_timestamps_only:
                    raise RuntimeError(f"Native timestamp API failed: {e}") from e
                logger.warning(f"Native timestamp attempt failed: {e}, using chunk-based fallback")
        
        # Strategy 2: Chunk-based timestamping (fallback)
        if native_timestamps_only:
            raise RuntimeError("native_timestamps_only is set but chunk-based fallback was reached (model not recognized as STT)")
        chunks = media.split_audio_with_ffmpeg(file_path, ts_chunk_sec, ts_overlap, str(ts_dir))
        logger.info(f"📦 {len(chunks)} timestamp chunks created (chunk-based)")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        results = {}
        lock = threading.Lock()
        completed = 0
        
        def transcribe_one(i, chunk_path):
            nonlocal completed
            start_sec = i * ts_chunk_sec
            end_sec = start_sec + ts_chunk_sec
            try:
                if use_stt:
                    text = self.transcribe_chunk_via_stt_api(tm, chunk_path, max_retries=2)
                else:
                    prompt = "Transcribe this short audio clip literally in Persian. Only output spoken words."
                    text = self.transcribe_chunk_with_retry(tm, chunk_path, prompt, max_retries=2)
                text = (text or "").strip()
                with lock:
                    completed += 1
                    if progress_callback and completed % 10 == 0:
                        progress_callback(completed, len(chunks), f"⏱️ {completed}/{len(chunks)}")
                return i, start_sec, end_sec, text
            except Exception as e:
                logger.error(f"Timestamp chunk {i} failed: {e}")
                with lock:
                    completed += 1
                return i, start_sec, end_sec, ""
        
        max_w = min(len(chunks), 16)
        with ThreadPoolExecutor(max_workers=max_w) as ex:
            futures = {ex.submit(transcribe_one, i, p): i for i, p in enumerate(chunks)}
            for future in as_completed(futures):
                i, start_sec, end_sec, text = future.result()
                if text:
                    results[i] = (start_sec, end_sec, text)
        
        logger.info(f"✅ {len(results)}/{len(chunks)} timestamp chunks transcribed")
        
        sorted_chunks = [(start, end, text) for i, (start, end, text) in sorted(results.items())]
        segments = align_cheap_to_good_text(full_text, sorted_chunks)
        
        result = {
            "text": full_text,
            "segments": segments,
            "segments_count": len(segments),
            "timestamp_method": "chunk_based",
        }
        if progress_callback:
            progress_callback(1, 1, f"✅ Chunk-based timestamp: {len(segments)} segments")
        return result

    def _process_file_internal(self, file_path, chunk_length, overlap, progress_callback, force, reuse_only=False):
        """Internal: the original process_file logic, returning plain text."""
        import shutil
        file_path = str(Path(file_path).resolve())
        work_dir = Path("work_dir") / Path(file_path).stem
        work_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = work_dir / "temp_chunks"
        progress_file = work_dir / "progress.json"
        
        if force:
            if progress_file.exists():
                logger.warning("Force mode enabled: Deleting previous progress.")
                try:
                    progress_file.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete progress file: {e}")
            if temp_dir.exists():
                logger.warning("Force mode enabled: Deleting cached audio chunks.")
                try:
                    shutil.rmtree(str(temp_dir))
                except OSError as e:
                    logger.warning(f"Failed to delete temp chunks: {e}")
        
        last_index, transcriptions, _, speaker_samples = self.load_progress(str(progress_file))
        if speaker_samples is None:
            speaker_samples = {}

        existing_chunks = sorted(temp_dir.glob("chunk_*.*")) if temp_dir.exists() else []
        if existing_chunks:
            logger.info(f"📂 Using {len(existing_chunks)} cached audio chunks (skipping re-split).")
            chunks = [str(p) for p in existing_chunks]
        else:
            chunks = media.split_audio_with_ffmpeg(
                file_path, chunk_length, overlap, str(temp_dir)
            )
        
        total_chunks = len(chunks)
        if progress_callback:
            progress_callback(0, total_chunks, "Starting transcription...")
        
        if last_index > 0:
            logger.info(f"▶ Resuming from chunk {last_index + 1}/{total_chunks} ({last_index} already done).")
            if progress_callback:
                progress_callback(last_index, total_chunks, f"Resuming from chunk {last_index+1}/{total_chunks}…")
            
        final_text_blocks = transcriptions[:]
        
        for i, chunk_path in enumerate(chunks):
            if i < last_index:
                continue
                
            chunk_name = Path(chunk_path).name
            logger.info(f"[{i+1}/{total_chunks}] Transcribing {chunk_name}…")
            if progress_callback:
                progress_callback(i, total_chunks, f"Transcribing chunk {i+1}/{total_chunks}...")
            
            current_prompt = self.build_prompt_with_context(
                self.transcription_prompt, i, speaker_samples
            )
            
            model = settings.llm.model
            text = self.transcribe_chunk_with_retry(model, chunk_path, current_prompt)
            
            new_speakers = self.extract_speaker_samples(text)
            speaker_samples.update(new_speakers)
            
            final_text_blocks.append(text)
            
            self.save_progress(str(progress_file), i + 1, final_text_blocks, speaker_samples=speaker_samples)
            if progress_callback:
                progress_callback(i + 1, total_chunks, f"Completed chunk {i+1}")
            
        full_text = self.merge_transcriptions(final_text_blocks, overlap)
        return full_text

    def _clean_json_block(self, text):
        """Attempts to clean markdown code blocks from JSON string."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
        
    def _merge_json_blocks(self, blocks):
        """Merges multiple JSON transcription blocks into one valid JSON object."""
        full_text = ""
        all_segments = []
        base_meta = {}
        
        for i, block_str in enumerate(blocks):
            try:
                clean_str = self._clean_json_block(block_str)
                data = json.loads(clean_str)
                
                if i == 0:
                    base_meta = data.get("meta", {})
                
                # Append text
                chunk_text = data.get("text", "")
                if full_text and chunk_text:
                    # heuristic: add space if missing
                    if not full_text.endswith(" ") and not chunk_text.startswith(" "):
                         full_text += " "
                full_text += chunk_text
                
                # Append segments
                # Note: This basic merge does NOT correct timestamps or IDs from chunks.
                # It simply aggregates them to produce valid JSON syntax.
                segs = data.get("segments", [])
                all_segments.extend(segs)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON chunk {i}: {e}")
                # Fallback: append raw text to full_text to avoid data loss
                full_text += f"\n[JSON PARSE ERROR IN CHUNK {i}]\n"
                
        merged = {
            "meta": base_meta,
            "text": full_text,
            "segments": all_segments
        }
        return json.dumps(merged, ensure_ascii=False, indent=2)

    def merge_transcriptions(self, blocks, overlap_sec):
        # Naive merge or smart overlap merge
        # For simplicity, using simple join for now as smart overlap requires text analysis
        # But we have `find_best_text_overlap_point`
        
        if not blocks:
            return ""
        
        # Check for JSON format in first block to determine strategy
        try:
            first_clean = self._clean_json_block(blocks[0])
            first_json = json.loads(first_clean)
            if isinstance(first_json, dict) and ("segments" in first_json or "text" in first_json):
                logger.info("Detected JSON output, using JSON merge strategy.")
                return self._merge_json_blocks(blocks)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Not JSON, proceed with text merge
            pass

        if len(blocks) == 1:
            return blocks[0]
            
        merged = blocks[0]
        # In this simplified flow, I'm just joining with newline for now because 
        # accurate overlap merging without the full timestamp logic (which was implicit or complex) might fail.
        # But wait, `find_best_text_overlap_point` was designed for this.
        
        # The overlap in audio is `overlap_sec`. The text overlap corresponds roughly to spoken words in that duration.
        # Let's try to use it.
        
        for i in range(1, len(blocks)):
            prev = merged
            curr = blocks[i]
            # Try to merge end of prev with start of curr
            # We don't know exact char length correlation to `overlap_sec`
            # But the function scans for match.
            merged, _ = find_best_text_overlap_point(prev, curr)
            # wait, `find_best_text_overlap_point` returns `text1_part, text2_part` to be joined?
            # My implementation: return text1[:start_in_text1 + match.size], text2[end_in_text2:]
            # So:
            p1, p2 = find_best_text_overlap_point(prev, curr)
            merged = p1 + p2
            
        return merged
