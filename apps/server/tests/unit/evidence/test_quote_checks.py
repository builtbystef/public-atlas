"""Quote and link matching, and the name-in-quote check."""

# ruff: noqa: RUF001 - the odd characters are the point

from public_atlas.integrations.browser import FrameLinks
from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.countries.schemas import NamingRules
from public_atlas.modules.evidence import capture, quote_checks
from public_atlas.modules.evidence.quote_checks import Found


def test_a_quote_matches_across_whitespace_case_and_unicode_width():
    text = "The  Regional\nMunicipality of  Fixture\twelcomes you"
    assert quote_checks.find_quote(text, "regional municipality of fixture") == Found(page=None)
    assert quote_checks.find_quote(text, "Ｍunicipality of Fixture") == Found(page=None)
    assert quote_checks.find_quote(text, "Municipality of Fixtures") is None


def test_a_quote_shorter_than_the_floor_is_a_stray_word_not_a_phrase():
    text = "The Town of Ajax met on Monday"
    assert quote_checks.find_quote(text, "the") is None
    assert quote_checks.find_quote(text, "of Ajax met") is None  # 11
    assert quote_checks.find_quote(text, "Town of Ajax") == Found(page=None)  # 12


def test_a_quote_in_a_multi_page_text_reports_its_page():
    text = "Cover page\fTable of contents\fOperating budget 2026: $1,200,000"
    assert quote_checks.find_quote(text, "operating budget 2026") == Found(page=3)
    assert quote_checks.find_quote(text, "nowhere at all") is None


def test_a_link_is_found_whatever_its_spelling():
    page = (
        "<a href=\"https://www.toronto.ca/\">Toronto</a> <a href='/agency'>A</a> "
        '<a href=https://ttc.ca/board?x=1#top>T</a> <a href="mailto:x@y">m</a>'
    )
    url = "https://example.org/list"
    assert quote_checks.link_in_html(page, url, "https://www.toronto.ca")
    assert quote_checks.link_in_html(page, url, "https://example.org/agency")
    assert quote_checks.link_in_html(page, url, "https://ttc.ca/board?x=1")
    assert not quote_checks.link_in_html(page, url, "https://ottawa.ca/")
    assert not quote_checks.link_in_html(page, url, "mailto:x@y")


def test_the_text_of_a_link_is_its_anchor_with_tags_stripped():
    page = (
        '<a href="/agency"><b>Fixture</b> Transit &amp; Rail</a> '
        '<a href="/empty"><img src="x.png"></a> '
        '<area href="/map"> <link href="/style.css">'
    )
    url = "https://example.org/list"
    assert (
        quote_checks.link_text(page, url, "https://example.org/agency") == "Fixture Transit & Rail"
    )
    # A link with no text is still a link; the caller quotes the URL instead.
    assert quote_checks.link_text(page, url, "https://example.org/empty") is None
    assert quote_checks.link_in_html(page, url, "https://example.org/empty")
    assert quote_checks.link_text(page, url, "https://example.org/map") is None
    assert quote_checks.link_in_html(page, url, "https://example.org/map")
    assert quote_checks.link_text(page, url, "https://example.org/nowhere") is None


def test_mentions_any_folds_case_and_spacing():
    assert quote_checks.mentions_any(
        "Welcome to the  TTC site", ["Toronto Transit Commission", "ttc"]
    )
    assert not quote_checks.mentions_any("Welcome", ["TTC", ""])


def test_a_url_in_a_file_is_a_link():
    """A directory in a spreadsheet or CSV has a website column; the cell is the link."""
    text = (
        "Municipality,Website\n"
        "Addington Highlands,http://www.addingtonhighlands.ca/\n"
        "Fixture,www.fixture.ca.\n"
        "Nowhere,see https://example.org/not-this|other\n"
    )
    page = "https://data.example.ca/dump.csv"
    assert quote_checks.link_in_text(text, page, "http://www.addingtonhighlands.ca/")
    # The scheme and a leading www. are not part of the match.
    assert quote_checks.link_in_text(text, page, "https://addingtonhighlands.ca")
    assert not quote_checks.link_in_text(text, page, "https://www.addingtonhighlands.ca/about")
    assert quote_checks.link_in_text(text, page, "http://www.fixture.ca")
    assert quote_checks.link_in_text(text, page, "https://example.org/not-this")
    assert not quote_checks.link_in_text(text, page, "https://example.org/other")
    assert not quote_checks.link_in_text(text, page, "https://www.nowhere.ca")


def test_a_quote_matches_across_typographic_punctuation_and_run_together_blocks():
    text = "Village of Burk’s Falls – est. 1890\n325 Farr Drive\nP.O. Box 2050\nHaileybury"
    assert quote_checks.find_quote(text, "Village of Burk's Falls - est. 1890") == Found(page=None)
    # The agent's view ran two blocks together where the page breaks a line.
    assert quote_checks.find_quote(text, "325 Farr DriveP.O. Box 2050Haileybury") == Found(
        page=None
    )
    assert quote_checks.find_quote(text, "325 Farr Drive P.O. Box 2051") is None


def test_the_navigate_tools_title_label_is_not_page_text():
    text = "Home | Town of Huntsville\n\nWelcome"
    assert quote_checks.find_quote(text, "Title: Home | Town of Huntsville") == Found(page=None)
    assert quote_checks.find_quote(text, "Title: Home | Town of Fixture") is None


