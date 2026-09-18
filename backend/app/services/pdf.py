"""履歷 PDF 的文字抽取。

刻意只用 pypdf，不引入任何雲端解析服務（全域範圍已排除）。

抽取失敗的情況分成幾種，各自回不同的訊息，因為使用者能做的補救不一樣：
- 加密：請對方先解除密碼
- 掃描檔（整份抽不出文字）：請對方改貼純文字
- 部分頁面抽不到：照樣回傳，但標出哪幾頁是空的讓使用者自己判斷
"""

from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# 一頁少於這個字數就當作「幾乎沒抽到東西」，通常是掃描或整頁都是圖。
_MIN_CHARS_PER_PAGE = 20


class PdfExtractError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ExtractedPdf:
    text: str
    page_count: int
    char_count: int
    empty_pages: list[int] = field(default_factory=list)

    @property
    def warning(self) -> str | None:
        if not self.empty_pages:
            return None
        pages = "、".join(str(p) for p in self.empty_pages)
        return f"第 {pages} 頁幾乎沒有抽到文字，可能是圖片或掃描。請確認下方內容是否完整。"


def extract_text(data: bytes, *, max_bytes: int, max_pages: int) -> ExtractedPdf:
    if not data:
        raise PdfExtractError("檔案是空的")
    if len(data) > max_bytes:
        raise PdfExtractError(
            f"檔案 {len(data) / 1_048_576:.1f} MB，超過上限 {max_bytes / 1_048_576:.0f} MB"
        )

    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as e:
        raise PdfExtractError(f"這個檔案不是有效的 PDF（{e}）") from e

    if reader.is_encrypted:
        # 有些 PDF 只設了空密碼，試著解開；解不開才報錯。
        try:
            if reader.decrypt("") == 0:
                raise PdfExtractError("PDF 有密碼保護，請先解除密碼再上傳")
        except (NotImplementedError, PdfReadError) as e:
            raise PdfExtractError("PDF 有密碼保護，請先解除密碼再上傳") from e

    page_count = len(reader.pages)
    if page_count == 0:
        raise PdfExtractError("這個 PDF 沒有任何頁面")
    if page_count > max_pages:
        raise PdfExtractError(f"這份 PDF 有 {page_count} 頁，超過上限 {max_pages} 頁")

    parts: list[str] = []
    empty_pages: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # pypdf 對破損頁面會丟各種例外，單頁失敗不該讓整份失敗
            text = ""
        if len(text) < _MIN_CHARS_PER_PAGE:
            empty_pages.append(i)
        parts.append(text)

    full = "\n\n".join(p for p in parts if p).strip()
    if not full:
        raise PdfExtractError(
            "整份 PDF 都抽不出文字，可能是掃描檔或純圖片。請改用純文字貼上。",
            status_code=422,
        )

    return ExtractedPdf(
        text=full,
        page_count=page_count,
        char_count=len(full),
        empty_pages=empty_pages,
    )
