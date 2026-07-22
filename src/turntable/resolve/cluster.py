"""Clustering scored pairs into resolved albums.

Takes the accepted pairs from scoring and forms connected components, then
applies a transitivity sanity check. Anything that fails the check, or that
scored into the uncertain band, goes to a human adjudication queue rather than
being silently guessed at.

The transitivity check is the reason this module is not four lines of
union-find. Naive connected components chain badly: if A~B and B~C both score
0.86, A and C get merged even when A~C scores 0.2. In a music catalogue that
means a live album, a studio album, and a compilation sharing a title fragment
can collapse into one entity. The check catches it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from .scoring import AUTO_ACCEPT, AUTO_REJECT, MatchExplanation, score_pair


@dataclass
class Cluster:
    """A set of source records believed to describe one album."""

    members: set[str] = field(default_factory=set)
    evidence: list[tuple[str, str, float]] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str | None = None

    @property
    def sources(self) -> set[str]:
        """Which upstream systems contributed, e.g. {'discogs', 'musicbrainz'}."""
        return {member.split(":", 1)[0] for member in self.members}


class UnionFind:
    """Standard union-find with path compression."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self._parent.setdefault(item, item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a

    def groups(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for item in self._parent:
            out[self.find(item)].add(item)
        return dict(out)


def _record_key(source: str, record: dict) -> str:
    return f"{source}:{record['id']}"


def build_clusters(
    records_by_source: dict[str, list[dict]],
    blocking_index: dict[str, set[str]],
    transitivity_floor: float = 0.45,
) -> tuple[list[Cluster], list[tuple[str, str, MatchExplanation]]]:
    """Resolve records into album clusters.

    Args:
        records_by_source: e.g. {"discogs": [...], "musicbrainz": [...]}
        blocking_index: blocking key -> set of record keys sharing that key.
            Only pairs co-occurring in a block are ever compared.
        transitivity_floor: minimum score an implied pair must reach for a
            cluster to be trusted without review.

    Returns:
        (clusters, review_queue) -- the queue holds pairs that landed between
        the accept and reject thresholds, for a human to adjudicate.
    """
    lookup: dict[str, dict] = {}
    for source, records in records_by_source.items():
        for record in records:
            lookup[_record_key(source, record)] = record

    scored: dict[tuple[str, str], MatchExplanation] = {}
    review_queue: list[tuple[str, str, MatchExplanation]] = []
    uf = UnionFind()

    # Ensure singletons survive into the output even if they match nothing.
    for key in lookup:
        uf.find(key)

    for block_members in blocking_index.values():
        for left_key, right_key in combinations(sorted(block_members), 2):
            if left_key.split(":", 1)[0] == right_key.split(":", 1)[0]:
                continue  # never merge two records from the same source
            pair = (left_key, right_key)
            if pair in scored:
                continue

            explanation = score_pair(lookup[left_key], lookup[right_key])
            scored[pair] = explanation

            if explanation.score >= AUTO_ACCEPT:
                uf.union(left_key, right_key)
            elif explanation.score >= AUTO_REJECT:
                review_queue.append((left_key, right_key, explanation))

    clusters: list[Cluster] = []
    for members in uf.groups().values():
        cluster = Cluster(members=set(members))

        for pair, explanation in scored.items():
            if pair[0] in members and pair[1] in members:
                cluster.evidence.append((pair[0], pair[1], explanation.score))

        # Transitivity check: every implied pair inside the cluster must be at
        # least plausible. A~B and B~C merging A and C is only safe if A~C
        # isn't actively contradicted.
        for left_key, right_key in combinations(sorted(members), 2):
            if left_key.split(":", 1)[0] == right_key.split(":", 1)[0]:
                continue
            implied = scored.get((left_key, right_key))
            if implied is None:
                implied = score_pair(lookup[left_key], lookup[right_key])
            if implied.score < transitivity_floor:
                cluster.needs_review = True
                cluster.review_reason = (
                    f"transitivity violation: {left_key} ~ {right_key} "
                    f"scored {implied.score:.2f}, below floor {transitivity_floor}"
                )
                break

        clusters.append(cluster)

    return clusters, review_queue
