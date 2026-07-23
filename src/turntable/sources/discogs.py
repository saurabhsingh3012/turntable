"""Discogs client.

Discogs is the source that thinks in *physical pressings* -- catalogue numbers,
pressing plants, formats -- which is exactly the identity information the
resolver leans on most (a matching catalogue number is near-conclusive). So the
mapper below is careful to preserve it.

Two access levels:
  * Database search + release lookup -- works with just a consumer key/secret
    (app-level auth), no user authorization. This is what runs today.
  * A user's collection -- needs either a public collection or the OAuth 1.0a
    user-authorization flow. Left as a documented method that works the moment
    the collection is public or a user token is supplied.

Rate limit: 60 requests/minute authenticated -> 1.0s minimum interval, kept
comfortably under the cap.
"""

from __future__ import annotations

from .base import HttpClient, special_types

API = "https://api.discogs.com"


class DiscogsClient:
    def __init__(self, consumer_key: str, consumer_secret: str,
                 user_agent: str) -> None:
        self._auth = {"key": consumer_key, "secret": consumer_secret}
        self.http = HttpClient(user_agent, min_interval=1.0)

    def search_releases(self, query: str, per_page: int = 5) -> list[dict]:
        """Search the Discogs database. Returns raw result dicts."""
        data = self.http.get_json(
            f"{API}/database/search",
            params={"q": query, "type": "release", "per_page": per_page, **self._auth},
        )
        return data.get("results", [])

    def get_release(self, release_id: int) -> dict:
        """Full release detail, including the tracklist we need for track count."""
        return self.http.get_json(f"{API}/releases/{release_id}", params=self._auth)

    def collection(self, username: str, per_page: int = 100) -> list[dict]:
        """A user's public collection. 403 if private (needs OAuth/public)."""
        releases: list[dict] = []
        page = 1
        while True:
            data = self.http.get_json(
                f"{API}/users/{username}/collection/folders/0/releases",
                params={"per_page": per_page, "page": page, **self._auth},
            )
            releases.extend(data.get("releases", []))
            pagination = data.get("pagination", {})
            if page >= pagination.get("pages", 1):
                break
            page += 1
        return releases

    @staticmethod
    def to_record(release_detail: dict, source_id: str | None = None) -> dict:
        """Map a Discogs release to the resolver's record shape.

        Preserves the catalogue number (Discogs' strongest identity signal) and
        derives track count and total duration from the tracklist when present.
        """
        artists = release_detail.get("artists") or []
        artist = artists[0]["name"] if artists else release_detail.get("artist", "")

        tracklist = release_detail.get("tracklist") or []
        # count only actual tracks, not headings/index entries
        tracks = [t for t in tracklist if t.get("type_") in (None, "track")]
        total_sec = _sum_durations(tracks)

        labels = release_detail.get("labels") or []
        catno = labels[0].get("catno") if labels else release_detail.get("catno")

        # Discogs encodes live/compilation status in each format's descriptions
        # (e.g. ["LP", "Album", "Live"]). Collect them so a live pressing is
        # marked as such and correctly matches a live release-group, while a
        # studio pressing ('') does not match a live one.
        descriptors: list[str] = []
        for fmt in release_detail.get("formats") or []:
            descriptors.extend(fmt.get("descriptions") or [])

        return {
            "id": str(source_id or release_detail.get("id", "")),
            "title": release_detail.get("title", ""),
            "artist": artist,
            "year": release_detail.get("year") or None,
            "track_count": len(tracks) or None,
            "total_duration_sec": total_sec or None,
            "catalogue_number": catno or None,
            "release_type": special_types(descriptors),
        }


def _sum_durations(tracks: list[dict]) -> int | None:
    """Sum 'mm:ss' track durations. Returns None if none are populated."""
    total = 0
    seen = False
    for t in tracks:
        dur = (t.get("duration") or "").strip()
        if not dur or ":" not in dur:
            continue
        try:
            mins, secs = dur.split(":")[-2:]
            total += int(mins) * 60 + int(secs)
            seen = True
        except (ValueError, IndexError):
            continue
    return total if seen else None
