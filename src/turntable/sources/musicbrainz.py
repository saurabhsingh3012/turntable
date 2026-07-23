"""MusicBrainz client.

MusicBrainz is the source that thinks in *release groups* -- the abstract
"album" that all its editions belong to -- which is a different identity model
from Discogs' physical pressings. Reconciling those two models is a good chunk
of why the resolver exists.

No API key needed for reads; MusicBrainz requires only a descriptive
User-Agent (and will 403 without one). The rate limit is a hard 1 request per
second for anonymous clients -- the base client's limiter enforces it.

MusicBrainz has no catalogue number at the release-group level, so records from
here deliberately leave that field empty; the resolver already handles missing
features by renormalising rather than penalising.
"""

from __future__ import annotations

from .base import HttpClient, special_types

API = "https://musicbrainz.org/ws/2"


class MusicBrainzClient:
    def __init__(self, user_agent: str) -> None:
        # 1.1s to stay safely under the 1 req/sec anonymous limit.
        self.http = HttpClient(user_agent, min_interval=1.1)

    def search_release_groups(self, artist: str, album: str,
                              limit: int = 5) -> list[dict]:
        """Search release-groups by artist + album title."""
        query = f'artist:"{artist}" AND releasegroup:"{album}"'
        data = self.http.get_json(
            f"{API}/release-group",
            params={"query": query, "fmt": "json", "limit": limit},
        )
        return data.get("release-groups", [])

    def get_release_group_release(self, rg_id: str) -> dict | None:
        """Fetch a representative release of a release-group, with track count.

        A release-group has many releases (editions); we take the first and pull
        its media/track info so the record has a track count and duration to
        match on.
        """
        data = self.http.get_json(
            f"{API}/release",
            params={"release-group": rg_id, "fmt": "json", "limit": 1,
                    "inc": "media"},
        )
        releases = data.get("releases", [])
        return releases[0] if releases else None

    @staticmethod
    def to_record(release_group: dict, release: dict | None,
                  source_id: str | None = None) -> dict:
        """Map a MusicBrainz release-group (+ optional release) to record shape."""
        artist_credit = release_group.get("artist-credit") or []
        artist = artist_credit[0]["name"] if artist_credit else ""

        year = None
        first_date = release_group.get("first-release-date", "")
        if first_date[:4].isdigit():
            year = int(first_date[:4])

        track_count = None
        total_sec = None
        if release:
            media = release.get("media") or []
            track_count = sum(m.get("track-count", 0) for m in media) or None
            length_ms = 0
            for m in media:
                for tr in m.get("tracks") or []:
                    length_ms += tr.get("length") or 0
            total_sec = round(length_ms / 1000) if length_ms else None

        return {
            "id": str(source_id or release_group.get("id", "")),
            "title": release_group.get("title", ""),
            "artist": artist,
            "year": year,
            "track_count": track_count,
            "total_duration_sec": total_sec,
            "catalogue_number": None,  # not a release-group concept
            # secondary-types (Live/Compilation/Remix/Demo/...) are the signal
            # that distinguishes a live album or compilation from the studio
            # album a collector actually owns. Empty string = plain studio album.
            "release_type": special_types(release_group.get("secondary-types") or []),
        }

