from enum import Enum

class QuestionType(Enum):
    """Type of questions to generate."""
    DESCRIPTIVE = "descriptive"
    MCQ = "mcq"

    @classmethod
    def _missing_(cls, value):
        """Accept legacy aliases and case-insensitive values."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            alias_map = {
                "open": cls.DESCRIPTIVE,
                "open-ended": cls.DESCRIPTIVE,
                "open_ended": cls.DESCRIPTIVE,
                "descriptive": cls.DESCRIPTIVE,
                "mcq": cls.MCQ,
            }
            return alias_map.get(normalized)
        return None

class AIProvider(Enum):
    """Supported AI providers."""
    OPENAI = "openai"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    AVALAI = "avalai"
    CUSTOM = "custom"
