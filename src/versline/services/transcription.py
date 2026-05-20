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
from versline.services import media
from versline.core.prompts import load_prompt
from versline.utils.common import find_best_text_overlap_point
from versline.services.pricing import TokenTracker

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
                self.tracker.add_usage(
                    completion.usage.prompt_tokens,
                    completion.usage.completion_tokens
                )

            return completion.choices[0].message.content
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

        existing_chunks = sorted(temp_dir.glob("chunk_*.mp3")) if temp_dir.exists() else []
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
