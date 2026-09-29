"""会話の状態を持ち、判断してから文章を作る。"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field

from dotenv import load_dotenv

from app.catalog import ROUTE_LABELS
from app.compose import compose
from app.judge import HeuristicJudge, JevJudge, SupportJudge
from app.models import ChatResponse, Judgment
from app.routing import decide

load_dotenv()

_PAN = re.compile(r"(?:\d[ -]?){13,19}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"0\d{1,4}[-−ー]?\d{1,4}[-−ー]?\d{3,4}")
_ADDRESS = re.compile(
    r"((?:北海道|東京都|京都府|大阪府|[\u4e00-\u9fff]{2,3}県)[^\n。]{4,80})"
)


@dataclass
class Session:
    category: str | None = None
    slots: dict[str, str] = field(default_factory=dict)
    transcript: list[dict[str, str]] = field(default_factory=list)


class Desk:
    def __init__(self, judge: SupportJudge | None = None) -> None:
        self.sessions: dict[str, Session] = {}
        self._jev: JevJudge | None = None
        self._heuristic = HeuristicJudge()
        self._judge = judge

    def reply(self, message: str, session_id: str | None) -> ChatResponse:
        session_id = session_id or uuid.uuid4().hex
        self._remember(session_id)
        session = self.sessions[session_id]
        cleaned = redact(message.strip())
        preview = _preview_slots(session, cleaned)

        state = {
            "product": "アオカード会員サポート",
            "policy": "判断と案内のみ。利用停止、登録変更、返金は実行しない。カード番号と暗証番号は受け取らない。",
            "active_procedure": session.category,
            "collected": preview,
            "transcript": list(session.transcript),
            "latest_message": cleaned,
        }
        judgment = self._judge_state(state)
        _commit(session, judgment, cleaned)
        decision = decide(judgment)
        session.transcript.append({"role": "user", "text": cleaned})
        reply, generation = compose(
            route=decision,
            judgment=judgment,
            collected=session.slots,
            transcript=session.transcript,
        )
        session.transcript.append({"role": "assistant", "text": reply})
        session.transcript = session.transcript[-16:]
        if decision.route == "clarify":
            session.category = None
            session.slots.clear()

        return ChatResponse(
            session_id=session_id,
            reply=reply,
            route=decision.route,
            route_label=ROUTE_LABELS[decision.route],
            reason=decision.reason,
            judgment=judgment,
            generation=generation,
        )

    def _judge_state(self, state: dict) -> Judgment:
        if self._judge is not None:
            return self._judge.judge(state)
        if not os.environ.get("TYPESAFE_API_KEY"):
            return self._heuristic.judge(state)
        try:
            if self._jev is None:
                self._jev = JevJudge()
            return self._jev.judge(state)
        except Exception:
            fallback = self._heuristic.judge(state)
            fallback.note = "Jev を呼び出せなかったため、キーワードの下書き判断に切り替えました。"
            return fallback

    def _remember(self, session_id: str) -> None:
        if session_id not in self.sessions:
            if len(self.sessions) >= 200:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[session_id] = Session()


def redact(text: str) -> str:
    return _PAN.sub("［カード番号は受け取りません］", text)


def _preview_slots(session: Session, message: str) -> dict[str, str]:
    if session.category != "profile_change" and not _mentions_profile(message):
        return {}
    preview = Session(
        category="profile_change",
        slots={} if session.category != "profile_change" else dict(session.slots),
    )
    _absorb_slots(preview, message)
    return preview.slots


def _commit(session: Session, judgment: Judgment, message: str) -> None:
    category = judgment.category.choice
    if category == "other":
        return
    if category != session.category:
        session.slots.clear()
        session.category = category
    if category != "profile_change":
        session.slots.clear()
        return
    _absorb_slots(session, message)
    target = judgment.change_target.choice
    if target not in {"", "unknown"}:
        previous = session.slots.get("change_target")
        if previous and previous != target:
            session.slots.pop("new_value", None)
        session.slots["change_target"] = target
    if target == "pin":
        session.slots.pop("new_value", None)


def _mentions_profile(message: str) -> bool:
    return any(
        word in message
        for word in ("住所", "引っ越し", "転居", "電話", "メール", "氏名", "改姓", "暗証", "登録情報")
    )


def _absorb_slots(session: Session, message: str) -> None:
    if session.category != "profile_change" and not _mentions_profile(message):
        return
    target = session.slots.get("change_target") if session.category == "profile_change" else None
    named = _field_named_in(message)
    if named:
        target = named
    if target == "address" or ("住所" in message or "引っ越し" in message or "転居" in message):
        match = _ADDRESS.search(message)
        if match:
            session.slots["change_target"] = "address"
            session.slots["new_value"] = _trim_value(match.group(1))
            return
    if target == "email" or "メール" in message:
        match = _EMAIL.search(message)
        if match:
            session.slots["change_target"] = "email"
            session.slots["new_value"] = match.group(0)
            return
    if target == "phone" or "電話" in message:
        match = _PHONE.search(message)
        if match:
            session.slots["change_target"] = "phone"
            session.slots["new_value"] = match.group(0)
            return
    if named:
        session.slots["change_target"] = named
        return
    if target in {"address", "name"} and _looks_like_value(message):
        switched = ("電話", "メール", "暗証", "限度", "明細", "ポイント", "紛失", "盗難")
        if not any(word in message for word in switched):
            session.slots["change_target"] = target
            session.slots["new_value"] = _trim_value(message)


def _field_named_in(message: str) -> str | None:
    rules = (
        ("pin", ("暗証",)),
        ("email", ("メール",)),
        ("phone", ("電話",)),
        ("name", ("氏名", "改姓")),
        ("address", ("住所", "引っ越し", "転居")),
    )
    for key, words in rules:
        if any(word in message for word in words):
            return key
    return None


def _looks_like_value(message: str) -> bool:
    if len(message) < 2 or len(message) > 80:
        return False
    blockers = ("ですか", "教えて", "変更", "お願い", "したい", "？", "?")
    return not any(word in message for word in blockers)


def _trim_value(value: str) -> str:
    trimmed = re.sub(r"(に変更|へ変更|に変え|へ変え|お願いします|お願い).*$", "", value)
    return trimmed.strip(" 　、。")
