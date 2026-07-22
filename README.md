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

## Status

See [ROADMAP.md](ROADMAP.md). Short version: architecture and scaffold done, Discogs ingestion in progress, everything downstream is stubs and interfaces.

## Running it

```bash
uv sync
cp .env.example .env      # add your API keys
dagster dev               # asset graph at localhost:3000
```

## Licence

MIT
