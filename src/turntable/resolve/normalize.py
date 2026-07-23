"""Title and artist normalization.

Every downstream matching decision depends on this module, which is why it is
the most heavily tested part of the codebase. Normalization here is
deliberately *lossy in one direction only*: we strip things that are reliably
noise (format annotations, edition markers, punctuation variance) and preserve
anything that could legitimately distinguish two releases.

The asymmetry matters. Over-stripping merges genuinely different records --
`Weezer (Blue Album)` and `Weezer (Green Album)` collapse to `weezer` if you
strip parentheticals blindly. Under-stripping leaves duplicates, which the
scorer can still recover from downstream. So when in doubt, strip less.
"""

from __future__ import annotations

import re
import unicodedata

# Edition/format annotations that carry no identity information. Ordered
# longest-first so that "deluxe edition" is consumed before "edition".
_NOISE_PHRASES = [
    "deluxe edition",
    "expanded edition",
    "special edition",
    "limited edition",
    "collector's edition",
    "anniversary edition",
    "remastered version",
    "digital remaster",
    "bonus track version",
    "deluxe version",
    "original soundtrack",
    "mono version",
    "stereo version",
    "remastered",
    "remaster",
    "reissue",
    "explicit",
    "clean",
]

# Disc/side markers. These *are* stripped: a multi-disc set is one album.
_DISC_MARKER = re.compile(
    r"\b(disc|disk|cd|lp|side)\s*[\divx]+\b",
    re.IGNORECASE,
)

# Trailing format annotations in brackets or parens, e.g. "(2007 Remaster)".
# Only stripped when the contents look like noise -- see _strip_annotations.
_BRACKETED = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")

# Artist prefixes that vary by source. Discogs disambiguates duplicate artist
# names with a numeric suffix: "Nirvana (2)".
_DISCOGS_ARTIST_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")

_THE_PREFIX = re.compile(r"^the\s+", re.IGNORECASE)

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def _fold_unicode(text: str) -> str:
    """Decompose accents and drop combining marks.

    Björk -> bjork, Mötley Crüe -> motley crue. Music metadata is wildly
    inconsistent about diacritics across sources, so folding them is close to
    mandatory. The information loss is real but has never once mattered in
    practice -- no two distinct artists in this dataset differ only by accent.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _is_noise_annotation(inner: str) -> bool:
    """Decide whether a bracketed phrase is disposable.

    Conservative by design. `(Blue Album)` and `(Live at Leeds)` are identity;
    `(2007 Remaster)` and `(Bonus Track Version)` are not. We only strip when
    the contents match a known noise phrase or are purely a year/format token.
    """
    cleaned = inner.strip().lower()
    if not cleaned:
        return True
    if any(phrase in cleaned for phrase in _NOISE_PHRASES):
        return True
    # Bare year, or year + noise word: "2007", "2007 remaster"
    if re.fullmatch(r"(19|20)\d{2}(\s+\w+)?", cleaned):
        return any(p in cleaned for p in _NOISE_PHRASES) or cleaned.isdigit()
    # Pure format tokens
    return cleaned in {"vinyl", "cd", "digital", "cassette", "lp", "ep", "single"}


def _strip_annotations(title: str) -> str:
    """Remove bracketed noise while preserving identity-bearing parentheticals."""

    def replace(match: re.Match[str]) -> str:
        return "" if _is_noise_annotation(match.group(1)) else match.group(0)

    return _BRACKETED.sub(replace, title)


def normalize_title(title: str) -> str:
    """Reduce a release title to a comparable form.

    >>> normalize_title("In Rainbows (2007 Remaster)")
    'in rainbows'
    >>> normalize_title("Weezer (Blue Album)")
    'weezer blue album'
    >>> normalize_title("OK Computer OKNOTOK 1997 2017")
    'ok computer oknotok 1997 2017'
    """
    if not title:
        return ""

    text = _fold_unicode(title)
    text = _strip_annotations(text)
    text = _DISC_MARKER.sub(" ", text)

    for phrase in _NOISE_PHRASES:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text, flags=re.IGNORECASE)

    text = _PUNCT.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip().lower()


def normalize_artist(artist: str) -> str:
    """Reduce an artist name to a comparable form.

    Drops a leading 'The' -- sources disagree constantly about whether it
    belongs ("The Beatles" vs "Beatles") and it is never the sole
    distinguishing feature between two artists.

    >>> normalize_artist("The Velvet Underground")
    'velvet underground'
    >>> normalize_artist("Nirvana (2)")
    'nirvana'
    """
    if not artist:
        return ""

    text = _DISCOGS_ARTIST_SUFFIX.sub("", artist)
    text = _fold_unicode(text)
    text = _THE_PREFIX.sub("", text.strip())
    text = _PUNCT.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip().lower()


def blocking_key(artist: str, year: int | None = None, window: int = 2) -> str:
    """Build the coarse bucket key used to avoid all-pairs comparison.

    Releases only get compared when they share a blocking key. Year is bucketed
    into `window`-sized bins so that sources disagreeing by a year or two still
    collide -- Discogs dates the *pressing*, MusicBrainz dates the *release
    group*, and for a reissue those can differ by decades.

    That last point is why year is a soft signal here and never a hard filter:
    we emit the artist-only key as well, and the scorer sorts it out.
    """
    artist_key = normalize_artist(artist)
    if year is None:
        return artist_key
    return f"{artist_key}|{year // window}"


def blocking_keys(artist: str, year: int | None = None, window: int = 2) -> set[str]:
    """All keys a release should be indexed under.

    Emits the artist-only key alongside the year-bucketed one so reissues
    still meet their originals. Costs recall-side compute, saves us from the
    single worst failure mode: a 1967 original and its 2012 repress never
    being compared at all.
    """
    keys = {normalize_artist(artist)}
    if year is not None:
        keys.add(blocking_key(artist, year, window))
        # Adjacent buckets, so a release on a bucket boundary isn't isolated.
        keys.add(f"{normalize_artist(artist)}|{(year - window) // window}")
        keys.add(f"{normalize_artist(artist)}|{(year + window) // window}")
    return keys
