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

# 本機：repo 根目錄的 data/。
# 部署（Day 19）：只有 app/ 會被打包上去，repo 的目錄結構不在了，
# 所以部署腳本會把清單複製一份到 app/_bundled/，這裡先找那份。
# 以前兩個都找不到時回空清單，雲端上看起來就是「永遠查無資源」，不會報錯。
# 清單裡目前一筆 verified 都沒有，查無資源本來就是正常結果，根本分不出來，
# 所以找不到檔案改成直接報錯。
_BUNDLED = Path(__file__).resolve().parents[1] / "_bundled" / "resources.json"
_REPO = Path(__file__).resolve().parents[3] / "data" / "resources" / "resources.json"
_DATA = _BUNDLED if _BUNDLED.exists() else _REPO


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
        raise FileNotFoundError(f"找不到資源清單：{_DATA}（部署時有沒有打包進 app/_bundled/？）")
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