def test_the_text_of_stored_html_keeps_a_hidden_footer_and_drops_scripts():
    page = (
        "<html><head><title>Town of Whitby</title><style>.x{}</style>"
        "<script>var secret = 'SCRIPT';</script></head><body><!-- note -->"
        '<p>Welcome &amp; hello</p><footer style="visibility:hidden">'
        "<div>&copy; 2026 Town of Whitby</div></footer></body></html>"
    )
    text = quote_checks.html_text(page)
    assert "SCRIPT" not in text
    assert ".x{}" not in text
    assert "note" not in text
    assert quote_checks.find_quote(text, "Welcome & hello") == Found(page=None)
    assert quote_checks.find_quote(text, "© 2026 Town of Whitby") == Found(page=None)


def test_the_closest_passage_shows_the_pages_own_wording():
    text = "News\nCouncil highlights\n© 2026 The Corporation of the Town of Whitby\nContact us"
    passage = quote_checks.closest_passage(text, "© 2026 Town of Whitby")
    assert passage is not None
    assert "2026 the corporation of the town of whitby contact us" in passage
    assert quote_checks.closest_passage(text, "nothing like this at all here") is None
    assert quote_checks.closest_passage("", "anything") is None


def test_an_address_written_in_the_quote_is_a_link():
    quote = "Township of Elmwood www.elmwood.ca 100 Main Street"
    page = "https://www.example.ca/closures"
    assert quote_checks.link_in_text(quote, page, "https://www.elmwood.ca/")
    assert not quote_checks.link_in_text(quote, page, "https://www.elmwood.com/")


def test_names_compare_across_slashes_and_mojibake_and_by_the_countrys_key():
    assert quote_checks.mentions_any("Municipality of Elm Oak: Home", ["Elm/Oak"])
    assert quote_checks.mentions_any("CafÃ© Elmwood, Township of", ["Café Elmwood"])
    assert quote_checks.find_quote("Café Elmwood, Township", "CafÃ© Elmwood, Township") == (
        Found(page=None)
    )
    # What "&" stands for is the country's: by default it is only itself.
    assert not quote_checks.mentions_any("Township of Elm & Oak", ["Elm and Oak"])
    naming = Naming(NamingRules(and_words=["and"]))
    assert quote_checks.mentions_any("Township of Elm & Oak", ["Elm and Oak"], key=naming.key)


def test_two_urls_name_the_same_page_scheme_www_and_slash_aside():
    assert quote_checks.same_address("http://www.elmwood.ca/about/", "https://elmwood.ca/about")
    assert not quote_checks.same_address("https://elmwood.ca/about", "https://elmwood.ca/about?x=1")


def test_a_run_together_match_still_respects_words():
    """The no-whitespace retry is for a block boundary run together inside the quote; it may
    not start or end in the middle of a word of the page."""
    assert quote_checks.find_quote("the publicity of a jaxon council", "City of Ajax") is None
    assert quote_checks.find_quote("Town of Ajaxville", "Town of Ajax") is None
    assert quote_checks.find_quote("The Downtown of Ajax", "Town of Ajax") is None
    assert quote_checks.find_quote("Meet the City of Ajax", "City of Ajax") == Found(page=None)
    # Punctuation is an edge: a quote ending at a full stop or an apostrophe is whole.
    assert quote_checks.find_quote("Meet the City of Ajax.", "City of Ajax") == Found(page=None)
    assert quote_checks.find_quote("City of Ajax's council", "City of Ajax") == Found(page=None)
    assert quote_checks.find_quote("©2026 City of Ajax", "2026 City of Ajax") == Found(page=None)
    # Run together inside, whole words at the edges: still a match.
    text = "Welcome\nCity of\nAjax council meets"
    assert quote_checks.find_quote(text, "City ofAjax council") == Found(page=None)
    assert quote_checks.find_quote("City ofAjax council", "City of Ajax council") == Found(
        page=None
    )


def test_a_link_in_a_script_or_comment_is_not_a_link():
    page = (
        '<script>var next = "https://example.org/in-script";</script>'
        '<style>a[href="https://example.org/in-style"] {}</style>'
        '<!-- <a href="https://example.org/in-comment">old</a> -->'
        '<p>href="https://example.org/in-text"</p>'
        '<a href="https://example.org/real">Real</a>'
    )
    url = "https://example.org/list"
    assert quote_checks.link_in_html(page, url, "https://example.org/real")
    assert quote_checks.link_text(page, url, "https://example.org/real") == "Real"
    for target in ("in-script", "in-style", "in-comment", "in-text"):
        assert not quote_checks.link_in_html(page, url, f"https://example.org/{target}"), target
        assert quote_checks.link_text(page, url, f"https://example.org/{target}") is None, target


def test_frame_links_are_linkable_but_not_quotable():
    """The links of a page's frames are appended to its stored copy as `<template>` blocks: the
    link check reads them, the page's text does not include them."""
    frames = (
        FrameLinks(
            "https://escribe.example/portal",
            (("https://escribe.example/m?id=1", "Council 2026-09-30"),),
        ),
    )
    page = "<html><body><h1>Meetings</h1></body></html>\n" + capture.frame_blocks(frames)
    url = "https://www.elmwood.ca/meetings"
    assert quote_checks.link_in_html(page, url, "https://escribe.example/portal")
    assert quote_checks.link_in_html(page, url, "https://escribe.example/m?id=1")
    assert (
        quote_checks.link_text(page, url, "https://escribe.example/m?id=1") == "Council 2026-09-30"
    )
    text = quote_checks.html_text(page)
    assert quote_checks.find_quote(text, "Meetings") is None  # too short, as any stray word
    assert "Council 2026-09-30" not in text
    assert "escribe.example" not in text
