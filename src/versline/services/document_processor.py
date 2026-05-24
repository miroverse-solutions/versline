"""Document processors for different file formats."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from markitdown import MarkItDown


def convert_to_markdown(file_path: str) -> str:
    """Convert a file to Markdown using markitdown."""
    md = MarkItDown()
    result = md.convert(file_path)
    return result.text_content


def convert_ppt_to_pptx(ppt_path: str) -> str:
    """Convert legacy .ppt files to .pptx using LibreOffice CLI."""
    office_cmd = shutil.which("soffice") or shutil.which("libreoffice")
    if not office_cmd:
        raise RuntimeError(
            "Legacy .ppt requires LibreOffice (soffice) for conversion to .pptx"
        )

    output_dir = tempfile.mkdtemp(prefix="versline_ppt_convert_")
    cmd = [
        office_cmd,
        "--headless",
        "--convert-to",
        "pptx",
        "--outdir",
        output_dir,
        ppt_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(
            f"Failed to convert .ppt to .pptx via LibreOffice: {stderr or exc}"
        ) from exc

    expected_path = Path(output_dir) / f"{Path(ppt_path).stem}.pptx"
    if expected_path.exists():
        return str(expected_path)

    generated = list(Path(output_dir).glob("*.pptx"))
    if generated:
        return str(generated[0])

    shutil.rmtree(output_dir, ignore_errors=True)
    raise RuntimeError("LibreOffice conversion did not produce a .pptx file")


# ============================================================================
# PPTX Processing
# ============================================================================

def split_pptx_to_batches(pptx_path: str, slides_per_batch: int) -> list[str]:
    """Split a PPTX file into multiple smaller PPTX files.
    
    Returns list of temporary file paths.
    """
    from pptx import Presentation
    
    prs = Presentation(pptx_path)
    total_slides = len(prs.slides)
    temp_files = []
    
    for batch_start in range(0, total_slides, slides_per_batch):
        batch_end = min(batch_start + slides_per_batch, total_slides)
        
        batch_prs = Presentation()
        batch_prs.slide_width = prs.slide_width
        batch_prs.slide_height = prs.slide_height
        
        slides_to_copy = list(prs.slides)[batch_start:batch_end]
        
        for slide in slides_to_copy:
            slide_layout = batch_prs.slide_layouts[6]
            new_slide = batch_prs.slides.add_slide(slide_layout)
            
            for shape in slide.shapes:
                if shape.has_text_frame:
                    left, top = shape.left, shape.top
                    width, height = shape.width, shape.height
                    
                    txBox = new_slide.shapes.add_textbox(left, top, width, height)
                    tf = txBox.text_frame
                    
                    for para_idx, para in enumerate(shape.text_frame.paragraphs):
                        p = tf.paragraphs[0] if para_idx == 0 else tf.add_paragraph()
                        p.text = para.text
                        p.level = para.level
                        
                        if para.runs:
                            for run_idx, run in enumerate(para.runs):
                                if run_idx == 0 and p.runs:
                                    p.runs[0].font.bold = run.font.bold
                                    p.runs[0].font.italic = run.font.italic
                
                elif shape.has_table:
                    table = shape.table
                    rows, cols = len(table.rows), len(table.columns)
                    
                    new_table = new_slide.shapes.add_table(
                        rows, cols, shape.left, shape.top, shape.width, shape.height
                    ).table
                    
                    for row_idx, row in enumerate(table.rows):
                        for col_idx, cell in enumerate(row.cells):
                            new_table.cell(row_idx, col_idx).text = cell.text
        
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".pptx", delete=False, prefix=f"batch_{batch_start+1}-{batch_end}_"
        )
        batch_prs.save(temp_file.name)
        temp_files.append(temp_file.name)
        
        print(f"  Created batch: slides {batch_start+1}-{batch_end}")
    
    return temp_files


def process_pptx(pptx_path: str, slides_per_batch: int) -> list[tuple[str, str, list[str]]]:
    """Process PPTX file and return batches.
    
    Returns:
        List of (markdown_content, batch_info, temp_files_to_cleanup)
    """
    print(f"\n📂 Splitting PPTX into batches of {slides_per_batch} slides...")
    temp_files = split_pptx_to_batches(pptx_path, slides_per_batch)
    total_batches = len(temp_files)
    print(f"   Created {total_batches} batch(es)\n")
    
    batches = []
    for i, temp_file in enumerate(temp_files):
        batch_num = i + 1
        markdown = convert_to_markdown(temp_file)
        batch_info = f"Batch {batch_num} of {total_batches} (Slides)"
        batches.append((markdown, batch_info, batch_num))
    
    return batches, temp_files


# ============================================================================
# PDF Processing
# ============================================================================

def split_pdf_to_batches(pdf_path: str, pages_per_batch: int) -> list[tuple[str, int, int]]:
    """Split PDF into batches by pages.
    
    Returns list of (temp_file_path, start_page, end_page).
    """
    import fitz  # PyMuPDF
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    batches = []
    
    for batch_start in range(0, total_pages, pages_per_batch):
        batch_end = min(batch_start + pages_per_batch, total_pages)
        
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=batch_start, to_page=batch_end - 1)
        
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix=f"batch_{batch_start+1}-{batch_end}_"
        )
        new_doc.save(temp_file.name)
        new_doc.close()
        
        batches.append((temp_file.name, batch_start + 1, batch_end))
        print(f"  Created batch: pages {batch_start+1}-{batch_end}")
    
    doc.close()
    return batches


def process_pdf(pdf_path: str, pages_per_batch: int) -> tuple[list[tuple], list[str]]:
    """Process PDF file and return batches.
    
    Returns:
        Tuple of (batches, temp_files_to_cleanup)
        where batches is list of (markdown, batch_info, batch_num, page_range)
    """
    print(f"\n📂 Splitting PDF into batches of {pages_per_batch} pages...")
    pdf_batches = split_pdf_to_batches(pdf_path, pages_per_batch)
    total_batches = len(pdf_batches)
    print(f"   Created {total_batches} batch(es)\n")
    
    temp_files = [b[0] for b in pdf_batches]
    batches = []
    
    for i, (temp_file, start_page, end_page) in enumerate(pdf_batches):
        batch_num = i + 1
        markdown = convert_to_markdown(temp_file)
        batch_info = f"Batch {batch_num} of {total_batches} (Pages {start_page}-{end_page})"
        batches.append((markdown, batch_info, batch_num, f"{start_page}-{end_page}"))
    
    return batches, temp_files


# ============================================================================
# DOCX Processing
# ============================================================================

def convert_docx_batch_to_markdown(paragraphs: list[tuple[str, str]]) -> str:
    """Convert a batch of DOCX paragraphs to Markdown."""
    lines = []
    
    for text, style in paragraphs:
        if not text.strip():
            lines.append("")
            continue
        
        # Convert heading styles
        if "Heading 1" in style:
            lines.append(f"# {text}")
        elif "Heading 2" in style:
            lines.append(f"## {text}")
        elif "Heading 3" in style:
            lines.append(f"### {text}")
        elif "Heading 4" in style:
            lines.append(f"#### {text}")
        elif "List" in style:
            lines.append(f"- {text}")
        else:
            lines.append(text)
        
        lines.append("")
    
    return "\n".join(lines)


def split_docx_to_batches(docx_path: str, pages_per_batch: int) -> list[tuple[str, int, int]]:
    """Split DOCX into batches by estimated pages.
    
    Returns list of (markdown_content, start_page, end_page).
    """
    from docx import Document
    
    doc = Document(docx_path)
    
    paragraphs = [(p.text, p.style.name if p.style else "Normal") for p in doc.paragraphs]
    
    words_per_page = 300
    words_per_batch = pages_per_batch * words_per_page
    
    batches = []
    current_batch = []
    current_words = 0
    batch_start_page = 1
    current_page = 1
    
    for text, style in paragraphs:
        word_count = len(text.split())
        current_batch.append((text, style))
        current_words += word_count
        
        current_page = batch_start_page + (current_words // words_per_page)
        
        if current_words >= words_per_batch:
            md_content = convert_docx_batch_to_markdown(current_batch)
            end_page = current_page
            batches.append((md_content, batch_start_page, end_page))
            print(f"  Created batch: pages {batch_start_page}-{end_page} (estimated)")
            
            current_batch = []
            current_words = 0
            batch_start_page = end_page + 1
    
    if current_batch:
        md_content = convert_docx_batch_to_markdown(current_batch)
        end_page = max(batch_start_page, current_page)
        batches.append((md_content, batch_start_page, end_page))
        print(f"  Created batch: pages {batch_start_page}-{end_page} (estimated)")
    
    return batches


def process_docx(docx_path: str, pages_per_batch: int) -> tuple[list[tuple], list[str]]:
    """Process DOCX file and return batches.
    
    Returns:
        Tuple of (batches, temp_files_to_cleanup)
        where batches is list of (markdown, batch_info, batch_num, page_range)
    """
    print(f"\n📂 Splitting DOCX into batches of ~{pages_per_batch} pages...")
    docx_batches = split_docx_to_batches(docx_path, pages_per_batch)
    total_batches = len(docx_batches)
    print(f"   Created {total_batches} batch(es)\n")
    
    batches = []
    for i, (content, start_page, end_page) in enumerate(docx_batches):
        batch_num = i + 1
        batch_info = f"Batch {batch_num} of {total_batches} (Pages {start_page}-{end_page} estimated)"
        batches.append((content, batch_info, batch_num, f"{start_page}-{end_page}"))
    
    return batches, []


# ============================================================================
# Markdown Processing
# ============================================================================

def split_markdown_to_batches(md_path: str, words_per_batch: int) -> list[tuple[str, int, int]]:
    """Split Markdown file into batches by word count.
    
    Returns list of (content, start_word, end_word).
    """
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    words = content.split()
    total_words = len(words)
    batches = []
    
    for batch_start in range(0, total_words, words_per_batch):
        batch_end = min(batch_start + words_per_batch, total_words)
        
        batch_content = " ".join(words[batch_start:batch_end])
        batches.append((batch_content, batch_start + 1, batch_end))
        print(f"  Created batch: words {batch_start+1}-{batch_end}")
    
    return batches


def process_markdown(md_path: str, words_per_batch: int) -> tuple[list[tuple], list[str]]:
    """Process Markdown file and return batches.
    
    Returns:
        Tuple of (batches, temp_files_to_cleanup)
        where batches is list of (content, batch_info, batch_num, word_range)
    """
    print(f"\n📂 Splitting Markdown into batches of {words_per_batch} words...")
    md_batches = split_markdown_to_batches(md_path, words_per_batch)
    total_batches = len(md_batches)
    print(f"   Created {total_batches} batch(es)\n")
    
    batches = []
    for i, (content, start_word, end_word) in enumerate(md_batches):
        batch_num = i + 1
        batch_info = f"Batch {batch_num} of {total_batches} (Words {start_word}-{end_word})"
        batches.append((content, batch_info, batch_num, f"{start_word}-{end_word}"))
    
    return batches, []

# ============================================================================
# Generic Processor Interface
# ============================================================================

from typing import List, Dict, Any, Union

class FileProcessor:
    def extract_text(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        raise NotImplementedError

class PDFProcessor(FileProcessor):
    def extract_text(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        pages_per_batch = kwargs.get('pages_per_batch', 5)
        batches, temp_files = process_pdf(file_path, pages_per_batch=pages_per_batch)
        # Cleanup temp files
        for t in temp_files:
            try:
                os.remove(t)
            except OSError: 
                pass
        return [{"text": b[0], "page": b[3]} for b in batches]

class PPTXProcessor(FileProcessor):
    def extract_text(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        ext = Path(file_path).suffix.lower()
        if ext == ".ppt":
            converted_pptx = convert_ppt_to_pptx(file_path)
            converted_dir = str(Path(converted_pptx).parent)
            slides_per_batch = kwargs.get('slides_per_batch', 10)

            try:
                batches, temp_files = process_pptx(converted_pptx, slides_per_batch=slides_per_batch)
                for t in temp_files:
                    try:
                        os.remove(t)
                    except OSError:
                        pass
                return [{"text": b[0], "page": b[1]} for b in batches]
            finally:
                if os.path.isdir(converted_dir):
                    shutil.rmtree(converted_dir, ignore_errors=True)

        slides_per_batch = kwargs.get('slides_per_batch', 10)
        batches, temp_files = process_pptx(file_path, slides_per_batch=slides_per_batch)
        for t in temp_files:
            try:
                os.remove(t)
            except OSError: 
                pass
        return [{"text": b[0], "page": b[1]} for b in batches]

class DOCXProcessor(FileProcessor):
    def extract_text(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        pages_per_batch = kwargs.get('pages_per_batch', 5)
        batches, _ = process_docx(file_path, pages_per_batch=pages_per_batch)
        return [{"text": b[0], "page": b[3]} for b in batches]

class MarkdownProcessor(FileProcessor):
    def extract_text(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        words_per_batch = kwargs.get('words_per_batch', 1000)
        batches, _ = process_markdown(file_path, words_per_batch=words_per_batch)
        return [{"text": b[0], "page": b[3]} for b in batches]

def get_file_processor(file_path: str) -> Union[FileProcessor, None]:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return PDFProcessor()
    elif ext in [".pptx", ".ppt"]:
        return PPTXProcessor()
    elif ext == ".docx":
        return DOCXProcessor()
    elif ext in [".md", ".txt", ".markdown"]:
        return MarkdownProcessor()
    return None
