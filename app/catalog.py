"""手続きの定義。判断そのものはここには書かない。"""

from __future__ import annotations

CATEGORIES: dict[str, str] = {
    "card_lost": "カードの盗難・紛失・磁気不良で、利用停止や再発行が必要",
    "profile_change": "住所・電話・氏名・メール・暗証番号など、登録情報の変更",
    "statement": "利用明細、請求金額、引き落とし日、二重に見える請求の確認",
    "unrecognized_charge": "身に覚えのない利用、または不正利用の疑い",
    "credit_limit": "利用限度額、利用可能枠、一時増額",
    "points": "ポイント残高、有効期限、マイルやキャッシュバック",
    "other": "上記のどれにも当てはまらない問い合わせ",
}

CATEGORY_LABELS: dict[str, str] = {
    "card_lost": "盗難・紛失",
    "profile_change": "登録情報変更",
    "statement": "明細・請求",
    "unrecognized_charge": "身に覚えのない利用",
    "credit_limit": "限度額",
    "points": "ポイント",
    "other": "その他",
}

# ボットが手続きを実行すると危険なカテゴリ。確信度がそこそこあれば人へ渡す。
SENSITIVE_CATEGORIES = frozenset({"card_lost", "unrecognized_charge"})

CHANGE_TARGETS: dict[str, str] = {
    "address": "住所・届出先の変更",
    "phone": "電話番号の変更",
    "name": "氏名の変更",
    "email": "メールアドレスの変更",
    "pin": "暗証番号の変更・再設定",
    "unknown": "変更項目がまだ特定できない、または登録情報の変更ではない",
}

CHANGE_TARGET_LABELS: dict[str, str] = {
    "address": "住所",
    "phone": "電話番号",
    "name": "氏名",
    "email": "メールアドレス",
    "pin": "暗証番号",
    "unknown": "未特定",
}

TONES: dict[str, str] = {
    "calm": "事実を淡々と伝えている",
    "concerned": "困っているが、攻撃的ではない",
    "angry": "強い非難、怒り、脅し、繰り返しの苦情",
}

TONE_LABELS: dict[str, str] = {
    "calm": "落ち着いている",
    "concerned": "困っている",
    "angry": "強い不満",
}

# Score は並び順が尺度。0 が最も低く、末尾が最も高い。
URGENCY_CRITERIA: list[str] = [
    "待てる。被害の拡大も、今日中でなければならない期限もない",
    "当日中に扱いたい",
    "今すぐ。被害が広がる、カードが第三者の手元にある、支払いが止まる、など",
]

URGENCY_LABELS: list[str] = ["待てる", "当日中", "今すぐ"]

# 確信度はリスクで変える。低いときに危険な手続きへ進まない。
CATEGORY_CONFIDENCE_FLOOR = 0.45
SENSITIVE_CONFIDENCE_FLOOR = 0.40
HANDOFF_PROBABILITY = 0.85
ANGRY_HANDOFF_PROBABILITY = 0.72
MISSING_INFO_PROBABILITY = 0.55

ROUTE_LABELS: dict[str, str] = {
    "handoff": "オペレーターへつなぐ",
    "ask": "足りない事実を聞く",
    "answer": "その場で案内する",
    "clarify": "用件を聞き直す",
}
