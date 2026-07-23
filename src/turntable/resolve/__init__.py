"""Entity resolution across music sources."""

from .cluster import Cluster, build_clusters
from .normalize import blocking_keys, normalize_artist, normalize_title
from .scoring import MatchExplanation, score_pair

__all__ = [
    "blocking_keys",
    "normalize_artist",
    "normalize_title",
    "MatchExplanation",
    "score_pair",
    "Cluster",
    "build_clusters",
]
