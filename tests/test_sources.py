"""Tests for the source clients' mappers and the release-type rule.

Network calls aren't tested here -- CI has no network and live APIs are
non-deterministic. What IS tested is the pure logic that turns raw API JSON into
the resolver's record shape, plus the release-type contradiction that the first
real-data run made necessary. Those are the parts that carry the risk.
"""

from __future__ import annotations

from turntable.resolve.scoring import score_pair
from turntable.sources.base import special_types
from turntable.sources.discogs import DiscogsClient
from turntable.sources.musicbrainz import MusicBrainzClient

# --- special_types normalisation -----------------------------------------

def test_special_types_marks_live_and_compilation() -> None:
    assert special_types(["LP", "Album", "Live"]) == "live"
    assert special_types(["Compilation", "Remix"]) == "compilation,remix"


def test_special_types_studio_album_is_empty() -> None:
    # a plain studio album carries no special tag -> '' (not None)
    assert special_types(["LP", "Album", "Reissue"]) == ""
    assert special_types([]) == ""


# --- Discogs mapper ------------------------------------------------------

def test_discogs_to_record_preserves_catalogue_and_derives_tracks() -> None:
    detail = {
        "id": 249504,
        "title": "In Rainbows",
        "artists": [{"name": "Radiohead"}],
        "year": 2007,
        "labels": [{"catno": "XLLP 324"}],
        "formats": [{"descriptions": ["LP", "Album"]}],
        "tracklist": [
            {"type_": "track", "duration": "4:15"},
            {"type_": "track", "duration": "5:15"},
            {"type_": "heading", "duration": ""},  # not a track
        ],
    }
    rec = DiscogsClient.to_record(detail, source_id="d0")
    assert rec["catalogue_number"] == "XLLP 324"
    assert rec["track_count"] == 2  # heading excluded
    assert rec["total_duration_sec"] == 4 * 60 + 15 + 5 * 60 + 15
    assert rec["release_type"] == ""  # studio album


def test_discogs_to_record_marks_live_pressing() -> None:
    detail = {
        "id": 1, "title": "Live at Leeds", "artists": [{"name": "The Who"}],
        "year": 1970, "formats": [{"descriptions": ["LP", "Album", "Live"]}],
        "tracklist": [],
    }
    assert DiscogsClient.to_record(detail)["release_type"] == "live"


# --- MusicBrainz mapper --------------------------------------------------

def test_musicbrainz_to_record_studio_vs_live_types() -> None:
    studio_rg = {
        "id": "rg1", "title": "In Rainbows",
        "artist-credit": [{"name": "Radiohead"}],
        "first-release-date": "2007-10-10", "secondary-types": [],
    }
    rec = MusicBrainzClient.to_record(studio_rg, None, source_id="m0")
    assert rec["year"] == 2007
    assert rec["catalogue_number"] is None  # not a release-group concept
    assert rec["release_type"] == ""

    live_rg = {**studio_rg, "title": "Live in Rainbows", "secondary-types": ["Live"]}
    assert MusicBrainzClient.to_record(live_rg, None)["release_type"] == "live"


def test_musicbrainz_track_count_from_media() -> None:
    rg = {"id": "rg", "title": "X", "artist-credit": [{"name": "Y"}],
          "first-release-date": "2000", "secondary-types": []}
    release = {"media": [{"track-count": 10,
                          "tracks": [{"length": 200000}, {"length": 100000}]}]}
    rec = MusicBrainzClient.to_record(rg, release)
    assert rec["track_count"] == 10
    assert rec["total_duration_sec"] == 300  # (200000+100000) ms -> 300 s


# --- Release-type contradiction in the resolver --------------------------

def test_release_type_contradiction_demotes_studio_vs_live() -> None:
    """REGRESSION (real data): 'In Rainbows' must not auto-merge with 'Live in
    Rainbows' just because title/artist/year agree. The release-type rule is what
    stops it."""
    studio = {"title": "In Rainbows", "artist": "Radiohead",
              "year": 2007, "release_type": ""}
    live = {"title": "Live in Rainbows", "artist": "Radiohead",
            "year": 2008, "release_type": "live"}
    result = score_pair(studio, live)
    assert result.verdict != "accept"
    assert any("release-type contradiction" in n for n in result.notes)


def test_release_type_matching_types_not_penalised() -> None:
    a = {"title": "In Rainbows", "artist": "Radiohead", "year": 2007,
         "release_type": ""}
    b = {"title": "In Rainbows", "artist": "Radiohead", "year": 2016,
         "release_type": ""}
    result = score_pair(a, b)
    assert not any("release-type contradiction" in n for n in result.notes)


def test_release_type_rule_is_noop_without_the_field() -> None:
    """The hand-built fixture has no release_type key; the rule must not fire,
    so the fixture evaluation stays unaffected."""
    a = {"title": "Weezer", "artist": "Weezer", "year": 1994, "track_count": 10}
    b = {"title": "Weezer", "artist": "Weezer", "year": 1994, "track_count": 10}
    result = score_pair(a, b)
    assert not any("release-type" in n for n in result.notes)
