"""URLs in one spelling, the domain a host creates, and the path a platform homepage vouches
for."""

import pytest

from public_atlas.modules.graph.service import (
    candidate_domain_name,
    normalize_url,
    trusted_path_of,
    under_trusted_path,
)


def test_normalize_url():
    assert normalize_url("HTTPS://WWW.Elmwood.CA") == "https://www.elmwood.ca/"
    assert normalize_url("www.elmwood.ca/en/#top") == "http://www.elmwood.ca/en/"
    assert normalize_url("https://elmwood.ca:443/a?b=1") == "https://elmwood.ca/a?b=1"
    assert normalize_url("http://elmwood.ca:8080/") == "http://elmwood.ca:8080/"


def test_candidate_domain_name():
    assert candidate_domain_name("www.elmwood.ca") == "elmwood.ca"
    assert candidate_domain_name("en.elmwood.ca") == "en.elmwood.ca"
    assert candidate_domain_name("WWW.ELMWOOD.CA") == "elmwood.ca"


@pytest.mark.parametrize(
    ("url", "prefix"),
    [
        (
            "https://sites.google.com/view/elmwoodlibrary/home",
            "https://sites.google.com/view/elmwoodlibrary/",
        ),
        (
            "https://sites.google.com/view/elmwoodlibrary",
            "https://sites.google.com/view/elmwoodlibrary/",
        ),
        ("https://www.youtube.com/@TownOfElmwood", "https://www.youtube.com/@TownOfElmwood/"),
        (
            "https://www.youtube.com/channel/UCabc123/videos",
            "https://www.youtube.com/channel/UCabc123/videos/",
        ),
        (
            "https://elmwood.wixsite.com/library/index.html?lang=en",
            "https://elmwood.wixsite.com/library/",
        ),
        ("https://www.facebook.com/ElmwoodFire/", "https://www.facebook.com/ElmwoodFire/"),
    ],
)
def test_trusted_path_of(url: str, prefix: str):
    assert trusted_path_of(url) == prefix


def test_a_platforms_root_is_nobodys_homepage():
    with pytest.raises(ValueError, match="root"):
        trusted_path_of("https://www.youtube.com/")


def test_under_trusted_path():
    prefix = "https://sites.google.com/view/elmwoodlibrary/"
    assert under_trusted_path("https://sites.google.com/view/elmwoodlibrary", prefix)
    assert under_trusted_path("https://sites.google.com/view/elmwoodlibrary/board?x=1", prefix)
    assert not under_trusted_path("https://sites.google.com/view/elmwoodlibraryfriends", prefix)
    assert not under_trusted_path("https://sites.google.com/view/other/", prefix)
