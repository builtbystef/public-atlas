"""The test double: one model, usually a scripted `FunctionModel`, stands in for every choice."""

from typing import TYPE_CHECKING

from pydantic_ai.settings import ModelSettings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

    from public_atlas.integrations.ai.base import ModelChoice


class FixedModels:
    def __init__(self, model: Model) -> None:
        self._model = model
        # Every choice asked for, so a test can check which model a session wanted.
        self.choices: list[ModelChoice] = []

    def model(self, choice: ModelChoice) -> Model:
        self.choices.append(choice)
        return self._model

    def settings(
        self,
        choice: ModelChoice,  # noqa: ARG002 - the port's signature
        *,
        cache_key: str,  # noqa: ARG002
        send_item_ids: bool = True,  # noqa: ARG002
    ) -> ModelSettings:
        return ModelSettings()
