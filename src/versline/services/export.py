"""Output utilities for Versqude."""

import csv
from pathlib import Path
from typing import Optional

from versline.core.types import QuestionType
from versline.resources.assets import load_css


def format_question_html(
    question: dict,
    css_content: str,
    question_type: QuestionType
) -> dict:
    """Format question fields as styled HTML for Anki import."""
    styled_q = question.copy()
    
    style_tag = f"<style>{css_content}</style>" if css_content else ""
    
    if question_type == QuestionType.MCQ:
        # Format MCQ question
        q_text = question.get("question", "")
        styled_q["question"] = f'{style_tag}<div class="question">{q_text}</div>'
        
        option_labels = {"option_a": "الف", "option_b": "ب", "option_c": "ج", "option_d": "د"}
        
        for key, label in option_labels.items():
            opt_text = question.get(key, "")
            styled_q[key] = f'{style_tag}<div class="option"><span class="option-label">{label})</span> {opt_text}</div>'
        
        explanation = question.get("explanation", "")
        if explanation:
            styled_q["explanation"] = f'{style_tag}<div class="explanation">{explanation}</div>'
        
        correct = question.get("correct_answer", "").lower()
        correct_label = {"a": "الف", "b": "ب", "c": "ج", "d": "د"}.get(correct, correct)
        styled_q["correct_answer"] = f'{style_tag}<div class="correct-answer" style="text-align:center;font-size:20px;font-weight:bold;">{correct_label}</div>'
    
    else:
        # Format descriptive question
        q_text = question.get("question", "")
        styled_q["question"] = f'{style_tag}<div class="question">{q_text}</div>'
        
        answer = question.get("answer", "")
        if answer:
            styled_q["answer"] = f'{style_tag}<div class="answer">{answer}</div>'
    
    # Format difficulty
    difficulty = question.get("difficulty", "")
    if difficulty:
        diff_class = f"difficulty difficulty-{difficulty.lower()}"
        diff_labels = {"easy": "آسان", "medium": "متوسط", "hard": "سخت"}
        diff_label = diff_labels.get(difficulty.lower(), difficulty)
        styled_q["difficulty"] = f'{style_tag}<span class="{diff_class}">{diff_label}</span>'
    
    # Format topic
    topic = question.get("topic", "")
    if topic:
        styled_q["topic"] = f'{style_tag}<span class="topic">{topic}</span>'
    
    return styled_q


def save_to_csv(
    questions: list[dict],
    output_path: str,
    question_type: QuestionType = QuestionType.DESCRIPTIVE,
    css_path: Optional[str] = None,
    apply_styling: bool = False
):
    """Save questions to a CSV file.
    
    Args:
        questions: List of question dictionaries.
        output_path: Path to output CSV file.
        question_type: Type of questions (descriptive or MCQ).
        css_path: Path to custom CSS file (None for default).
        apply_styling: Whether to apply HTML styling for Anki.
    """
    if not questions:
        print("Warning: No questions to save!")
        return
    
    # Load CSS if styling is enabled
    css_content = ""
    if apply_styling:
        css_content = load_css(css_path)
        if css_content:
            print(f"📎 Applying HTML styling")
    
    all_keys = set()
    for q in questions:
        all_keys.update(q.keys())
    
    # Different column order for MCQ vs descriptive
    if question_type == QuestionType.MCQ:
        standard_columns = ["question", "option_a", "option_b", "option_c", "option_d", 
                          "correct_answer", "explanation", "difficulty", "topic", "batch"]
    else:
        standard_columns = ["question", "answer", "type", "difficulty", "topic", "batch"]
    
    columns = [col for col in standard_columns if col in all_keys]
    columns.extend([col for col in sorted(all_keys) if col not in columns])
    
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        
        for question in questions:
            if css_content:
                q_styled = format_question_html(question, css_content, question_type)
                row = {k: str(v) if v is not None else "" for k, v in q_styled.items()}
            else:
                row = {k: str(v) if v is not None else "" for k, v in question.items()}
            writer.writerow(row)
    
    print(f"\nSaved {len(questions)} questions to: {output_path}")
    if css_content:
        print(f"  ✨ HTML styling applied for Anki import")

def save_to_html(
    questions: list[dict], 
    output_path: str,
    title: str = "Versline Questions"
):
    """Save questions to a simple HTML file for preview."""
    
    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Tahoma, Arial, sans-serif; padding: 20px; line-height: 1.6; }}
        .question-card {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 20px; border-radius: 8px; background: #f9f9f9; }}
        .q-text {{ font-weight: bold; font-size: 1.1em; margin-bottom: 10px; color: #333; }}
        .options {{ margin-left: 20px; }}
        .option {{ margin: 5px 0; }}
        .correct {{ color: green; font-weight: bold; }}
        .meta {{ font-size: 0.9em; color: #666; margin-top: 10px; border-top: 1px dashed #eee; padding-top: 5px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
"""
    
    for i, q in enumerate(questions):
        html += '<div class="question-card">'
        html += f'<div class="q-text">{i+1}. {q.get("question", "")}</div>'
        
        # Check if MCQ
        if "option_a" in q:
            html += '<div class="options">'
            labels = {"option_a": "A", "option_b": "B", "option_c": "C", "option_d": "D"}
            correct = q.get("correct_answer", "").lower()
            
            for key, label in labels.items():
                opt_text = q.get(key, "")
                is_correct = (correct == label.lower() or correct == key) 
                # Basic check, might need better normalization
                style_attr = ' class="option correct"' if is_correct else ' class="option"'
                html += f'<div{style_attr}>{label}) {opt_text}</div>'
            html += '</div>'
            
            explanation = q.get("explanation", "")
            if explanation:
                 html += f'<div class="meta"><strong>توضیحات:</strong> {explanation}</div>'
        
        # Descriptive
        elif "answer" in q:
             html += f'<div class="meta"><strong>پاسخ:</strong> {q.get("answer", "")}</div>'
             
        html += '</div>'

    html += "</body></html>"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
