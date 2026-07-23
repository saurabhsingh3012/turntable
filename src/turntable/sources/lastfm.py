"""Last.fm client.

Last.fm is the source with the loosest identity model: user-typed artist and
album *strings*, no release identity, no track counts, no durations. That
sparseness is exactly why the resolver drops missing features and renormalises
rather than scoring them as mismatches -- a Last.fm record legitimately has
almost nothing but a title and an artist.

Reading a user's public listening history (scrobbles, top artists/albums) needs
only the API key plus the username; no user-authorization flow. So the moment
the real listening username is set, this pulls real data.
"""

from __future__ import annotations

from .base import HttpClient

API = "https://ws.audioscrobbler.com/2.0/"


class LastfmClient:
    def __init__(self, api_key: str, user_agent: str) -> None:
        self.api_key = api_key
        # Last.fm's published limit is generous; 0.25s is courteous and safe.
        self.http = HttpClient(user_agent, min_interval=0.25)

    def _call(self, method: str, **params) -> dict:
        return self.http.get_json(
            API,
            params={"method": method, "api_key": self.api_key,
                    "format": "json", **params},
        )

    def user_info(self, username: str) -> dict:
        return self._call("user.getinfo", user=username).get("user", {})

    def top_albums(self, username: str, limit: int = 50,
                   period: str = "overall") -> list[dict]:
        data = self._call("user.gettopalbums", user=username, limit=limit,
                          period=period)
        return data.get("topalbums", {}).get("album", [])

    def top_artists(self, username: str, limit: int = 50,
                    period: str = "overall") -> list[dict]:
        data = self._call("user.gettopartists", user=username, limit=limit,
                          period=period)
        return data.get("topartists", {}).get("artist", [])

    @staticmethod
    def album_to_record(album: dict, source_id: str | None = None) -> dict:
        """Map a Last.fm top-album entry to the resolver's record shape.

        Deliberately sparse -- title, artist, and nothing else -- which is all
        Last.fm provides. The playcount is carried separately by the caller; it
        is listening data, not identity data, so it doesn't belong on the record
        the resolver sees.
        """
        return {
            "id": str(source_id or album.get("mbid") or album.get("name", "")),
            "title": album.get("name", ""),
            "artist": (album.get("artist") or {}).get("name", ""),
            "year": None,
            "track_count": None,
            "total_duration_sec": None,
            "catalogue_number": None,
        }
