"""Anki output generation for Versqude."""

import random
import genanki
from typing import List, Dict, Any, Optional
from versline.core.types import QuestionType

# CSS for Anki cards
DEFAULT_CSS = """
.card {
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
}

.question {
    font-weight: bold;
    margin-bottom: 20px;
    padding: 10px;
    background-color: #f0f0f0;
    border-radius: 5px;
    direction: rtl;
}

.options {
    text-align: right;
    direction: rtl;
    margin: 20px auto;
    display: inline-block;
}

.option {
    margin: 5px 0;
    padding: 5px;
}

.answer, .explanation {
    margin-top: 20px;
    padding: 10px;
    border-top: 1px solid #ddd;
    direction: rtl;
}

.correct-answer {
    color: green;
    font-weight: bold;
}

.meta {
    font-size: 12px;
    color: #888;
    margin-top: 30px;
    direction: rtl;
}

.difficulty-easy { color: green; }
.difficulty-medium { color: orange; }
.difficulty-hard { color: red; }
"""

def _get_model_id() -> int:
    """Generate a random model ID."""
    return random.randrange(1 << 30, 1 << 31)

def _get_deck_id() -> int:
    """Generate a random deck ID."""
    return random.randrange(1 << 30, 1 << 31)

def get_mcq_model(css: str = DEFAULT_CSS) -> genanki.Model:
    """Create Anki model for MCQ questions."""
    return genanki.Model(
        1607392319,  # Stable ID for this model
        'Versqude MCQ Model',
        fields=[
            {'name': 'Question'},
            {'name': 'OptionA'},
            {'name': 'OptionB'},
            {'name': 'OptionC'},
            {'name': 'OptionD'},
            {'name': 'CorrectAnswer'},
            {'name': 'Explanation'},
            {'name': 'Topic'},
            {'name': 'Difficulty'},
        ],
        templates=[
            {
                'name': 'Card 1',
                'qfmt': """
<div class="question">{{Question}}</div>
<div class="options">
    <div class="option">الف) {{OptionA}}</div>
    <div class="option">ب) {{OptionB}}</div>
    <div class="option">ج) {{OptionC}}</div>
    <div class="option">د) {{OptionD}}</div>
</div>
""",
                'afmt': """
{{FrontSide}}
<hr id=answer>
<div class="answer">
    پاسخ صحیح: <span class="correct-answer">{{CorrectAnswer}}</span>
</div>
<div class="explanation">
    {{Explanation}}
</div>
<div class="meta">
    موضوع: {{Topic}} | سختی: <span class="difficulty-{{Difficulty}}">{{Difficulty}}</span>
</div>
""",
            },
        ],
        css=css
    )

def get_descriptive_model(css: str = DEFAULT_CSS) -> genanki.Model:
    """Create Anki model for descriptive questions."""
    return genanki.Model(
        1607392320,  # Stable ID for this model
        'Versqude Descriptive Model',
        fields=[
            {'name': 'Question'},
            {'name': 'Answer'},
            {'name': 'Topic'},
            {'name': 'Difficulty'},
        ],
        templates=[
            {
                'name': 'Card 1',
                'qfmt': '<div class="question">{{Question}}</div>',
                'afmt': """
{{FrontSide}}
<hr id=answer>
<div class="answer">{{Answer}}</div>
<div class="meta">
    موضوع: {{Topic}} | سختی: <span class="difficulty-{{Difficulty}}">{{Difficulty}}</span>
</div>
""",
            },
        ],
        css=css
    )

def create_anki_notes(
    questions: List[Dict[str, Any]],
    question_type: QuestionType = QuestionType.DESCRIPTIVE,
    model: Optional[genanki.Model] = None,
    css: Optional[str] = None
) -> List[genanki.Note]:
    """Create a list of Anki notes from questions.
    
    Args:
        questions: List of question dictionaries.
        question_type: Type of questions.
        model: Optional genanki.Model (if None, creates one based on type/css).
        css: Optional CSS string (only used if model is None).
        
    Returns:
        List of genanki.Note objects.
    """
    if model is None:
        if css is None:
            css = DEFAULT_CSS
        
        if question_type == QuestionType.MCQ:
            model = get_mcq_model(css)
        else:
            model = get_descriptive_model(css)
            
    notes = []
    for q in questions:
        if question_type == QuestionType.MCQ:
            note = genanki.Note(
                model=model,
                fields=[
                    q.get('question', ''),
                    q.get('option_a', ''),
                    q.get('option_b', ''),
                    q.get('option_c', ''),
                    q.get('option_d', ''),
                    q.get('correct_answer', ''),
                    q.get('explanation', ''),
                    q.get('topic', ''),
                    q.get('difficulty', '')
                ]
            )
        else:
            note = genanki.Note(
                model=model,
                fields=[
                    q.get('question', ''),
                    q.get('answer', ''),
                    q.get('topic', ''),
                    q.get('difficulty', '')
                ]
            )
        notes.append(note)
        
    return notes

def create_anki_package(
    questions: List[Dict[str, Any]],
    output_path: str,
    deck_name: str = "Versqude Deck",
    question_type: QuestionType = QuestionType.DESCRIPTIVE,
    css: Optional[str] = None
):
    """Create an Anki package (.apkg) from questions."""
    
    # Use default CSS if none provided
    if css is None:
        css = DEFAULT_CSS
    
    # Select model based on question type
    if question_type == QuestionType.MCQ:
        model = get_mcq_model(css)
    else:
        model = get_descriptive_model(css)

    deck = genanki.Deck(
        _get_deck_id(),
        deck_name
    )
    
    # Create notes
    notes = create_anki_notes(questions, question_type, model=model)
    
    for note in notes:
        deck.add_note(note)

    # Save to file
    genanki.Package(deck).write_to_file(output_path)
    print(f"📦 Created Anki package: {output_path}")
