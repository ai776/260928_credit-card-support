"""問い合わせ本文から、Jev（またはキーが無いときの下書き）で判断を取る。"""

from __future__ import annotations

import os
import time
from typing import Protocol

from app.catalog import (
    CATEGORIES,
    CATEGORY_LABELS,
    CHANGE_TARGET_LABELS,
    CHANGE_TARGETS,
    TONE_LABELS,
    TONES,
    URGENCY_CRITERIA,
    URGENCY_LABELS,
)
from app.models import ChoiceView, Judgment, ScoreView

CategoryKey = str


class SupportJudge(Protocol):
    def judge(self, state: dict) -> Judgment: ...


def questions() -> dict:
    from typesafe_sdk import Choice, Noul, Score

    return {
        "category": Choice(
            instructions=(
                "会話全体として、顧客がいま進めたいクレジットカードの手続きはどれか。"
                "active_procedure がある場合、直近の発話が別件を明示しない限りそれを維持する。"
                "住所や電話番号だけの発話は、直前が登録情報変更なら profile_change のままにする。"
            ),
            criteria=CATEGORIES,
        ),
        "urgency": Score(
            instructions="この問い合わせを、被害の広がりと期限の切迫から見てどの程度急ぐべきか。",
            criteria=URGENCY_CRITERIA,
        ),
        "tone": Choice(
            instructions="顧客の話し方はどの調子に近いか。",
            criteria=TONES,
        ),
        "change_target": Choice(
            instructions=(
                "登録情報の変更なら、どの項目か。"
                "会話全体と collected を見て、すでに特定済みならそれを維持する。"
                "登録情報の変更でなければ unknown。"
            ),
            criteria=CHANGE_TARGETS,
        ),
        "handoff": Noul(
            instructions=(
                "この会話は、チャットボットの案内だけでは完結せず、"
                "人間のオペレーターが本人確認または例外対応をすべきである。"
            ),
        ),
        "missing_info": Noul(
            instructions=(
                "次の案内に進む前に、顧客へまだ確認すべき事実がある。"
                "collected に手続きへ必要な値が既にあるなら、この文は偽である。"
            ),
        ),
    }


def _choice(choice: str, confidence: float, probabilities: dict[str, float], labels: dict[str, str]) -> ChoiceView:
    return ChoiceView(
        choice=choice,
        label=labels.get(choice, choice),
        confidence=confidence,
        probabilities=probabilities,
    )


def _urgency(score: float, confidence: float) -> ScoreView:
    index = min(len(URGENCY_LABELS) - 1, max(0, int(round(score))))
    return ScoreView(score=score, label=URGENCY_LABELS[index], confidence=confidence)


