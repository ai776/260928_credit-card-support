"""Jev の出力を、手続きの分岐に変える。判断の中身はモデル、危険度のしきい値はコード。"""

from __future__ import annotations

from app.catalog import (
    ANGRY_HANDOFF_PROBABILITY,
    CATEGORY_CONFIDENCE_FLOOR,
    HANDOFF_PROBABILITY,
    MISSING_INFO_PROBABILITY,
    SENSITIVE_CATEGORIES,
    SENSITIVE_CONFIDENCE_FLOOR,
)
from app.models import Judgment, RouteDecision


def decide(judgment: Judgment) -> RouteDecision:
    category = judgment.category.choice
    confidence = judgment.category.confidence

    if category in SENSITIVE_CATEGORIES:
        if confidence < SENSITIVE_CONFIDENCE_FLOOR:
            return RouteDecision(
                route="clarify",
                reason="利用停止や不正調査に進むには、用件の確信度が足りない",
            )
        return RouteDecision(
            route="handoff",
            reason="利用停止や不正調査は本人確認が必要なので、オペレーターが対応する",
        )

    if confidence < CATEGORY_CONFIDENCE_FLOOR or category == "other":
        return RouteDecision(
            route="clarify",
            reason="定義した手続きのどれかへ、まだ確定できない",
        )

    if judgment.handoff_probability >= HANDOFF_PROBABILITY or (
        judgment.tone.choice == "angry"
        and judgment.handoff_probability >= ANGRY_HANDOFF_PROBABILITY
    ):
        return RouteDecision(
            route="handoff",
            reason="自動の案内では収まりきらないため、オペレーターが対応する",
        )

    if judgment.missing_info_probability >= MISSING_INFO_PROBABILITY:
        return RouteDecision(
            route="ask",
            reason="案内の前に、顧客へ確認する事実が残っている",
        )

    return RouteDecision(
        route="answer",
        reason="カテゴリが決まり、案内に足る内容が揃っている",
    )
