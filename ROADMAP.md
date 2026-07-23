# Roadmap

Honest status. Nothing here is marked done unless it runs.

## Done

- [x] Normalization layer — title/artist folding, edition-marker stripping, diacritic folding
- [x] Blocking strategy with reissue-safe year bucketing (**90.1% comparison reduction** on the fixture set)
- [x] Pairwise scorer — weighted features, missing-feature renormalization, catalogue-number short-circuit
- [x] Runtime-contradiction veto (see regression note below)
- [x] Connected-component clustering with transitivity checking
- [x] Labelled evaluation fixture — 20 adversarial pairs
- [x] Evaluation harness reporting precision/recall/F1 and review-queue rate
- [x] 26 unit + regression tests, CI on push

### Measured — resolver v0.2, adversarial fixture

```
records                23        precision        1.000
all-pairs             253        recall           1.000
after blocking         25        F1               1.000
reduction           90.1%        false merges         0
                                 routed to review     7 of 20
```

Fixture is deliberately adversarial and over-weights hard cases. Read as a
lower bound, not a production estimate. Reproduce with `python tests/evaluate.py`.

**Regression worth knowing about:** v0.1 auto-merged Weezer's Blue Album (1994)
and Green Album (2001) at exactly 0.850. Same title, same artist, same track
count — the only disagreement was runtime, and at weight 0.10 it was drowned
out by agreement everywhere else. Fixed by making severe runtime disagreement a
multiplicative veto rather than a weighted feature, on the reasoning that *any*
weighted mean has this failure mode. The pair now scores 0.637 and routes to
human review. Locked in by `test_regression_self_titled_albums_do_not_merge`.

## Real-data milestone (done)

- [x] Discogs client — search + release detail (consumer key/secret), rate-limited
- [x] MusicBrainz client — release-group lookup, 1 req/sec, descriptive User-Agent
- [x] Real Discogs × MusicBrainz resolution run (`scripts/build_real_sample.py`)
- [x] **Release-type contradiction** — found necessary by real data (live/comp/remix
      near-misses); precision 0.476 → 0.833, recall held at 1.000, fixture unaffected
- [x] Last.fm + Setlist.fm clients built (awaiting username / approved key)
- [x] 35 tests incl. source-mapper + release-type regression tests

## Next

- [ ] Discogs OAuth 1.0a flow for the owner's private collection (or public toggle)
- [ ] Last.fm scrobble ingestion once the listening username is set
- [ ] Setlist.fm concert history once the key is approved (currently 403)
- [ ] The 2 remaining real-data false positives (bonus discs, untagged sessions) —
      needs primary-type and disambiguation signals
- [ ] Raw landing tables, append-only with ingested_at
- [ ] Dagster asset graph wiring ingestion to resolution
- [ ] dbt staging + marts, tests on every mart model
- [ ] Adjudication CLI for the review queue
- [ ] Dashboard

## Open questions

- Ground truth beyond the fixture requires manually labelling a few hundred
  real pairs. Worth it before trusting these numbers on live data.
- Whether to learn the feature weights once labelled data exists, or keep them
  hand-tuned for auditability. Currently hand-tuned deliberately — see the
  design note at the top of `scoring.py`.
- Slowly-changing dimensions for collection value: Discogs marketplace prices
  move constantly. SCD2, or periodic snapshots?
