from enum import Enum

class QuestionType(Enum):
    """Type of questions to generate."""
    DESCRIPTIVE = "descriptive"
    MCQ = "mcq"

class AIProvider(Enum):
    """Supported AI providers."""
    OPENAI = "openai"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    AVALAI = "avalai"
    CUSTOM = "custom"
