"""Pairwise match scoring.

Given two candidate releases from different sources, produce a score in [0, 1]
and an explanation of how it was reached. The explanation is not decoration --
every cluster in the warehouse carries its provenance, so that any claim of
"these are the same album" can be audited later.

Design note: this is a hand-weighted linear model, not a learned one. That is a
deliberate choice given roughly 400 records of ground truth; a learned model on
that little labelled data would overfit to my particular collection and be
impossible to reason about when it goes wrong. The weights below are readable,
adjustable, and were tuned by hand against the adjudication queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import normalize_artist, normalize_title

# Feature weights. These sum to 1.0 before the catalogue-number override.
WEIGHTS = {
    "title": 0.40,
    "artist": 0.25,
    "track_count": 0.15,
    "duration": 0.10,
    "year": 0.10,
}

# A matching catalogue number is near-conclusive: it identifies a specific
# physical pressing from a specific label. When both sides have one and they
# agree, we short-circuit. When they disagree, we do NOT short-circuit to zero
# -- the same album legitimately has many catalogue numbers across pressings.
CATALOGUE_MATCH_SCORE = 0.97

# --- Contradiction handling ---------------------------------------------
# A weighted average lets strong agreement on several weak features drown out
# one feature that is screaming "these are different". That is not a
# hypothetical: the Weezer self-titled case (Blue 1994 vs Green 2001) matches
# perfectly on title, artist, and track count -- all ten tracks -- and differs
# only in runtime, by fourteen minutes. It scored 0.850 and auto-merged.
#
# The fix is to treat severe disagreement as a veto rather than a low score.
# Contradicted evidence dampens the whole result multiplicatively, so it can
# pull a pair out of auto-accept regardless of how well everything else lines
# up. Chosen over simply reweighting duration because the problem is
# structural: any weighted mean has this failure mode.
DURATION_CONTRADICTION_THRESHOLD = 0.25  # relative difference
DURATION_CONTRADICTION_PENALTY = 0.75

AUTO_ACCEPT = 0.85
AUTO_REJECT = 0.55
# Between the two thresholds, a human decides. See resolve/cluster.py.


@dataclass
class MatchExplanation:
    """Why a pair scored the way it did."""

    score: float
    features: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.score >= AUTO_ACCEPT:
            return "accept"
        if self.score < AUTO_REJECT:
            return "reject"
        return "review"


def jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler similarity.

    Chosen over Levenshtein because it rewards common prefixes, and album
    titles that share a prefix are usually the same album with an appended
    edition marker that normalization missed. Implemented directly to keep the
    dependency footprint small -- this is the only string metric needed.
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    match_window = max(len(s1), len(s2)) // 2 - 1
    match_window = max(match_window, 0)

    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0

    for i, ch in enumerate(s1):
        start = max(0, i - match_window)
        end = min(i + match_window + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j] or s2[j] != ch:
                continue
            s1_matches[i] = s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # Count transpositions
    transpositions = 0
    k = 0
    for i, matched in enumerate(s1_matches):
        if not matched:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    jaro = (
        matches / len(s1)
        + matches / len(s2)
        + (matches - transpositions) / matches
    ) / 3

    # Winkler prefix bonus, capped at 4 characters by convention.
    prefix = 0
    for c1, c2 in zip(s1[:4], s2[:4], strict=False):
        if c1 != c2:
            break
        prefix += 1

    return jaro + prefix * prefix_weight * (1 - jaro)


def _track_count_similarity(a: int | None, b: int | None) -> float | None:
    """Agreement on track count.

    Returns None when either side is missing, so the feature can be dropped
    and the remaining weights renormalized rather than scored as zero.
    Missing data is not evidence of mismatch -- Last.fm supplies no track
    counts at all, and scoring that as disagreement would sink every
    Last.fm pairing.
    """
    if a is None or b is None:
        return None
    if a == b:
        return 1.0
    diff = abs(a - b)
    # A bonus track or two is common between editions; a gap of 5+ is a
    # different release entirely.
    if diff <= 2:
        return 0.7
    if diff <= 4:
        return 0.3
    return 0.0


def _duration_similarity(
    a: int | None, b: int | None, tolerance: float = 0.05
) -> float | None:
    """Agreement on total runtime in seconds, within a relative tolerance."""
    if not a or not b:
        return None
    relative_diff = abs(a - b) / max(a, b)
    if relative_diff <= tolerance:
        return 1.0
    if relative_diff <= 0.15:
        return 0.6
    if relative_diff <= 0.30:
        return 0.2
    return 0.0


def _year_similarity(a: int | None, b: int | None) -> float | None:
    """Agreement on year, heavily softened.

    Deliberately generous. Discogs dates the physical pressing; MusicBrainz
    dates the release group; Spotify dates whatever the label uploaded. A 1967
    album and its 2012 repress are the same album and will differ by 45 years,
    so a hard year comparison actively harms recall. This feature exists to
    break ties, not to make decisions.
    """
    if a is None or b is None:
        return None
    diff = abs(a - b)
    if diff == 0:
        return 1.0
    if diff <= 2:
        return 0.8
    if diff <= 10:
        return 0.5
    return 0.3  # floor, not zero -- see docstring


def score_pair(left: dict, right: dict) -> MatchExplanation:
    """Score two candidate releases.

    Each side is a dict with any of: title, artist, track_count,
    total_duration_sec, year, catalogue_number. Missing keys are handled by
    dropping the corresponding feature and renormalizing.
    """
    explanation = MatchExplanation(score=0.0)

    # --- Catalogue number short-circuit -----------------------------------
    left_cat = (left.get("catalogue_number") or "").replace(" ", "").upper()
    right_cat = (right.get("catalogue_number") or "").replace(" ", "").upper()
    if left_cat and right_cat and left_cat == right_cat:
        explanation.score = CATALOGUE_MATCH_SCORE
        explanation.features["catalogue_number"] = 1.0
        explanation.notes.append(
            f"catalogue number exact match ({left_cat}) -- near-conclusive"
        )
        return explanation

    # --- Feature computation ----------------------------------------------
    raw: dict[str, float | None] = {
        "title": jaro_winkler(
            normalize_title(left.get("title", "")),
            normalize_title(right.get("title", "")),
        ),
        "artist": jaro_winkler(
            normalize_artist(left.get("artist", "")),
            normalize_artist(right.get("artist", "")),
        ),
        "track_count": _track_count_similarity(
            left.get("track_count"), right.get("track_count")
        ),
        "duration": _duration_similarity(
            left.get("total_duration_sec"), right.get("total_duration_sec")
        ),
        "year": _year_similarity(left.get("year"), right.get("year")),
    }

    # Drop unavailable features and renormalize the remaining weights, so a
    # sparse source is not penalized for its sparseness.
    available = {k: v for k, v in raw.items() if v is not None}
    if not available:
        explanation.notes.append("no comparable features -- cannot score")
        return explanation

    total_weight = sum(WEIGHTS[k] for k in available)
    score = sum(WEIGHTS[k] * v for k, v in available.items()) / total_weight

    # --- Contradiction veto ------------------------------------------------
    # Applied after the weighted mean so it can override broad agreement.
    left_duration = left.get("total_duration_sec")
    right_duration = right.get("total_duration_sec")
    if left_duration and right_duration:
        relative_diff = abs(left_duration - right_duration) / max(
            left_duration, right_duration
        )
        if relative_diff > DURATION_CONTRADICTION_THRESHOLD:
            score *= DURATION_CONTRADICTION_PENALTY
            explanation.notes.append(
                f"runtime contradiction: {relative_diff:.0%} apart "
                f"({left_duration}s vs {right_duration}s) -- score damped by "
                f"{1 - DURATION_CONTRADICTION_PENALTY:.0%}"
            )

    explanation.score = round(score, 4)
    explanation.features = {k: round(v, 4) for k, v in available.items()}

    dropped = set(raw) - set(available)
    if dropped:
        explanation.notes.append(
            f"features unavailable, weights renormalized: {sorted(dropped)}"
        )
    if left_cat and right_cat and left_cat != right_cat:
        explanation.notes.append(
            "catalogue numbers differ -- expected across pressings, not penalized"
        )

    return explanation
