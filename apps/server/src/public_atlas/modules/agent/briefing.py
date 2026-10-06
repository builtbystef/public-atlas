"""What a session is told (spec section 8): the standing instructions of its assignment type and
country, and a briefing with the subject, the checklist of types still to account for, the pages
already visited and the last handoff note. Never the old transcript. The full port of v1's
prompts in the glossary's words comes with the second half of phase 4."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent import findings
from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.assignments.models import Assignment
from public_atlas.modules.evidence.models import Snapshot
from public_atlas.modules.graph.models import EntityStatus, Homepage, Institution, Place, Webpage

COMMON = """\
You are Public Atlas, an agent building a verified map of public institutions and the web \
pages that carry procurement signals about them. You work one assignment per session. \
Everything you save goes to a database that outlives this session; the database is your \
memory, not this conversation.

Rules enforced in code, so work with them:
- You reach only the allowed domains the briefing lists. navigate refuses every other site \
and the refusal is recorded. A link elsewhere is not a dead end: save it as a homepage with \
the tool for that, and another assignment decides it.
- Every finding needs a quote that exists word for word on a page you opened. Copy text \
exactly as get_text or navigate returned it; do not paraphrase, translate or trim words from \
inside a phrase. A quote is at least twelve characters and, for a place, institution or \
homepage, contains a name or acronym of the thing saved. The backend checks the quote \
against the stored copy of the page and refuses what it cannot find, answering with the \
closest passage so you can copy the page's own words.
- Only code or a human marks something verified. A quote from a trusted domain verifies \
what it names; you never set a status yourself.
- Only the backend creates work; you never spawn it. Your assignment ends with the \
finishing tool your goal names.

How to work:
- Read directories and lists with navigate, snapshot and get_text. Page through every \
"next" and "load more" until a list ends.
- Save as you go, one call per finding. A session can restart, and unsaved findings are lost.
- PDFs, spreadsheets and other files open with read_file, not in the browser.
- When you are unsure whether something belongs, request_review with what you saw; do not \
skip it silently.
- status() tells you what this assignment has saved and opened; use it before repeating \
work, and after a restart.
- Use screenshot only when snapshot and get_text do not explain a page.
"""


def instructions(ctx: SessionContext) -> str:
    """The standing text of an assignment type and country. It is the same for every session of
    that type, so the provider can cache it."""
    rules = ctx.rules
    parts = [COMMON, "Your goal:", ctx.descriptor.goal, ""]
    parts.append(f"Country: {rules.name} ({rules.country_code}).")
    parts.append(
        "Administrative levels, from the top (level: government type; institution types "
        "expected at a place of the level):"
    )
    parts.extend(
        f"- {level.name}: {level.government_institution_type}; "
        f"{', '.join(level.expected_institution_types) or 'none'}"
        for level in rules.levels_by_rank
    )
    parts.append(
        "Institution types this country uses (type: what it is; the source types expected for "
        "it; what its names look like, when stated). A body of a listed type at another level "
        "is still saved with that type and goes to review:"
    )
    for name, use in sorted(rules.uses.items()):
        line = f"- {name}: {rules.institution_types.get(name, '')}; "
        line += ", ".join(use.expected_source_types) or "no sources expected"
        if use.name_pattern is not None:
            line += f"; names match /{use.name_pattern.pattern}/"
        parts.append(line)
    parts.append(
        "- other: a public body that buys things and fits none of the types above; pass "
        "suggested_type with it (the kind of body, in a few words). It goes to review, where a "
        "human adds the type. Only when no listed type fits."
    )
    parts.append("Source types (what counts as each one, in any language):")
    parts.extend(f"- {name}: {text}" for name, text in sorted(rules.source_types.items()))
    if rules.platforms:
        parts.append(
            (
                "Platforms (fetchable, never trusted; a page on one becomes a source only when a "
                "trusted page links to it): "
            )
            + ", ".join(rules.platforms)
        )
    return "\n".join(parts)


async def briefing(ctx: SessionContext, session: AsyncSession) -> str:
    """The user prompt of a session: the subject, the checklist still open, the pages this
    assignment opened already, and the previous session's handoff note."""
    assignment = await session.get_one(Assignment, ctx.assignment_id)
    parts = [f"Assignment: {ctx.descriptor.type.value}."]
    parts.extend(await _subject_lines(ctx, session))
    remaining = await findings.remaining_checklist(ctx, session)
    if remaining:
        parts.append("Types still to account for: " + ", ".join(remaining) + ".")
    parts.append("Allowed domains: " + (", ".join(ctx.allowed_domains) or "none") + ".")
    visited = list(
        await session.scalars(
            select(Webpage.url)
            .join(Snapshot, Snapshot.webpage_id == Webpage.id)
            .where(Snapshot.assignment_id == assignment.id)
            .distinct()
            .order_by(Webpage.url)
            .limit(findings.MAX_VISITED)
        )
    )
    if visited:
        parts.append("Pages this assignment opened already:")
        parts.extend(f"- {url}" for url in visited)
    if assignment.handoff_note:
        parts.append(f"Handoff note from the previous session: {assignment.handoff_note}")
    parts.append(
        f"Budget left: {max(assignment.budget_requests - assignment.requests_used, 0)} requests."
    )
    return "\n".join(parts)


async def _subject_lines(ctx: SessionContext, session: AsyncSession) -> list[str]:
    place = ctx.place
    if isinstance(ctx.subject, Place):
        lines = [f"Subject: the place {place.name!r}, a {place.administrative_level}."]
        if place.government_institution_id is not None:
            government = await session.get_one(Institution, place.government_institution_id)
            lines.append(f"Its government: {government.name!r}.")
            lines.extend(await _homepage_lines(session, government))
        return lines
    institution = ctx.subject
    subject = (
        f"Subject: the institution {institution.name!r} ({institution.institution_type}), at "
        f"{place.name!r} ({place.administrative_level})."
    )
    lines = [subject]
    lines.extend(await _homepage_lines(session, institution))
    return lines


async def _homepage_lines(session: AsyncSession, institution: Institution) -> list[str]:
    claims = await session.execute(
        select(Homepage, Webpage.url)
        .join(Webpage, Webpage.id == Homepage.webpage_id)
        .where(Homepage.institution_id == institution.id)
        .order_by(Homepage.id)
    )
    lines = []
    for homepage, url in claims.all():
        if homepage.id == institution.homepage_id:
            lines.append(f"Homepage (verified): {url}")
        elif homepage.status in (EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW):
            lines.append(f"Candidate homepage ({homepage.status.value}): {url}")
        elif homepage.status is EntityStatus.REJECTED:
            lines.append(f"Rejected homepage claim: {url} ({homepage.rejected_reason})")
    if not lines:
        lines.append("Homepage: none known yet.")
    return lines
