from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RinConfig:
    """
    Configuration for RIN project. This should be passed around explicitly.
    """
    # This existing 'model_name' might be for a general purpose or a default.
    # The specific model calls in ModelClient use shot0_model, shot1_model, big_model.
    model_name: str = "gpt-4.1-nano" # Keeping this as it was in your original file
    max_tokens: int = 6000
    temperature: float = 0.2
    top_p: float = 1.0
    stop_sequences: List[str] = field(default_factory=lambda: ["\n```", "\n\n"])

    # Linter config: map from language name to validation function name
    linter_map: Dict[str, str] = field(default_factory=lambda: {
        "python": "validate_python_code",
    })

    # Timeouts in seconds
    api_timeout: float = 15.0
    self_fix_timeout: float = 3.0

    # Gate thresholds (used in later sprints)
    fence_parity_required: bool = True
    run_linter_gate: bool = True

    # Specific models for different stages of the RIN pipeline
    # Updated based on the latest OpenAI model information (May 2025)
    shot0_model: str = "gpt-4.1-nano"  # For initial, fast attempts
    shot1_model: str = "gpt-4.1-nano"  # For self-correction attempts
    big_model: str = "gpt-4.1"         # More capable model for fallback

    def as_dict(self):
        # A common way to get a dictionary from a dataclass
        return self.__dict__