"""Tests for normalization, scoring, and clustering.

The regression tests at the bottom encode failures the evaluation harness
actually caught. Each one names the case it protects against.
"""

from __future__ import annotations

import pytest

from turntable.resolve.cluster import UnionFind, build_clusters
from turntable.resolve.normalize import (
    blocking_keys,
    normalize_artist,
    normalize_title,
)
from turntable.resolve.scoring import jaro_winkler, score_pair

# --- Normalization -------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("In Rainbows", "in rainbows"),
        ("In Rainbows (2007 Remaster)", "in rainbows"),
        ("In Rainbows [Remastered]", "in rainbows"),
        ("IN RAINBOWS", "in rainbows"),
        ("In  Rainbows", "in rainbows"),
        ("The Dark Side of the Moon", "the dark side of the moon"),
        ("Discovery (Deluxe Edition)", "discovery"),
        ("Abbey Road (Disc 1)", "abbey road"),
    ],
)
def test_normalize_title_strips_noise(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


def test_normalize_title_preserves_identity_parentheticals() -> None:
    """Regression: stripping all parentheticals merges distinct albums.

    'Weezer (Blue Album)' and 'Weezer (Green Album)' are different records.
    Blind parenthetical removal collapses both to 'weezer'.
    """
    assert normalize_title("Weezer (Blue Album)") == "weezer blue album"
    assert normalize_title("Weezer (Green Album)") == "weezer green album"
    assert normalize_title("Weezer (Blue Album)") != normalize_title(
        "Weezer (Green Album)"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("The Velvet Underground", "velvet underground"),
        ("Velvet Underground", "velvet underground"),
        ("Björk", "bjork"),
        ("Bjork", "bjork"),
        ("Mötley Crüe", "motley crue"),
        ("Nirvana (2)", "nirvana"),
        ("Sigur Rós", "sigur ros"),
    ],
)
def test_normalize_artist(raw: str, expected: str) -> None:
    assert normalize_artist(raw) == expected


def test_blocking_keys_bridge_reissue_year_gap() -> None:
    """A 1973 original and its 2011 remaster must share at least one key."""
    original = blocking_keys("Pink Floyd", 1973)
    remaster = blocking_keys("Pink Floyd", 2011)
    assert original & remaster, "reissues would never be compared"


# --- String similarity ---------------------------------------------------

def test_jaro_winkler_bounds() -> None:
    assert jaro_winkler("kind of blue", "kind of blue") == 1.0
    assert jaro_winkler("", "anything") == 0.0
    assert 0.0 <= jaro_winkler("rumours", "rumours live") <= 1.0


def test_jaro_winkler_rewards_shared_prefix() -> None:
    shared = jaro_winkler("in rainbows", "in rainbows disc")
    unshared = jaro_winkler("in rainbows", "zzz rainbows")
    assert shared > unshared


# --- Scoring -------------------------------------------------------------

def test_catalogue_number_short_circuits() -> None:
    left = {"title": "In Rainbows", "artist": "Radiohead",
            "catalogue_number": "XLLP 324"}
    right = {"title": "wildly different", "artist": "Radiohead",
             "catalogue_number": "XLLP324"}
    result = score_pair(left, right)
    assert result.verdict == "accept"
    assert "catalogue" in result.notes[0]


def test_missing_features_are_dropped_not_zeroed() -> None:
    """Last.fm supplies no counts or durations. It must not be penalized."""
    rich = {
        "title": "Homogenic",
        "artist": "Björk",
        "year": 1997,
        "track_count": 10,
        "total_duration_sec": 2622,
    }
    sparse = {"title": "Homogenic", "artist": "Bjork"}
    result = score_pair(rich, sparse)
    assert result.verdict == "accept"
    assert "track_count" not in result.features


def test_explanation_is_always_populated() -> None:
    result = score_pair(
        {"title": "A", "artist": "X", "year": 2000},
        {"title": "B", "artist": "Y", "year": 1980},
    )
    assert result.features
    assert 0.0 <= result.score <= 1.0


# --- Regressions ---------------------------------------------------------

def test_regression_self_titled_albums_do_not_merge() -> None:
    """REGRESSION: Weezer Blue (1994) vs Green (2001) auto-merged at 0.850.

    Identical title, identical artist, identical track count. The only
    distinguishing signal is runtime -- 2610s vs 1770s, fourteen minutes
    apart -- and at weight 0.10 it could not overcome agreement everywhere
    else. Fixed by making severe runtime disagreement a multiplicative veto
    rather than a low-weighted feature.
    """
    blue = {
        "title": "Weezer",
        "artist": "Weezer",
        "year": 1994,
        "track_count": 10,
        "total_duration_sec": 2610,
    }
    green = {
        "title": "Weezer",
        "artist": "Weezer",
        "year": 2001,
        "track_count": 10,
        "total_duration_sec": 1770,
    }
    result = score_pair(blue, green)
    assert result.verdict != "accept", (
        f"self-titled albums auto-merged at {result.score}"
    )
    assert any("runtime contradiction" in note for note in result.notes)


def test_regression_legitimate_reissues_survive_the_veto() -> None:
    """The runtime veto must not break genuine reissues.

    Kind of Blue gains an alternate take on reissue (+5 min, ~10% longer);
    Discovery's deluxe edition adds a bonus disc (~13% longer). Both are the
    same album and must stay under the contradiction threshold.
    """
    kind_of_blue = {
        "title": "Kind of Blue", "artist": "Miles Davis", "year": 1959,
        "track_count": 5, "total_duration_sec": 2724,
    }
    reissue = {
        "title": "Kind of Blue", "artist": "Miles Davis", "year": 1997,
        "track_count": 6, "total_duration_sec": 3045,
    }
    result = score_pair(kind_of_blue, reissue)
    assert not any("runtime contradiction" in n for n in result.notes)
    assert result.verdict in {"accept", "review"}


# --- Clustering ----------------------------------------------------------

def test_union_find_groups_transitively() -> None:
    uf = UnionFind()
    uf.union("a", "b")
    uf.union("b", "c")
    uf.union("x", "y")
    groups = {frozenset(members) for members in uf.groups().values()}
    assert frozenset({"a", "b", "c"}) in groups
    assert frozenset({"x", "y"}) in groups


def test_clusters_never_merge_within_a_source() -> None:
    """Two records from the same source are distinct by construction."""
    records = {
        "discogs": [
            {"id": "1", "title": "Weezer", "artist": "Weezer", "year": 1994,
             "track_count": 10, "total_duration_sec": 2610},
            {"id": "2", "title": "Weezer", "artist": "Weezer", "year": 2001,
             "track_count": 10, "total_duration_sec": 1770},
        ]
    }
    index = {"weezer": {"discogs:1", "discogs:2"}}
    clusters, _ = build_clusters(records, index)
    for cluster in clusters:
        assert len(cluster.members) == 1
