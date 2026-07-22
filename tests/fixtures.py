"""Hand-curated evaluation fixture for entity resolution.

IMPORTANT PROVENANCE NOTE: these records are hand-written to reproduce the
failure modes seen when reconciling Discogs / MusicBrainz / Last.fm / Spotify,
using real album metadata. They are NOT a random sample of any live API. The
set is deliberately adversarial -- it over-represents hard cases relative to a
real collection, so scores here should be read as a lower bound on a
representative sample, not as an estimate of production accuracy.

Every pair carries a ground-truth label and a short note on why it is hard.
"""

from __future__ import annotations

# --- Source records ------------------------------------------------------
# `id` is unique within a source. Sparse fields reflect what each API actually
# supplies: Last.fm gives no track counts or durations at all.

DISCOGS = [
    {
        "id": "d1",
        "title": "In Rainbows",
        "artist": "Radiohead",
        "year": 2007,
        "track_count": 10,
        "total_duration_sec": 2559,
        "catalogue_number": "XLLP 324",
    },
    {
        "id": "d2",
        "title": "The Dark Side Of The Moon",
        "artist": "Pink Floyd",
        "year": 1973,
        "track_count": 10,
        "total_duration_sec": 2569,
        "catalogue_number": "SHVL 804",
    },
    {
        "id": "d3",
        "title": "Weezer",
        "artist": "Weezer",
        "year": 1994,
        "track_count": 10,
        "total_duration_sec": 2610,
        "catalogue_number": "GED 24629",
    },
    {
        "id": "d4",
        "title": "Weezer",
        "artist": "Weezer",
        "year": 2001,
        "track_count": 10,
        "total_duration_sec": 1770,
        "catalogue_number": "9362-47965-2",
    },
    {
        "id": "d5",
        "title": "Kind Of Blue",
        "artist": "Miles Davis",
        "year": 1959,
        "track_count": 5,
        "total_duration_sec": 2724,
        "catalogue_number": "CL 1355",
    },
    {
        "id": "d6",
        "title": "Kid A",
        "artist": "Radiohead",
        "year": 2000,
        "track_count": 10,
        "total_duration_sec": 2999,
        "catalogue_number": "XLLP 782",
    },
    {
        "id": "d7",
        "title": "The Velvet Underground & Nico",
        "artist": "The Velvet Underground",
        "year": 1967,
        "track_count": 11,
        "total_duration_sec": 2884,
        "catalogue_number": "V6-5008",
    },
    {
        "id": "d8",
        "title": "Rumours",
        "artist": "Fleetwood Mac",
        "year": 1977,
        "track_count": 11,
        "total_duration_sec": 2359,
        "catalogue_number": "BSK 3010",
    },
    {
        "id": "d9",
        "title": "Homogenic",
        "artist": "Björk",
        "year": 1997,
        "track_count": 10,
        "total_duration_sec": 2622,
        "catalogue_number": "ELEKTRA 62061",
    },
    {
        "id": "d10",
        "title": "Discovery",
        "artist": "Daft Punk",
        "year": 2001,
        "track_count": 14,
        "total_duration_sec": 3654,
        "catalogue_number": "7243 8 49606 1 4",
    },
]

MUSICBRAINZ = [
    {
        # Same album, remaster edition marker, 9 years later. Must match d1.
        "id": "m1",
        "title": "In Rainbows (2016 Remaster)",
        "artist": "Radiohead",
        "year": 2016,
        "track_count": 10,
        "total_duration_sec": 2559,
        "catalogue_number": None,
    },
    {
        # 38-year gap, identical content. The hardest positive in the set.
        "id": "m2",
        "title": "The Dark Side of the Moon [Remastered]",
        "artist": "Pink Floyd",
        "year": 2011,
        "track_count": 10,
        "total_duration_sec": 2572,
        "catalogue_number": None,
    },
    {
        # Blue Album. Same title AND same track count as the Green Album.
        "id": "m3",
        "title": "Weezer",
        "artist": "Weezer",
        "year": 1994,
        "track_count": 10,
        "total_duration_sec": 2610,
        "catalogue_number": None,
    },
    {
        # Reissue adds an alternate take -> track count differs by 1.
        "id": "m4",
        "title": "Kind of Blue",
        "artist": "Miles Davis",
        "year": 1997,
        "track_count": 6,
        "total_duration_sec": 3045,
        "catalogue_number": None,
    },
    {
        # "The" dropped by the source. Must still match d7.
        "id": "m5",
        "title": "The Velvet Underground & Nico",
        "artist": "Velvet Underground",
        "year": 1967,
        "track_count": 11,
        "total_duration_sec": 2884,
        "catalogue_number": None,
    },
    {
        # Diacritic dropped. Must still match d9.
        "id": "m6",
        "title": "Homogenic",
        "artist": "Bjork",
        "year": 1997,
        "track_count": 10,
        "total_duration_sec": 2622,
        "catalogue_number": None,
    },
    {
        # Deluxe edition with bonus disc -> track count and runtime both differ.
        "id": "m7",
        "title": "Discovery (Deluxe Edition)",
        "artist": "Daft Punk",
        "year": 2001,
        "track_count": 16,
        "total_duration_sec": 4180,
        "catalogue_number": None,
    },
    {
        # Live album sharing a name fragment with a studio record. Negative.
        "id": "m8",
        "title": "Rumours Live",
        "artist": "Fleetwood Mac",
        "year": 2023,
        "track_count": 13,
        "total_duration_sec": 2890,
        "catalogue_number": None,
    },
]

