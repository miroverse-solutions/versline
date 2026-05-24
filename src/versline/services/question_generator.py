"""Core logic for question generation."""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from versline.core.constants import (
    DEFAULT_MODELS,
    COST_PER_MILLION_TOKENS_IRT_AVALAI,
    COST_PER_MILLION_TOKENS_USD_AVALAI,
    USD_TO_IRT,
)
from versline.core.types import AIProvider, QuestionType
from versline.config import settings
from .ai import AIClient
from .pricing import lookup_avalai_cost, print_cost_report
from .document_processor import get_file_processor
from .export import save_to_csv, save_to_html
from versline.utils.anki import create_anki_package
from versline.utils.cache import CacheManager
from versline.core.prompts import load_prompt

from versline.resources.assets import load_css

PROMPTS_DIR = Path(__file__).parent.parent / "resources" / "prompts"

console = Console()

class QuestionDesigner:
    def __init__(
        self,
        input_path: str,
        output_dir: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy_url: Optional[str] = None,
        question_type: str = "mcq",
        language: str = "en",
        num_questions: Optional[int] = None,
        slides_per_batch: int = 10,
        pages_per_batch: int = 5,
        words_per_batch: int = 1000,
        output_formats: str = "all",
        style_path: Optional[str] = None,
        prompt_path: Optional[str] = None,
        force: bool = False,
        debug: bool = False,
        no_cache: bool = False,
        user_note: Optional[str] = None,
    ):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        
        # Resolve settings from global config if not provided
        resolved_provider = provider or settings.llm.provider or "openai"
        if resolved_provider.lower() == "google":
            resolved_provider = "gemini"
        self.provider = AIProvider(resolved_provider.lower())
        
        self.model = model or settings.llm.model
        self.api_key = api_key or settings.llm.api_key
        self.base_url = base_url or settings.llm.api_endpoint
        self.proxy_url = proxy_url or settings.llm.proxy
        
        self.question_type = QuestionType(question_type)
        self.language = language
        self.num_questions = num_questions
        self.slides_per_batch = slides_per_batch
        self.pages_per_batch = pages_per_batch
        self.words_per_batch = words_per_batch
        self.output_formats = [f.strip().lower() for f in output_formats.split(',')]
        self.style_path = style_path
        self.prompt_path = prompt_path
        self.force = force
        self.debug = debug
        self.no_cache = no_cache
        self.user_note = user_note
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Cache
        self.cache_manager = CacheManager(self.output_dir, no_cache)
        
        # Initialize AI Client
        self.client = AIClient(
            provider=self.provider.value,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            proxy_url=self.proxy_url,
        )
        
        # Load Prompts
        self._load_prompts()
    
    def _load_prompts(self):
        """Load system prompts from files."""
        try:
            self.doc_prompt = load_prompt("document_prompt.md")
            
            if self.prompt_path:
                with open(self.prompt_path, "r", encoding="utf-8") as f:
                    base_prompt = f.read()
                console.print(f"[cyan]Loaded custom prompt from {self.prompt_path}[/cyan]")
            else:
                p_file_name = f"{self.question_type.value}_prompt.md"
                base_prompt = load_prompt(p_file_name)
                
            # Customize prompt with language and number of questions
            self.system_prompt = base_prompt.replace("{{language}}", self.language)
            
            if self.num_questions:
                qty_text = f"Generate specific number of questions: {self.num_questions}. Ensure you generate exactly this amount if possible."
            else:
                qty_text = "Generate as many questions as possible to cover all key details and concepts found in the text."
                
            self.system_prompt = self.system_prompt.replace("{{num_questions}}", qty_text)

            if self.user_note:
                self.system_prompt += f"\n\n---\n\n**Additional instructions from user:**\n{self.user_note}"
            
        except Exception as e:
            console.print(f"[red]Error loading prompts: {e}[/red]")
            # Fallback for now if not found via load_prompt immediately
            # Try to read directly if load_prompt fails (though load_prompt handles it)
            raise

    def process(self):
        """Main processing loop."""
        input_files = []
        if self.input_path.is_file():
            input_files = [self.input_path]
        elif self.input_path.is_dir():
            # Recursively find supported files
            for ext in ['.pptx', '.pdf', '.docx', '.md', '.txt']:
                input_files.extend(self.input_path.rglob(f"*{ext}"))
        
        if not input_files:
            console.print(f"[yellow]No supported files found in {self.input_path}[/yellow]")
            return
        
        console.print(Panel(f"Found [bold]{len(input_files)}[/bold] files to process", title="Question Designer"))
        
        all_questions = []
        
        for file_path in input_files:
            try:
                # Check cache first
                cached_data = self.cache_manager.get(file_path, self.question_type.value, self.language)
                if cached_data and not self.force:
                    console.print(f"[green]Using cached questions for {file_path.name}[/green]")
                    all_questions.extend(cached_data)
                    continue

                console.print(f"\nProcessing: [bold cyan]{file_path.name}[/bold cyan]")
                
                # Extract text
                processor = get_file_processor(str(file_path))
                if not processor:
                    console.print(f"[red]No processor for {file_path.name}[/red]")
                    continue
                    
                chunks = processor.extract_text(
                    str(file_path),
                    slides_per_batch=self.slides_per_batch,
                    pages_per_batch=self.pages_per_batch,
                    words_per_batch=self.words_per_batch
                )
                if not chunks:
                    console.print(f"[yellow]No text extracted from {file_path.name}[/yellow]")
                    continue
                
                # Generate Questions
                file_questions = self._process_batches(chunks, file_path.name)
                
                if file_questions:
                    # Save to cache
                    self.cache_manager.set(file_path, self.question_type.value, self.language, file_questions)
                    all_questions.extend(file_questions)
                    
            except Exception as e:
                console.print(f"[red]Error processing {file_path.name}: {e}[/red]")
                if self.debug:
                    import traceback
                    traceback.print_exc()
        
        # Save Outputs
        if all_questions:
            self._save_outputs(all_questions)
            print_cost_report(self.client.tracker, self.api_key)
        else:
            console.print("\n[yellow]No questions generated.[/yellow]")

    def _process_batches(self, chunks: List[Dict[str, Any]], filename: str) -> List[Dict[str, Any]]:
        """Process text chunks with AI to generate questions."""
        questions = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
        ) as progress:
            task = progress.add_task(f"Generating questions for {filename}...", total=len(chunks))
            
            for i, chunk in enumerate(chunks):
                content = chunk['text']
                page_info = f"Source: {filename}, Page/Slide: {chunk.get('page', i+1)}"
                
                # Check cache for this chunk specifically? 
                # Currently we cache at file level. 
                
                # Send to AI
                batch_questions, _ = self.client.send_with_retry(
                    content=content,
                    prompt=self.system_prompt,
                    batch_info=page_info
                )
                
                # Post-process questions
                for q in batch_questions:
                    q['source_file'] = filename
                    q['source_page'] = chunk.get('page', i+1)
                    q['tags'] = [filename]
                    questions.append(q)
                
                progress.advance(task)
                
        return questions

    def _save_outputs(self, questions: List[Dict[str, Any]]):
        """Save questions to various formats."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base_name = f"questions_{self.question_type.value}_{timestamp}"
        
        save_all = "all" in self.output_formats
        
        # Load custom CSS if provided
        css_content = None
        if self.style_path:
            css_content = load_css(self.style_path)
            if css_content:
                console.print(f"[cyan]Loaded custom CSS from {self.style_path}[/cyan]")

        # CSV
        if save_all or "csv" in self.output_formats:
            csv_path = self.output_dir / f"{base_name}.csv"
            save_to_csv(questions, csv_path)
            console.print(f"[green]Saved CSV: {csv_path}[/green]")
        
        # HTML
        if save_all or "html" in self.output_formats:
            html_path = self.output_dir / f"{base_name}.html"
            save_to_html(questions, html_path, title=f"Generated Questions ({self.question_type.value})")
            console.print(f"[green]Saved HTML: {html_path}[/green]")
        
        # Anki
        if save_all or "anki" in self.output_formats or "apkg" in self.output_formats:
            anki_path = self.output_dir / f"{base_name}.apkg"
            deck_name = f"GenQ::{self.input_path.name}::{timestamp}"
            create_anki_package(questions, str(anki_path), deck_name, self.question_type, css=css_content)
            console.print(f"[green]Saved Anki Deck: {anki_path}[/green]")

    def regenerate_from_cache(self):
        """Regenerate outputs from cached data without calling AI."""
        input_files = []
        if self.input_path.is_file():
            input_files = [self.input_path]
        elif self.input_path.is_dir():
            for ext in ['.pptx', '.pdf', '.docx', '.md', '.txt']:
                input_files.extend(self.input_path.rglob(f"*{ext}"))
                
        all_questions = []
        for file_path in input_files:
            cached_data = self.cache_manager.get(file_path, self.question_type.value, self.language)
            if cached_data:
                console.print(f"[green]Loaded {len(cached_data)} questions from cache for {file_path.name}[/green]")
                all_questions.extend(cached_data)
        
        if all_questions:
            self._save_outputs(all_questions)
        else:
            console.print("[yellow]No cached data found.[/yellow]")

import time
