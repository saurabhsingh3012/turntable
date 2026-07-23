"""Shared HTTP plumbing for the source clients.

Every music API here has a different, strict rate limit, and every one of them
will ban a client that ignores it -- MusicBrainz in particular is unforgiving.
So rate limiting is not optional politeness; it's the difference between a
pipeline that runs and one that gets a 503 halfway through. This module
centralises it so each client just declares its own minimum interval.

Also centralises: a descriptive User-Agent (MusicBrainz *requires* one and will
403 without it), retry-with-backoff on transient errors, and JSON decoding.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Minimum seconds between requests, enforced by sleeping.

    A single shared clock per client. Deliberately simple -- a token bucket
    would be more elegant, but these APIs specify a flat floor ("1 request per
    second"), and honouring that floor exactly is what keeps us un-banned.
    """

    min_interval: float
    _last: float = field(default=0.0, repr=False)

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


class HttpClient:
    """Rate-limited JSON HTTP client with backoff.

    Retries on 429 (rate limited) and 5xx, honouring a Retry-After header when
    present. Does NOT retry on 4xx other than 429 -- a 401/403/404 is a real
    answer, not a transient blip, and retrying it just wastes the rate budget.
    """

    def __init__(
        self,
        user_agent: str,
        min_interval: float,
        default_headers: dict[str, str] | None = None,
        max_retries: int = 4,
    ) -> None:
        self.user_agent = user_agent
        self.limiter = RateLimiter(min_interval)
        self.default_headers = default_headers or {}
        self.max_retries = max_retries

    def get_json(
        self, url: str, params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        hdrs = {"User-Agent": self.user_agent, **self.default_headers,
                **(headers or {})}

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            req = urllib.request.Request(url, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429 or 500 <= e.code < 600:
                    retry_after = e.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2.0 ** attempt
                    time.sleep(min(delay, 30.0))
                    continue
                raise  # 401/403/404 etc. -- a real answer, surface it
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                time.sleep(2.0**attempt)
        raise RuntimeError(
            f"GET {url} failed after {self.max_retries} tries: {last_err}"
        )


_SPECIAL_TYPES = {"live", "compilation", "remix", "demo", "soundtrack",
                  "bootleg", "interview", "mixtape", "dj-mix"}


def special_types(descriptors: list[str]) -> str:
    """Normalise release-type tags to the special ones, sorted+joined.

    Studio albums carry no special secondary type and map to '' -- which is what
    lets the resolver treat 'studio vs live' as a contradiction while leaving
    'studio vs studio' untouched. Shared by the Discogs and MusicBrainz mappers
    so both sources speak the same release-type vocabulary.
    """
    found = sorted({d.lower() for d in descriptors if d.lower() in _SPECIAL_TYPES})
    return ",".join(found)
