"""OpenAI through the Responses API."""

from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from public_atlas.integrations.ai.base import ModelChoice

if TYPE_CHECKING:
    from pydantic_ai.models import Model
    from pydantic_ai.settings import ModelSettings

# Retries of a request the API refused with 429 or a 5xx, with backoff. The client's default of
# 2 is not enough: parallel sessions share one organization's tokens-per-minute limit, and a
# refusal that reaches the agent fails the session and costs the job an attempt.
MAX_RETRIES = 8


class OpenAIModels:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, max_retries=MAX_RETRIES)
        self._models: dict[str, Model] = {}

    def model(self, choice: ModelChoice) -> Model:
        found = self._models.get(choice.name)
        if found is None:
            found = self._models[choice.name] = OpenAIResponsesModel(
                choice.name, provider=OpenAIProvider(openai_client=self._client)
            )
        return found

    def settings(
        self, choice: ModelChoice, *, cache_key: str, send_item_ids: bool = True
    ) -> ModelSettings:
        return OpenAIResponsesModelSettings(
            openai_reasoning_effort=choice.reasoning_effort,
            openai_prompt_cache_key=cache_key,
            openai_send_reasoning_ids=send_item_ids,
        )
