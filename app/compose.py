"""判断のあと、カテゴリ専用の文章だけを作る。Jev には文章を書かせない。"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.catalog import CATEGORY_LABELS, CHANGE_TARGET_LABELS
from app.models import GenerationInfo, Judgment, RouteDecision

_DISCLAIMER = "このチャットでは、利用停止・登録変更・返金は実行しません。"


def specialist_for(category: str) -> tuple[str, str]:
    labels = {
        "card_lost": "盗難・紛失デスク",
        "profile_change": "登録情報変更デスク",
        "statement": "明細案内デスク",
        "unrecognized_charge": "不正利用調査デスク",
        "credit_limit": "限度額案内デスク",
        "points": "ポイント案内デスク",
        "other": "一次受付",
        "clarify": "一次受付",
    }
    key = category if category in labels else "other"
    return key, labels[key]


def system_prompt(category: str) -> str:
    label = CATEGORY_LABELS.get(category, "問い合わせ")
    return (
        f"あなたはアオカード会員サポートの{label}担当です。"
        "日本語で、3〜6文、丁寧語で答えてください。"
        "カード番号と暗証番号を書かせないでください。"
        "会員の明細・残高・限度額の具体的な数値を作らないでください。"
        "利用停止、登録変更、返金が完了したように書かないでください。"
        "判断は既に終わっています。分類の説明はせず、次の一手だけを伝えてください。"
    )


def compose(
    *,
    route: RouteDecision,
    judgment: Judgment,
    collected: dict[str, str],
    transcript: list[dict[str, str]],
) -> tuple[str, GenerationInfo]:
    category = "clarify" if route.route == "clarify" else judgment.category.choice
    key, label = specialist_for(category)
    info = GenerationInfo(engine="template", specialist=key, specialist_label=label)
    if _generation_configured():
        reply = _complete_with_llm(category, route, judgment, collected, transcript)
        if reply:
            info.engine = "llm"
            return reply, info
    return _template(route, judgment, collected), info


def _template(route: RouteDecision, judgment: Judgment, collected: dict[str, str]) -> str:
    if route.route == "clarify":
        return (
            "ご用件をもう少し特定させてください。"
            "カードの紛失、登録情報の変更、利用明細、身に覚えのない請求、限度額、ポイントのどれに近いですか。"
            + _DISCLAIMER
        )

    category = judgment.category.choice
    if category == "card_lost":
        return (
            "カードの盗難・紛失として受け付け、オペレーターへつなぎます。"
            "利用停止と再発行は、登録済みの電話番号で本人確認したうえで進めます。"
            "警察への届出が済んでいれば、受付番号をオペレーターにお伝えください。"
            "カード番号と暗証番号は、このチャットには書かないでください。"
            + _DISCLAIMER
        )
    if category == "unrecognized_charge":
        return (
            "身に覚えのないご利用として、調査窓口のオペレーターへつなぎます。"
            "カードが手元にある場合は、調査が終わるまで破棄せず保管してください。"
            "分かる範囲で、利用日・加盟店名・金額をオペレーターにお知らせください。"
            + _DISCLAIMER
        )
    if category == "profile_change":
        return _profile_reply(judgment, collected)
    if category == "statement":
        if route.route == "ask":
            return (
                "利用明細のご確認ですね。いつの、どの加盟店の、いくら分を見たいですか。"
                "会員アプリの「ご利用明細」でも、日付と加盟店名から探せます。"
                "このチャットからは、お客様の明細は参照できません。"
            )
        return (
            "明細は、会員アプリの「ご利用明細」で利用日・加盟店名・金額を照合できます。"
            "同じ加盟店で同額の行が2つある場合は、二重請求の可能性があるので、その2行の日付を控えてオペレーターへご連絡ください。"
            "このチャットでは金額の内訳を照会できません。"
        )
    if category == "credit_limit":
        return (
            "ご利用限度額と、いま使える枠は会員アプリのホームに表示されます。"
            "一時増額は審査があり、希望額と利用目的が決まっていればアプリの増額申請から進められます。"
            "このチャットでは増額の可否を確定できません。"
        )
    if category == "points":
        return (
            "ポイント残高と有効期限は、会員アプリの「ポイント」に表示されます。"
            "期限の近いポイントから使われるため、旅行や大きな買い物の前にアプリで残数を確認してください。"
            "このチャットでは残高を照会できません。"
        )
    return (
        "自動では手続きを特定できませんでした。オペレーターが内容を伺います。"
        + _DISCLAIMER
    )


def _profile_reply(judgment: Judgment, collected: dict[str, str]) -> str:
    target = collected.get("change_target") or judgment.change_target.choice
    if target == "pin":
        return (
            "暗証番号は、このチャットには入力しないでください。"
            "会員アプリの「暗証番号の変更」から、登録済みの電話番号で本人確認したうえで再設定できます。"
            "変更そのものは、ここでは確定しません。"
        )
    label = CHANGE_TARGET_LABELS.get(target, "変更項目")
    if target in {None, "", "unknown"}:
        return (
            "登録情報の変更ですね。住所、電話番号、氏名、メールアドレスのどれを変えますか。"
            "暗証番号はチャットに書かず、アプリから変更してください。"
        )
    if not collected.get("new_value"):
        return (
            f"{label}の変更を承ります。新しい{label}を教えてください。"
            "反映の前に、登録済みの電話番号へ確認コードを送ります。"
            "このチャットだけでは変更は確定しません。"
        )
    value = collected.get("new_value", "")
    return (
        f"新しい{label}として「{value}」を伺いました。"
        "反映は、登録済みの電話番号で本人確認したあとです。"
        "このチャットでは変更を確定しません。"
    )


def _generation_configured() -> bool:
    return bool(os.environ.get("GENERATION_API_KEY") and os.environ.get("GENERATION_BASE_URL"))


def _complete_with_llm(
    category: str,
    route: RouteDecision,
    judgment: Judgment,
    collected: dict[str, str],
    transcript: list[dict[str, str]],
) -> str | None:
    base = os.environ["GENERATION_BASE_URL"].rstrip("/")
    model = os.environ.get("GENERATION_MODEL", "gpt-4.1-mini")
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt(category)},
        {
            "role": "system",
            "content": (
                f"分岐は {route.route}。理由: {route.reason}。"
                f"カテゴリ: {judgment.category.choice}。収集済み: {collected or 'なし'}。"
                "route が handoff ならオペレーターへつなぐ一文を入れる。"
                "route が ask なら不足している事実を1つだけ質問する。"
                "route が clarify なら6つの用件候補から選ばせる。"
            ),
        },
    ]
    for turn in transcript[-8:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": turn.get("text", "")})
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['GENERATION_API_KEY']}"},
            json={"model": model, "messages": messages, "temperature": 0.2},
            timeout=20.0,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError):
        return None
