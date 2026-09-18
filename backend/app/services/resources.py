"""學習資源查詢。

刻意只讀本地 JSON，不串搜尋引擎也不爬蟲（全域範圍已排除）。
理由不只是省事：模型很會生成看起來合理但不存在的課程連結，
而一份人工核實過的清單是唯一能保證連結真的打得開的做法。

每一筆都有 verified 欄位。false 的不會被推薦出去 ——
寧可資源少，也不要推一個連不上的網址給正在找工作的人。
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

_DATA = Path(__file__).resolve().parents[3] / "data" / "resources" / "resources.json"


class Resource(BaseModel):
    id: str
    title: str
    url: str
    kind: str = Field(description="course / doc / book / tutorial")
    topics: list[str] = Field(default_factory=list)
    hours: float | None = None
    language: str = "en"
    verified: bool = Field(
        default=False, description="人工開過連結確認存在才設 true"
    )
    verified_at: str | None = None


@lru_cache
def load_all() -> list[Resource]:
    if not _DATA.exists():
        return []
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    return [Resource.model_validate(r) for r in raw]


def verified_only() -> list[Resource]:
    return [r for r in load_all() if r.verified]


def by_id(resource_id: str) -> Resource | None:
    return next((r for r in verified_only() if r.id == resource_id), None)


def search(topics: list[str], limit: int = 5) -> list[Resource]:
    """用主題關鍵字找資源。只回 verified 的。"""
    wanted = {t.casefold() for t in topics}
    scored = []
    for r in verified_only():
        hits = len(wanted & {t.casefold() for t in r.topics})
        if hits:
            scored.append((hits, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def known_ids() -> set[str]:
    return {r.id for r in verified_only()}
