"""The one adapter between the findings and Pydantic AI (spec section 8.1): the browser's tools
and the findings are registered by the names the descriptor lists, and every typed result is
rendered to text (or an image) at this edge. There is no wrapper layer."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai import BinaryContent, RunContext
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from public_atlas.integrations.browser import TOOLS as BROWSING
from public_atlas.integrations.browser import Browser, Screenshot
from public_atlas.modules.agent import findings
from public_atlas.modules.agent.context import SessionContext

logger = logging.getLogger(__name__)

# A tool's refusals are retried this many times before the run gives up on it.
TOOL_RETRIES = 3

# The findings by the names the descriptors use.
FINDINGS: dict[str, Callable[..., Awaitable[Any]]] = {
    "status": findings.status,
    "finish": findings.finish,
    "request_review": findings.request_review,
    "save_institution": findings.save_institution,
    "save_homepage": findings.save_homepage,
    "save_source": findings.save_source,
    "confirm_domain": findings.confirm_domain,
    "reject_domain": findings.reject_domain,
    "domain_moved": findings.domain_moved,
    "read_file": findings.read_file,
    "search": findings.search,
}


def render(result: object) -> str | BinaryContent:
    """A typed result as the model sees it: a screenshot as an image, everything else as the
    text the result renders itself to."""
    if isinstance(result, Screenshot):
        return BinaryContent(data=result.png, media_type="image/png")
    return str(result)


class Adapter(FunctionToolset[SessionContext]):
    """The agent's toolset: counts the calls and renders what each tool returns."""

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[SessionContext],
        tool: ToolsetTool[SessionContext],
    ) -> Any:  # noqa: ANN401 - the base class's signature
        ctx.deps.tool_calls += 1
        return render(await super().call_tool(name, tool_args, ctx, tool))


def toolset(ctx: SessionContext, browser: Browser) -> Adapter:
    """The tools the descriptor lists, out of the browser's and the findings. `search` is left
    out when no search engine is configured."""
    adapter = Adapter(max_retries=TOOL_RETRIES)
    for name in ctx.descriptor.tools:
        if name in BROWSING:
            adapter.add_function(getattr(browser, name), name=name, takes_ctx=False)
        elif name == "search" and ctx.searcher is None:
            continue
        elif name in FINDINGS:
            adapter.add_function(FINDINGS[name], name=name, takes_ctx=True)
        else:  # pragma: no cover - the descriptor test keeps the names in step
            logger.warning("Tool %s is not registered; the session runs without it", name)
    return adapter
