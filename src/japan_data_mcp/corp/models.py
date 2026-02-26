"""法人番号 API データモデル."""

from __future__ import annotations

from pydantic import BaseModel


class Corporation(BaseModel):
    """法人情報."""

    corporate_number: str
    """法人番号（13桁）."""

    name: str
    """法人名."""

    kind: str = ""
    """法人種別コード（101=国の機関, 201=地方公共団体, 301=株式会社, 等）."""

    prefecture_name: str = ""
    """所在地: 都道府県."""

    city_name: str = ""
    """所在地: 市区町村."""

    street_number: str = ""
    """所在地: 丁目番地."""

    post_code: str = ""
    """郵便番号."""

    prefecture_code: str = ""
    """都道府県コード（2桁）."""

    city_code: str = ""
    """市区町村コード（5桁）."""

    assignment_date: str = ""
    """法人番号指定年月日."""

    update_date: str = ""
    """更新年月日."""

    change_date: str = ""
    """変更年月日."""

    close_date: str = ""
    """閉鎖年月日（空文字列 = 現存）."""

    close_cause: str = ""
    """閉鎖事由."""

    furigana: str = ""
    """法人名フリガナ."""

    process: str = ""
    """処理区分（01=新規, 11=商号変更, 等）."""

    @property
    def kind_label(self) -> str:
        """法人種別の日本語ラベル."""
        return _KIND_LABELS.get(self.kind, self.kind)

    @property
    def is_active(self) -> bool:
        """現存法人かどうか."""
        return not self.close_date

    @property
    def full_address(self) -> str:
        """所在地（結合済み）."""
        return f"{self.prefecture_name}{self.city_name}{self.street_number}"

    @property
    def verification_url(self) -> str:
        """法人番号公表サイトの検証用URL."""
        return (
            "https://www.houjin-bangou.nta.go.jp/"
            f"henkorireki-johoto.html?selHouzinNo={self.corporate_number}"
        )


class CorpApiError(Exception):
    """法人番号 API エラー."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"法人番号API エラー ({status_code}): {message}")


# 法人種別コード → ラベル
_KIND_LABELS: dict[str, str] = {
    "101": "国の機関",
    "201": "地方公共団体",
    "301": "株式会社",
    "302": "有限会社",
    "303": "合名会社",
    "304": "合資会社",
    "305": "合同会社",
    "399": "その他の設立登記法人",
    "401": "外国会社等",
    "499": "その他",
}
