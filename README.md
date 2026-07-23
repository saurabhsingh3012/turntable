# turntable

**A personal music data platform.** Four music APIs that fundamentally disagree about what an album is, resolved into a single dimensional warehouse.

> 🚧 **Active development.** Scaffold and architecture are in place; ingestion is being built out source by source. See [ROADMAP.md](ROADMAP.md) for honest status.

---

## The actual problem

I own a few hundred records, scrobble everything I listen to, and go to more shows than is reasonable. That data lives in four places, and none of them agree with each other.

Ask a simple question — *do I listen to artists more after seeing them live?* — and you immediately hit the real problem:

| Source | What it calls this record |
|---|---|
| Discogs | `Radiohead – In Rainbows (2007, XL Recordings, XLLP324, UK pressing)` |
| MusicBrainz | `In Rainbows` — release-group `b1392450-e666-3926-a536-22c65998f837` |
| Last.fm | `Radiohead — In Rainbows` (no release identity at all) |
| Setlist.fm | songs performed, no album context whatsoever |
| Spotify | `In Rainbows` — but which of the six editions? |

Same record. Five identity models, none of which map cleanly onto the others. Discogs thinks in *physical pressings* — catalogue numbers, pressing plants, matrix runouts. MusicBrainz thinks in *release groups*. Last.fm thinks in loose artist/album strings typed by users. Setlist.fm doesn't think about albums at all.

**Entity resolution across these is the entire engineering problem**, and it's the reason this project exists. The dashboard at the end is the easy part.

---

## Architecture

```
   Discogs API ─┐
   Last.fm API ─┤
MusicBrainz API ─┼──▶ ingest ──▶ raw (append-only, JSONB)
  Setlist.fm  ──┤              │
   Spotify API ─┘              ▼
                          entity resolution
                        (blocking → scoring → clustering)
                               │
                               ▼
                     dbt ──▶ staging ──▶ marts
                               │
                               ▼
                      DuckDB / Postgres
                               │
                               ▼
                          dashboard
```

**Orchestration:** Dagster (asset-based — the lineage between "a Discogs release" and "a resolved album" is the interesting part, and asset graphs model that better than task graphs)

**Warehouse:** DuckDB locally, Postgres for the deployed version. Deliberately not Snowflake — this shouldn't cost money to run.

**Transformation:** dbt, with tests on every mart model.

---

## The entity resolution approach

Naive string matching fails immediately. `In Rainbows` vs `In Rainbows (Disc 2)` vs `In Rainbows [Bonus Disc]` vs `IN RAINBOWS` are four strings and one album — while `Weezer` and `Weezer` are two entirely different albums, both self-titled, six years apart. String similarity actively misleads here.

The pipeline:

1. **Blocking** — never compare all pairs. Bucket by normalized artist name + release year window to cut the comparison space.
2. **Scoring** — weighted feature vector per candidate pair:
   - normalized title distance (Jaro-Winkler over a cleaned title)
   - track count agreement
   - total duration agreement, with tolerance
   - track title sequence similarity
   - year proximity
   - catalogue number exact match, where present — very high weight
3. **Clustering** — connected components over the pairs that clear threshold, with transitivity constraints.
4. **Human adjudication** — a review queue for pairs in the uncertain band. Ground truth for anything ambiguous is me, looking at the record.

Every resolved cluster keeps its full provenance chain. If the warehouse says two things are the same album, you can trace exactly why.

---

## Questions this is built to answer

- Do I listen to an artist more in the months after seeing them live, or does the effect fade within weeks?
- What's the lag between first scrobbling an artist and buying their record?
- How much of my collection do I never actually play?
- Which venues have the best hit rate for artists I keep listening to a year later?
- Is my collection's market value drifting, and does that correlate at all with what I listen to?

---

## Real data — Discogs × MusicBrainz

The resolver started life on a hand-built fixture. It now runs on **real API
data**: `scripts/build_real_sample.py` pulls live records from Discogs and
MusicBrainz and resolves them. Here is what happened, unedited, because the story
is the point.

**First real run.** 12 albums, 40 real records (12 Discogs pressings, 28
MusicBrainz release-groups — the true match plus near-miss distractors per album):

```
                       fixture      real data (v1)
precision                1.000            0.476
recall                   1.000            1.000
```

Recall held — every true album was found. But precision **collapsed**, and the
false positives were all the same shape: `Live in Rainbows`, `Rumours Live`,
`Discovery Remixed`, `The Dark Side of the Moon (demos)`. Real near-miss
release-groups — live albums, compilations, remixes — that share a title, an
artist, and a year with the studio album, and that the clean fixture simply never
contained. A scorer tuned on tidy data over-accepted them.

**The fix, from domain knowledge.** MusicBrainz tags release-groups with
*secondary-types* (Live / Compilation / Remix / Demo …) and Discogs encodes the
same in its format descriptions — signals the resolver wasn't using. Adding a
**release-type contradiction** (a studio pressing should not merge with a live
release-group, even when everything else agrees) — as a veto that is a *no-op*
when the field is absent, so the fixture is unaffected:

```
                       real (v1)     real (v2, release-type)
precision                0.476              0.833
recall                   1.000              1.000
F1                       0.645              0.909
```

Precision nearly doubled; recall stayed perfect; the fixture's 26 tests and its
precision-1.000 are untouched (verified — the rule can't fire without the field).
The two remaining false positives are genuinely hard (bonus discs and untagged
sessions) and are honest future work, not swept away.

> This is the whole point of running on real data: it revealed a limitation the
> synthetic fixture *could not*, and fixing it made the resolver better in a way
> that generalises. Reproduce with `python scripts/build_real_sample.py` (needs
> Discogs + MusicBrainz configured in `.env`).

**Source status:** Discogs search + MusicBrainz work today. Last.fm (listening
history) and Setlist.fm (concerts) clients are built and awaiting a username /
approved key. A private Discogs collection needs the OAuth toggle. The seed album
list stands in for the owner's collection — swap it in and the same pipeline runs.

## Status

See [ROADMAP.md](ROADMAP.md). Resolver done and now validated on real Discogs ×
MusicBrainz data; Last.fm / Setlist.fm clients built and awaiting credentials;
warehouse + dashboard still ahead.

## Running it

```bash
pip install -e ".[dev]"
cp .env.example .env                     # add your API keys
python scripts/build_real_sample.py      # real Discogs x MusicBrainz resolution
pytest -q                                # 35 unit + regression tests
```

## Licence

MIT
