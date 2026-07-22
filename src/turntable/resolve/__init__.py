"""Entity resolution across music sources."""

from .normalize import blocking_keys, normalize_artist, normalize_title
from .scoring import MatchExplanation, score_pair
from .cluster import Cluster, build_clusters

__all__ = [
    "blocking_keys",
    "normalize_artist",
    "normalize_title",
    "MatchExplanation",
    "score_pair",
    "Cluster",
    "build_clusters",
]
