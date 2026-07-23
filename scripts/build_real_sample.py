"""Pull REAL Discogs + MusicBrainz records and run the resolver on them.

This is the first real-data run: it replaces the hand-built fixture with actual
API responses. For each seed album it fetches the top Discogs release (with its
tracklist) and the top few MusicBrainz release-groups -- the true match plus
near-miss distractors (live albums, compilations, same-name different-album) --
then runs the existing resolver and measures whether it pairs Discogs to the
right MusicBrainz release-group and rejects the distractors.

Ground truth is heuristic but honest: a precise `artist:X AND releasegroup:Y`
MusicBrainz query returns the true release-group at rank 0 essentially always,
so rank 0 is treated as the positive and lower ranks as distractors. Stated
plainly so the numbers aren't oversold.

The seed list is a stand-in for Saurabh's actual collection, which is private
pending an OAuth/public toggle -- swap `SEED_ALBUMS` for his collection and the
same code runs unchanged.

Run:  python scripts/build_real_sample.py
Writes raw + resolved data under data/ (gitignored). Prints real metrics.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from turntable.resolve.normalize import blocking_keys  # noqa: E402
from turntable.resolve.scoring import score_pair  # noqa: E402
from turntable.sources import Config, DiscogsClient, MusicBrainzClient  # noqa: E402

SEED_ALBUMS = [
    ("Radiohead", "In Rainbows"),
    ("Pink Floyd", "The Dark Side of the Moon"),
    ("Miles Davis", "Kind of Blue"),
    ("Fleetwood Mac", "Rumours"),
    ("Daft Punk", "Discovery"),
    ("Björk", "Homogenic"),
    ("The Velvet Underground", "The Velvet Underground & Nico"),
    ("Nirvana", "Nevermind"),
    ("Radiohead", "OK Computer"),
    ("Kendrick Lamar", "To Pimp a Butterfly"),
    ("Amy Winehouse", "Back to Black"),
    ("Bon Iver", "For Emma, Forever Ago"),
]

DATA = Path(__file__).resolve().parents[1] / "data"


def pull(cfg: Config) -> tuple[list[dict], list[dict], dict[int, str]]:
    """Fetch real records. Returns (discogs_records, mb_records, truth).

    truth maps a discogs record key -> the mb record key that is its true match.
    """
    discogs = DiscogsClient(cfg.discogs_key, cfg.discogs_secret,
                            cfg.musicbrainz_user_agent)
    mb = MusicBrainzClient(cfg.musicbrainz_user_agent)

    discogs_records: list[dict] = []
    mb_records: list[dict] = []
    truth: dict[str, str] = {}

    for i, (artist, album) in enumerate(SEED_ALBUMS):
        try:
            hits = discogs.search_releases(f"{artist} {album}", per_page=3)
            if not hits:
                print(f"  [skip] discogs miss: {artist} - {album}")
                continue
            detail = discogs.get_release(hits[0]["id"])
            drec = DiscogsClient.to_record(detail, source_id=f"d{i}")
            dkey = f"discogs:{drec['id']}"

            groups = mb.search_release_groups(artist, album, limit=3)
            if not groups:
                print(f"  [skip] musicbrainz miss: {artist} - {album}")
                continue

            # rank 0 = true match (fetch track detail); lower = distractors
            for rank, rg in enumerate(groups):
                rel = mb.get_release_group_release(rg["id"]) if rank == 0 else None
                mrec = MusicBrainzClient.to_record(rg, rel, source_id=f"m{i}_{rank}")
                mb_records.append(mrec)
                if rank == 0:
                    truth[dkey] = f"musicbrainz:{mrec['id']}"

            discogs_records.append(drec)
            print(f"  [ok] {artist} - {album}: discogs '{drec['title'][:40]}' "
                  f"+ {len(groups)} mb candidates")
        except Exception as e:  # noqa: BLE001 -- one bad album shouldn't kill the run
            print(f"  [err] {artist} - {album}: {str(e)[:70]}")
            time.sleep(2)

    return discogs_records, mb_records, truth


def evaluate(discogs_records, mb_records, truth) -> dict:
    """Score every Discogs<->MusicBrainz pair that blocking admits; measure it."""
    records = {f"discogs:{r['id']}": r for r in discogs_records}
    records.update({f"musicbrainz:{r['id']}": r for r in mb_records})

    # blocking index
    index: dict[str, set[str]] = {}
    for key, rec in records.items():
        for block in blocking_keys(rec["artist"], rec.get("year")):
            index.setdefault(block, set()).add(key)

    tp = fp = fn = tn = review = 0
    compared_positive: set[str] = set()
    seen: set[tuple[str, str]] = set()  # dedupe: a pair can share several blocks

    all_pairs = 0
    for members in index.values():
        members = sorted(members)
        for a in members:
            for b in members:
                if a >= b:
                    continue
                if a.split(":")[0] == b.split(":")[0]:
                    continue  # same source, never a match
                if (a, b) in seen:
                    continue  # already scored via another shared blocking key
                seen.add((a, b))
                all_pairs += 1
                verdict = score_pair(records[a], records[b]).verdict
                is_true = truth.get(a) == b or truth.get(b) == a
                if is_true:
                    compared_positive.add(a if a.startswith("discogs") else b)
                if verdict == "accept":
                    if is_true:
                        tp += 1
                    else:
                        fp += 1
                elif verdict == "review":
                    review += 1
                else:  # reject
                    if is_true:
                        fn += 1
                    else:
                        tn += 1

    # positives that blocking never even brought together
    missed_by_blocking = sum(
        1 for dkey, mkey in truth.items()
        if dkey in records and mkey in records and dkey not in compared_positive
    )

    denom_recall = tp + fn + missed_by_blocking
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / denom_recall if denom_recall else 0.0
    pr = precision + recall
    f1 = (2 * precision * recall / pr) if pr else 0.0

    return {
        "records": len(records), "true_pairs": len(truth),
        "pairs_compared": all_pairs,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "review": review,
        "missed_by_blocking": missed_by_blocking,
        "precision": precision, "recall": recall, "f1": f1,
    }


def main() -> int:
    cfg = Config.load(str(Path(__file__).resolve().parents[1] / ".env"))
    avail = cfg.available()
    if not (avail["discogs_search"] and avail["musicbrainz"]):
        print("Need Discogs + MusicBrainz configured. See .env.example.")
        return 1

    DATA.mkdir(exist_ok=True)
    print(f"Pulling {len(SEED_ALBUMS)} albums from Discogs + MusicBrainz "
          "(real API calls, rate-limited)...")
    discogs_records, mb_records, truth = pull(cfg)

    (DATA / "discogs_records.json").write_text(json.dumps(discogs_records, indent=2))
    (DATA / "musicbrainz_records.json").write_text(json.dumps(mb_records, indent=2))

    m = evaluate(discogs_records, mb_records, truth)
    print("\n" + "=" * 66)
    print("REAL DATA -- Discogs x MusicBrainz entity resolution")
    print("=" * 66)
    print(f"  records                 {m['records']} "
          f"({len(discogs_records)} discogs, {len(mb_records)} musicbrainz)")
    print(f"  true album pairs        {m['true_pairs']}")
    print(f"  pairs compared          {m['pairs_compared']} (after blocking)")
    print(f"  true positives          {m['tp']}")
    print(f"  false positives         {m['fp']}")
    print(f"  false negatives         {m['fn']}")
    print(f"  routed to review        {m['review']}")
    print(f"  missed by blocking      {m['missed_by_blocking']}")
    print(f"  precision               {m['precision']:.3f}")
    print(f"  recall                  {m['recall']:.3f}")
    print(f"  F1                      {m['f1']:.3f}")
    print("\n  Ground truth is heuristic (MusicBrainz rank-0 = true match). Seed")
    print("  list stands in for Saurabh's private collection; swap it in and the")
    print("  same pipeline runs. Raw records saved under data/.")
    (DATA / "resolution_metrics.json").write_text(json.dumps(m, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
