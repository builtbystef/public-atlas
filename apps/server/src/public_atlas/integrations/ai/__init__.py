"""The model behind the agent: the port, the provider the settings have a key for, and the
in-memory double. Which model each assignment type runs on is product data in the assignment
descriptors; the settings only hold the key."""

from typing import TYPE_CHECKING

from public_atlas.integrations.ai.base import ModelChoice, Models, ReasoningEffort
from public_atlas.integrations.ai.memory import FixedModels
from public_atlas.integrations.ai.openai import OpenAIModels

if TYPE_CHECKING:
    from public_atlas.config import Settings


def create_models(settings: Settings) -> Models | None:
    """None when no key is configured: no assignment can run, and the runner says so."""
    if settings.openai_api_key is None:
        return None
    return OpenAIModels(settings.openai_api_key.get_secret_value())


__all__ = [
    "FixedModels",
    "ModelChoice",
    "Models",
    "OpenAIModels",
    "ReasoningEffort",
    "create_models",
]
