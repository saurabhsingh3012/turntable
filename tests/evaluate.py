"""Evaluate the resolver against the labelled fixture set.

Run with:  python tests/evaluate.py

Reports precision / recall / F1 at the accept threshold, the proportion of
pairs routed to human review, and a per-pair breakdown so failures are visible
rather than averaged away.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import LABELLED_PAIRS, RECORDS_BY_SOURCE  # noqa: E402

from turntable.resolve.normalize import blocking_keys  # noqa: E402
from turntable.resolve.scoring import (  # noqa: E402
    AUTO_ACCEPT,
    AUTO_REJECT,
    score_pair,
)


def build_lookup() -> dict[str, dict]:
    return {
        f"{source}:{record['id']}": record
        for source, records in RECORDS_BY_SOURCE.items()
        for record in records
    }


def build_blocking_index() -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for source, records in RECORDS_BY_SOURCE.items():
        for record in records:
            key = f"{source}:{record['id']}"
            for block in blocking_keys(record["artist"], record.get("year")):
                index.setdefault(block, set()).add(key)
    return index


def main() -> int:
    lookup = build_lookup()
    index = build_blocking_index()

    total_records = len(lookup)
    all_pairs = total_records * (total_records - 1) // 2
    blocked_pairs = set()
    for members in index.values():
        members = sorted(members)
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                if left.split(":", 1)[0] != right.split(":", 1)[0]:
                    blocked_pairs.add((left, right))

    print("=" * 74)
    print("BLOCKING")
    print("=" * 74)
    print(f"  records                     {total_records}")
    print(f"  all-pairs comparisons       {all_pairs}")
    print(f"  after blocking              {len(blocked_pairs)}")
    reduction = 100 * (1 - len(blocked_pairs) / all_pairs) if all_pairs else 0.0
    print(f"  comparison reduction        {reduction:.1f}%")

    tp = fp = tn = fn = 0
    review = 0
    review_correct = 0
    rows = []

    for left, right, expected, why in LABELLED_PAIRS:
        same_source = left.split(":", 1)[0] == right.split(":", 1)[0]
        if same_source:
            rows.append((left, right, expected, None, "SKIPPED", "same-source", why))
            continue

        explanation = score_pair(lookup[left], lookup[right])
        verdict = explanation.verdict
        score = explanation.score

        if verdict == "review":
            review += 1
            if expected:
                review_correct += 1
            outcome = "REVIEW"
        elif verdict == "accept":
            if expected:
                tp += 1
                outcome = "TP"
            else:
                fp += 1
                outcome = "FP  <-- FALSE MERGE"
        else:
            if expected:
                fn += 1
                outcome = "FN  <-- MISSED"
            else:
                tn += 1
                outcome = "TN"

        rows.append((left, right, expected, score, outcome, verdict, why))

    print()
    print("=" * 74)
    print("PER-PAIR RESULTS")
    print("=" * 74)
    print(f"{'pair':<34}{'truth':<7}{'score':<8}{'outcome':<22}")
    print("-" * 74)
    for left, right, expected, score, outcome, _verdict, why in rows:
        pair = f"{left.split(':')[1]}~{right.split(':')[1]}"
        score_str = f"{score:.3f}" if score is not None else "  -  "
        truth = "same" if expected else "diff"
        print(f"{pair:<34}{truth:<7}{score_str:<8}{outcome:<22}")
        print(f"{'':<34}{'':<7}{'':<8}{why}")

    decided = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    print()
    print("=" * 74)
    print("SUMMARY")
    print("=" * 74)
    print(f"  thresholds                  accept >= {AUTO_ACCEPT}, "
          f"reject < {AUTO_REJECT}")
    print(f"  labelled pairs              {len(LABELLED_PAIRS)}")
    print(f"  auto-decided                {decided}")
    print(f"  routed to human review      {review}")
    print()
    print(f"  true positives              {tp}")
    print(f"  false positives             {fp}")
    print(f"  true negatives              {tn}")
    print(f"  false negatives             {fn}")
    print()
    print(f"  precision                   {precision:.3f}")
    print(f"  recall                      {recall:.3f}")
    print(f"  F1                          {f1:.3f}")
    if review:
        print(f"  review queue: {review_correct}/{review} were true matches")

    print()
    print("  NOTE: fixture is deliberately adversarial and over-represents hard")
    print("  cases. Treat as a lower bound, not a production estimate.")

    return 0 if fp == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
