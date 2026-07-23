"""Load API credentials from the environment / a local .env file.

Secrets never live in the repo. This reads them from process env, falling back
to a local .env (which is gitignored). Every field is optional at load time so
the pipeline can run whatever subset of sources is currently configured -- if
only Discogs and MusicBrainz are set up, those two run and the rest are skipped
with a clear message, rather than the whole thing erroring out.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file, without overwriting real env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Config:
    discogs_key: str | None
    discogs_secret: str | None
    discogs_username: str | None
    musicbrainz_user_agent: str
    lastfm_api_key: str | None
    lastfm_username: str | None
    setlistfm_api_key: str | None

    @classmethod
    def load(cls, dotenv: str | os.PathLike | None = ".env") -> Config:
        if dotenv:
            _load_dotenv(Path(dotenv))
        g = os.environ.get
        return cls(
            discogs_key=g("DISCOGS_CONSUMER_KEY") or None,
            discogs_secret=g("DISCOGS_CONSUMER_SECRET") or None,
            discogs_username=g("DISCOGS_USERNAME") or None,
            musicbrainz_user_agent=g("MUSICBRAINZ_USER_AGENT")
            or "turntable/0.1 (https://github.com/saurabhsingh3012)",
            lastfm_api_key=g("LASTFM_API_KEY") or None,
            lastfm_username=g("LASTFM_USERNAME") or None,
            setlistfm_api_key=g("SETLISTFM_API_KEY") or None,
        )

    def available(self) -> dict[str, bool]:
        """Which sources are configured enough to use right now."""
        return {
            "discogs_search": bool(self.discogs_key and self.discogs_secret),
            "discogs_collection": bool(
                self.discogs_key and self.discogs_secret and self.discogs_username
            ),
            "musicbrainz": True,  # needs only a User-Agent
            "lastfm": bool(self.lastfm_api_key and self.lastfm_username),
            "setlistfm": bool(self.setlistfm_api_key),
        }
