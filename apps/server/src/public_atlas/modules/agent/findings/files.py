"""`read_file` and `search`: documents on allowed domains, and web search within or beyond them
(spec section 8.1). Search belongs to `find_homepage` alone and is billed per request."""

from dataclasses import dataclass

from pydantic_ai import RunContext

from public_atlas.integrations.search import SearchFailed, SearchResult
from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.agent.findings.shared import FindingError
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import UsageKind
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service as graph

SEARCH_RESULTS = 8
MAX_SEARCH_DOMAINS = 3
# Every search an assignment makes, on allowed domains or the whole web, counts against this: the
# engine bills per request. The site's own name usually turns up in the first search or two; the
# rest cover a misspelt or older name and the parent's directory.
MAX_SEARCHES = 5


async def read_file(
    ctx: RunContext[SessionContext], url: str, chunk: int = 1
) -> evidence.FileResult:
    """Download a PDF, spreadsheet, Word file, CSV, feed or other document on an
    allowed domain and return one chunk of its text. Documents open here, not in
    the browser. Call again with the next `chunk` for more.

    Args:
        url: The document's URL.
        chunk: Which chunk of the text to return, from 1.
    """
    deps = ctx.deps
    return await evidence.read_file(
        deps.res, deps.file_policy(), url=url, chunk=chunk, assignment_id=deps.assignment_id
    )


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """What a search returned: leads, never evidence."""

    results: list[SearchResult]
    whole_web: bool
    note: str | None = None

    def __str__(self) -> str:
        if self.note:
            return self.note
        if not self.results:
            return "No results." if self.whole_web else "No results on those domains."
        lines = [f"- {r.title}\n  {r.url}\n  {r.snippet}" for r in self.results]
        if not self.whole_web:
            return "\n".join(lines)
        return (
            "Leads, not evidence. These results' sites are open to you now: open the likely one "
            "and judge it (home page with and without www, about, contact, the footer). When it "
            "is the institution's own site, save it with save_homepage (no linking page is "
            "needed for a search result), which makes it your candidate; then decide it with "
            "confirm_domain, domain_moved or reject_domain. A dead or unrelated result needs no "
            "saving. Prefer a page on an allowed domain that links to the site or writes its "
            "address out, saved with found_on_url: a trusted link lets your confirmation verify "
            "it without a human.\n" + "\n".join(lines)
        )


async def search(
    ctx: RunContext[SessionContext], query: str, domains: list[str] | None = None
) -> SearchOutcome:
    """Web search limited to the given domains (up to three), each of which must be
    an allowed domain, or of the whole web when no domains are passed, for the
    institution's own homepage. Results are leads, not evidence: the sites they are
    on open for you from then on, so open a result and judge it before saving
    anything. An assignment gets five searches in all, so make each one count:
    name the place and the institution.

    Args:
        query: What to look for, e.g. "Township of Elmwood official website".
        domains: Domains to search within, e.g. ["ontario.ca"]; empty for the whole web.
    """
    return await search_web(ctx.deps, query, domains or [])


async def search_web(ctx: SessionContext, query: str, domains: list[str]) -> SearchOutcome:
    searcher = ctx.searcher
    if searcher is None:
        return SearchOutcome(
            [],
            whole_web=not domains,
            note=(
                "Error: no search engine is configured. Browse the site's own pages and search box."
            ),
        )
    if ctx.searches >= MAX_SEARCHES:
        return SearchOutcome(
            [],
            whole_web=not domains,
            note=(
                f"Error: this assignment has made its {MAX_SEARCHES} searches. Browse the allowed "
                "domains' own pages and search boxes instead, or save what you have."
            ),
        )
    wanted = list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))[
        :MAX_SEARCH_DOMAINS
    ]
    for domain in wanted:
        if not any(_covers(domain, allowed) for allowed in ctx.allowed_domains):
            raise FindingError(f"{domain} is not an allowed domain; search is limited to those.")
    query = " ".join(query.split())
    if not query:
        raise FindingError("query must say what to look for.")
    # One request for every domain: the engine bills per request and honours `site:` filters
    # joined with OR.
    if wanted:
        sites = " OR ".join(f"site:{domain}" for domain in wanted)
        sent = f"{query} ({sites})" if len(wanted) > 1 else f"{query} {sites}"
    else:
        sent = query
    ctx.searches += 1
    async with ctx.session() as session:
        await assignments.record_usage(
            session,
            assignment_id=ctx.assignment_id,
            kind=UsageKind.SEARCH,
            provider=searcher.name,
            purpose=ctx.descriptor.type.value,
            units=1,
        )
        await session.commit()
    try:
        found = await searcher.search(sent, count=SEARCH_RESULTS * max(len(wanted), 1))
    except SearchFailed as exc:
        return SearchOutcome([], whole_web=not wanted, note=f"Error: {exc}")
    results = [
        r
        for r in found
        if not wanted or any(_covers(graph.host_of(r.url), domain) for domain in wanted)
    ]
    # The results' sites join the session's allowlist, so the agent judges a site itself
    # instead of saving it blind for a check that opens it later.
    for result in results:
        host = graph.host_of(result.url)
        if host:
            name = graph.candidate_domain_name(host)
            ctx.search_hosts.add(name)
            ctx.allow_domain(name)
    return SearchOutcome(results, whole_web=not wanted)


def _covers(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")
