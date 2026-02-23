from __future__ import annotations

from typing import Any, Dict, List


def rank_and_limit(items: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    protein = [x for x in items if x.get("bucket") == "protein"]
    daily = [x for x in items if x.get("bucket") == "daily"]
    other = [x for x in items if x.get("bucket") not in ("protein", "daily")]

    def score(it: Dict[str, Any]) -> int:
        tags = set(it.get("tags") or [])
        s = 0
        if "protein-design" in tags:
            s += 5
        if "antibody" in tags:
            s += 3
        if "enzyme" in tags:
            s += 3
        if "preprint" in tags:
            s += 1
        if "blog" in tags:
            s += 1
        return s

    protein.sort(key=score, reverse=True)
    other.sort(key=score, reverse=True)

    lim = cfg.get("limits", {})
    max_total = int(lim.get("max_items_total", 40))
    max_protein = int(lim.get("max_items_protein", 25))
    max_daily = int(lim.get("max_items_daily_knowledge", 2))

    protein = protein[:max_protein]
    daily = daily[:max_daily]
    merged = protein + other + daily
    return merged[:max_total]