class JevJudge:
    def __init__(self) -> None:
        from typesafe_sdk import TypeSafeClient

        self._client = TypeSafeClient(model=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"))

    def judge(self, state: dict) -> Judgment:
        started = time.perf_counter()
        response = self._client.system_one(state, questions())
        latency_ms = (time.perf_counter() - started) * 1000

        category = response.choices["category"]
        urgency = response.scores["urgency"]
        tone = response.choices["tone"]
        change_target = response.choices["change_target"]

        return Judgment(
            engine="jev",
            model=getattr(response, "model", None),
            latency_ms=round(latency_ms, 1),
            category=_choice(
                category.choice,
                category.confidence,
                dict(category.probabilities),
                CATEGORY_LABELS,
            ),
            urgency=_urgency(float(urgency.score), float(urgency.confidence)),
            tone=_choice(tone.choice, tone.confidence, dict(tone.probabilities), TONE_LABELS),
            change_target=_choice(
                change_target.choice,
                change_target.confidence,
                dict(change_target.probabilities),
                CHANGE_TARGET_LABELS,
            ),
            handoff_probability=float(response.nouls["handoff"].noul),
            missing_info_probability=float(response.nouls["missing_info"].noul),
        )


_KEYWORD_SCORES: dict[str, tuple[tuple[str, int], ...]] = {
    "card_lost": (
        ("紛失", 3),
        ("落とし", 3),
        ("落として", 3),
        ("盗難", 3),
        ("盗まれ", 3),
        ("なくし", 2),
        ("見当たらない", 2),
        ("再発行", 2),
        ("利用停止", 2),
        ("止めて", 2),
    ),
    "unrecognized_charge": (
        ("身に覚え", 4),
        ("覚えのない", 3),
        ("知らない店", 4),
        ("不正", 3),
        ("使っていない", 2),
    ),
    "profile_change": (
        ("引っ越し", 3),
        ("住所", 2),
        ("電話番号", 3),
        ("氏名", 2),
        ("メール", 2),
        ("登録情報", 3),
        ("暗証", 3),
    ),
    "statement": (
        ("明細", 3),
        ("引き落とし", 3),
        ("請求金額", 3),
        ("二重", 2),
    ),
    "credit_limit": (
        ("限度額", 4),
        ("増額", 3),
        ("利用枠", 3),
        ("利用可能", 2),
    ),
    "points": (
        ("ポイント", 3),
        ("有効期限", 2),
        ("マイル", 3),
    ),
}

_ANGRY = ("ふざけ", "最悪", "苦情", "怒り", "対応しろ", "馬鹿", "バカ")
_URGENT = ("今すぐ", "すぐに", "至急", "急ぎ", "盗")


class HeuristicJudge:
    """APIキーが無いとき、画面確認用の下書き判断。較正された確信度ではない。"""

    def judge(self, state: dict) -> Judgment:
        started = time.perf_counter()
        text = _customer_text(state)
        latest = str(state.get("latest_message") or "")
        latest_scores = _score(latest)
        active = state.get("active_procedure")
        if any(latest_scores.values()):
            scores = latest_scores
            category = max(scores, key=scores.get)
            confidence = min(0.93, 0.52 + scores[category] * 0.08)
        elif active in CATEGORIES and active != "other":
            scores = {key: 0 for key in CATEGORIES if key != "other"}
            category = str(active)
            confidence = 0.62
        else:
            scores = {key: 0 for key in CATEGORIES if key != "other"}
            category = "other"
            confidence = 0.34

        probabilities = _softmax_like(scores, category)

        change_target, target_confidence = _guess_target(latest, text, state)
        tone = _guess_tone(latest)
        urgency_index = (
            2
            if any(word in latest for word in _URGENT) or latest_scores.get("card_lost", 0)
            else 1
            if "今日" in latest
            else 0
        )
        missing = _missing_info(category, state, change_target)
        handoff = 0.9 if category in {"card_lost", "unrecognized_charge"} else 0.78 if tone == "angry" else 0.18

        latency_ms = (time.perf_counter() - started) * 1000
        return Judgment(
            engine="heuristic",
            model=None,
            latency_ms=round(latency_ms, 1),
            category=_choice(category, confidence, probabilities, CATEGORY_LABELS),
            urgency=_urgency(float(urgency_index), 0.7),
            tone=_choice(tone, 0.7, {tone: 0.7, **{k: 0.15 for k in TONES if k != tone}}, TONE_LABELS),
            change_target=_choice(
                change_target,
                target_confidence,
                {change_target: target_confidence},
                CHANGE_TARGET_LABELS,
            ),
            handoff_probability=handoff,
            missing_info_probability=missing,
            note="TYPESAFE_API_KEY が無いため、キーワードの下書き判断です。確信度は較正されていません。",
        )


def _score(text: str) -> dict[str, int]:
    return {
        key: sum(weight for word, weight in rules if word in text)
        for key, rules in _KEYWORD_SCORES.items()
    }


def _customer_text(state: dict) -> str:
    lines = [str(state.get("latest_message") or "")]
    for turn in state.get("transcript") or []:
        if isinstance(turn, dict) and turn.get("role") == "user":
            lines.append(str(turn.get("text") or ""))
    return "\n".join(lines)


def _softmax_like(scores: dict[str, int], winner: str) -> dict[str, float]:
    if all(value == 0 for value in scores.values()):
        probs = {key: 0.04 for key in scores}
        probs["other"] = 0.12 if winner == "other" else 0.06
        probs[winner] = 0.76
        scale = sum(probs.values())
        return {key: round(value / scale, 3) for key, value in probs.items()}
    total = sum(scores.values()) or 1
    raw = {key: value / total for key, value in scores.items()}
    raw["other"] = 0.05
    scale = sum(raw.values())
    return {key: round(value / scale, 3) for key, value in raw.items()}


def _guess_target(latest: str, text: str, state: dict) -> tuple[str, float]:
    collected = state.get("collected") or {}
    previous = collected.get("change_target")
    named_now = _named_field(latest)
    if named_now:
        return named_now, 0.8
    if previous in CHANGE_TARGETS and previous != "unknown":
        return str(previous), 0.66
    named_before = _named_field(text)
    if named_before:
        return named_before, 0.7
    return "unknown", 0.4


def _named_field(text: str) -> str | None:
    rules = (
        ("pin", ("暗証",)),
        ("email", ("メール",)),
        ("phone", ("電話",)),
        ("name", ("氏名", "改姓")),
        ("address", ("住所", "引っ越し", "転居")),
    )
    for key, words in rules:
        if any(word in text for word in words):
            return key
    return None


def _guess_tone(text: str) -> str:
    if any(word in text for word in _ANGRY):
        return "angry"
    if any(word in text for word in ("困っ", "不安", "心配", "どうすれば")):
        return "concerned"
    return "calm"


def _missing_info(category: str, state: dict, change_target: str) -> float:
    collected = state.get("collected") or {}
    if category == "profile_change":
        if change_target == "pin":
            return 0.1
        if change_target in {None, "unknown"}:
            return 0.84
        if not collected.get("new_value"):
            return 0.88
        return 0.12
    if category == "statement":
        latest = str(state.get("latest_message") or "")
        if any(token in latest for token in ("円", "店", "月")):
            return 0.28
        return 0.8
    return 0.2
