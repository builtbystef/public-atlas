"""A quote shown in the context of the page it was taken from."""

from public_atlas.integrations.parse import PAGE_SEPARATOR
from public_atlas.modules.evidence.service import quote_context


def test_the_quote_is_found_with_the_text_around_it():
    text = "Welcome to the\n\n  Town of Elmwood.   Council meets on Mondays.\nContact us."
    context = quote_context(text, "town of ELMWOOD", chars=12)
    assert context.found
    assert (context.before, context.quote, context.after) == (
        "come to the ",
        "Town of Elmwood",
        ". Council me",
    )
    assert context.page is None


def test_a_quote_on_a_later_page_names_its_page():
    text = PAGE_SEPARATOR.join(["Cover page.", "Budget 2026: capital plan."])
    context = quote_context(text, "Budget 2026: capital plan")
    assert (context.found, context.page) == (True, 2)
    assert context.before == ""


def test_a_quote_the_text_no_longer_has_comes_back_alone():
    context = quote_context("Nothing of the kind here.", "Town of Elmwood")
    assert not context.found
    assert (context.before, context.quote, context.after) == ("", "Town of Elmwood", "")
