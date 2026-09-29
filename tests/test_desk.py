from app.catalog import CATEGORY_LABELS, TONE_LABELS, CHANGE_TARGET_LABELS
from app.judge import HeuristicJudge
from app.models import ChoiceView, Judgment, ScoreView
from app.routing import decide
from app.service import Desk, redact


def _choice(choice: str, confidence: float, labels: dict[str, str]) -> ChoiceView:
    return ChoiceView(choice=choice, label=labels[choice], confidence=confidence, probabilities={choice: confidence})


def _judgment(
    category: str,
    confidence: float = 0.9,
    tone: str = "calm",
    handoff: float = 0.1,
    missing: float = 0.1,
    target: str = "unknown",
) -> Judgment:
    return Judgment(
        engine="heuristic",
        latency_ms=1,
        category=_choice(category, confidence, CATEGORY_LABELS),
        urgency=ScoreView(score=0, label="待てる", confidence=0.8),
        tone=_choice(tone, 0.8, TONE_LABELS),
        change_target=_choice(target, 0.8, CHANGE_TARGET_LABELS),
        handoff_probability=handoff,
        missing_info_probability=missing,
    )


def test_sensitive_categories_go_to_a_person() -> None:
    lost = decide(_judgment("card_lost", confidence=0.5))
    fraud = decide(_judgment("unrecognized_charge", confidence=0.5))
    assert lost.route == "handoff"
    assert fraud.route == "handoff"


def test_uncertain_sensitive_case_asks_again() -> None:
    decision = decide(_judgment("card_lost", confidence=0.2))
    assert decision.route == "clarify"


def test_low_confidence_does_not_pick_a_procedure() -> None:
    decision = decide(_judgment("statement", confidence=0.3))
    assert decision.route == "clarify"


def test_missing_facts_ask_before_answering() -> None:
    decision = decide(_judgment("profile_change", missing=0.8, target="address"))
    assert decision.route == "ask"


def test_complete_profile_change_is_answered() -> None:
    decision = decide(_judgment("profile_change", missing=0.1, target="address"))
    assert decision.route == "answer"


def test_angry_customer_is_handed_off() -> None:
    decision = decide(_judgment("statement", tone="angry", handoff=0.75))
    assert decision.route == "handoff"


def test_card_number_is_removed_before_it_is_stored() -> None:
    assert "4111" not in redact("カード番号は 4111 1111 1111 1111 です")


def test_desk_routes_a_lost_card_and_then_collects_an_address() -> None:
    desk = Desk(judge=HeuristicJudge())
    first = desk.reply("財布を落としてカードが見当たりません。すぐに止めてください。", None)
    assert first.route == "handoff"
    assert first.judgment.category.choice == "card_lost"
    assert "オペレーター" in first.reply
    assert "実行しません" in first.reply

    second = desk.reply("引っ越ししたので登録住所を変えてください。", None)
    assert second.judgment.category.choice == "profile_change"
    assert second.route == "ask"
    assert "住所" in second.reply

    third = desk.reply("東京都港区芝公園4-2-8", second.session_id)
    assert third.route == "answer"
    assert "芝公園4-2-8" in third.reply
    assert "記録しました" not in third.reply
    assert "確定しません" in third.reply
    assert third.generation.specialist == "profile_change"


def test_a_place_in_a_theft_report_is_not_treated_as_a_new_address() -> None:
    desk = Desk(judge=HeuristicJudge())
    result = desk.reply("東京都のATMでカードを盗まれました。止めてください。", None)
    assert result.judgment.category.choice == "card_lost"
    assert result.route == "handoff"
    assert "伺いました" not in result.reply


def test_same_session_can_switch_from_theft_to_an_address_change() -> None:
    desk = Desk(judge=HeuristicJudge())
    first = desk.reply("財布を落としてカードが見当たりません。すぐに止めてください。", None)
    second = desk.reply("引っ越ししたので登録住所を変えてください。", first.session_id)
    assert second.judgment.category.choice == "profile_change"
    assert second.route == "ask"
    third = desk.reply("東京都港区芝公園4-2-8", first.session_id)
    assert third.route == "answer"
    assert "芝公園4-2-8" in third.reply
    assert "確定しません" in third.reply


def test_pin_is_never_collected_in_chat() -> None:
    desk = Desk(judge=HeuristicJudge())
    result = desk.reply("暗証番号を変更したいです。", None)
    assert "入力しない" in result.reply
    assert result.route == "answer"


def test_points_stay_on_the_points_desk() -> None:
    desk = Desk(judge=HeuristicJudge())
    result = desk.reply("ポイントの有効期限はいつですか。", None)
    assert result.judgment.category.choice == "points"
    assert result.route == "answer"
    assert result.generation.specialist_label == "ポイント案内デスク"
