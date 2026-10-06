"""The model port: which model an assignment type runs on and how hard it reasons, and the
object that turns that choice into a Pydantic AI model with its settings."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from pydantic_ai.models import Model
    from pydantic_ai.settings import ModelSettings

type ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """A model, how hard it reasons, and the size of its context window. Product data: the
    assignment descriptors hold one per type."""

    name: str
    reasoning_effort: ReasoningEffort
    # In tokens. A session hands off once one of its requests passes half of it.
    context_window: int


class Models(Protocol):
    """Implement this to add a provider, then return it from `create_models`."""

    def model(self, choice: ModelChoice) -> Model: ...

    def settings(
        self, choice: ModelChoice, *, cache_key: str, send_item_ids: bool = True
    ) -> ModelSettings:
        """`cache_key` groups requests that share an instruction and tool prefix, so the provider
        serves that prefix from its cache. `send_item_ids` off sends the history as plain
        messages without the provider's item IDs, which a run on a different model than the one
        that produced the history needs."""
        ...
