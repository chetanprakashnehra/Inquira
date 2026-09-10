from typing import List, Dict, Any
from app.config import settings


class ReciprocalRankFusion:
    """Combines multiple ranked lists using Reciprocal Rank Fusion (RRF)."""

    @staticmethod
    def fuse(
        ranked_lists: List[List[Dict[str, Any]]],
        k: int = None,
        top_n: int = None
    ) -> List[Dict[str, Any]]:
        """
        Merge multiple candidate result lists into a single ranked list.
        Each item in ranked_lists is expected to have 'point_id' and 'payload'.
        """
        k = k or settings.RRF_K
        top_n = top_n or settings.TOP_K_FUSED

        rrf_scores: Dict[str, float] = {}
        items_by_id: Dict[str, Dict[str, Any]] = {}

        for ranked_list in ranked_lists:
            for rank, item in enumerate(ranked_list, start=1):
                point_id = item.get("point_id") or str(item.get("id"))
                if not point_id:
                    continue
                
                items_by_id[point_id] = item
                score = 1.0 / (k + rank)
                rrf_scores[point_id] = rrf_scores.get(point_id, 0.0) + score

        # Sort point_ids by descending RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda pid: rrf_scores[pid], reverse=True)

        fused_results: List[Dict[str, Any]] = []
        for pid in sorted_ids[:top_n]:
            item = items_by_id[pid].copy()
            item["rrf_score"] = rrf_scores[pid]
            fused_results.append(item)

        return fused_results
