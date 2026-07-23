"""Setlist.fm client.

Setlist.fm is the outlier source: it has no album concept at all, only songs
performed at shows. It contributes concert history, which is what lets the
warehouse answer the question the whole project started from -- "do I listen to
artists more after seeing them live?"

Needs an API key (and a descriptive User-Agent). Setlist.fm is strict: it
returns 403 for a missing/unapproved key and rate-limits at ~2 req/sec, so the
base client's interval is set conservatively.
"""

from __future__ import annotations

from .base import HttpClient

API = "https://api.setlist.fm/rest/1.0"


class SetlistfmClient:
    def __init__(self, api_key: str, user_agent: str) -> None:
        self.http = HttpClient(
            user_agent,
            min_interval=0.6,
            default_headers={"Accept": "application/json", "x-api-key": api_key},
        )

    def search_artist(self, name: str) -> list[dict]:
        data = self.http.get_json(f"{API}/search/artists",
                                  params={"artistName": name, "sort": "relevance"})
        return data.get("artist", [])

    def artist_setlists(self, mbid: str, page: int = 1) -> dict:
        """A page of an artist's setlist history, keyed by MusicBrainz artist id."""
        return self.http.get_json(f"{API}/artist/{mbid}/setlists",
                                  params={"p": page})

    @staticmethod
    def songs_from_setlist(setlist: dict) -> list[str]:
        """Flatten a setlist's sets into an ordered list of song names."""
        songs: list[str] = []
        for s in (setlist.get("sets", {}) or {}).get("set", []):
            for song in s.get("song", []):
                if song.get("name"):
                    songs.append(song["name"])
        return songs