LASTFM = [
    # Last.fm supplies artist + album strings only. No counts, no durations.
    {"id": "l1", "title": "In Rainbows", "artist": "Radiohead", "year": None,
     "track_count": None, "total_duration_sec": None, "catalogue_number": None},
    {"id": "l2", "title": "Dark Side of the Moon", "artist": "Pink Floyd", "year": None,
     "track_count": None, "total_duration_sec": None, "catalogue_number": None},
    {"id": "l3", "title": "Kid A", "artist": "Radiohead", "year": None,
     "track_count": None, "total_duration_sec": None, "catalogue_number": None},
    {"id": "l4", "title": "Homogenic", "artist": "Björk", "year": None,
     "track_count": None, "total_duration_sec": None, "catalogue_number": None},
]

SPOTIFY = [
    {
        # Catalogue number agrees with d1 -> should short-circuit to accept.
        "id": "s1",
        "title": "In Rainbows",
        "artist": "Radiohead",
        "year": 2007,
        "track_count": 10,
        "total_duration_sec": 2559,
        "catalogue_number": "XLLP324",
    },
]

RECORDS_BY_SOURCE = {
    "discogs": DISCOGS,
    "musicbrainz": MUSICBRAINZ,
    "lastfm": LASTFM,
    "spotify": SPOTIFY,
}

# --- Ground truth --------------------------------------------------------
# (left_key, right_key, is_same_album, why_it_is_hard)

LABELLED_PAIRS: list[tuple[str, str, bool, str]] = [
    # -- Positives ------------------------------------------------------
    ("discogs:d1", "musicbrainz:m1", True, "remaster marker + 9y year gap"),
    ("discogs:d1", "lastfm:l1", True, "sparse source, no counts or duration"),
    ("discogs:d1", "spotify:s1", True, "catalogue number match, spacing differs"),
    ("discogs:d2", "musicbrainz:m2", True, "38y gap, 'The' placement, bracket marker"),
    ("discogs:d2", "lastfm:l2", True, "sparse + leading 'The' dropped from title"),
    ("discogs:d3", "musicbrainz:m3", True, "self-titled, identical metadata"),
    ("discogs:d5", "musicbrainz:m4", True, "reissue adds a track, +38y, +5min"),
    ("discogs:d7", "musicbrainz:m5", True, "'The' dropped from artist"),
    ("discogs:d9", "musicbrainz:m6", True, "diacritic dropped from artist"),
    ("discogs:d9", "lastfm:l4", True, "diacritic + sparse source"),
    ("discogs:d10", "musicbrainz:m7", True, "deluxe edition, +2 tracks, +9min"),
    ("discogs:d6", "lastfm:l3", True, "sparse source, exact title"),
    # -- Negatives ------------------------------------------------------
    ("discogs:d3", "discogs:d4", False, "SAME source -- must never be compared"),
    ("discogs:d4", "musicbrainz:m3", False, "Green vs Blue: same title, same count"),
    ("discogs:d8", "musicbrainz:m8", False, "studio vs live, shared title fragment"),
    ("discogs:d1", "musicbrainz:m2", False, "different artists entirely"),
    ("discogs:d6", "musicbrainz:m1", False, "same artist, both 10 tracks, diff album"),
    ("discogs:d1", "lastfm:l3", False, "same artist, different album"),
    ("discogs:d5", "musicbrainz:m7", False, "unrelated, different decade"),
    ("discogs:d7", "musicbrainz:m8", False, "unrelated"),
]
