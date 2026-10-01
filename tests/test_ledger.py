import pytest

from arcadekit.ledger import BY, OLD_LABELS, Ledger


def make():
    lines = []
    return Ledger(lambda **record: lines.append(record)), lines


def test_a_booked_move_is_logged_and_counted_by_who_and_through_what():
    ledger, lines = make()
    ledger.book("model", "junction", proposed="UP", executed="UP")
    ledger.book("code-override", "reflex", proposed="LEFT", executed="DOWN")
    ledger.count("code-skill", "park")
    assert lines == [{"event": "move", "by": "model", "via": "junction", "proposed": "UP", "executed": "UP"},
                     {"event": "move", "by": "code-override", "via": "reflex", "proposed": "LEFT", "executed": "DOWN"}]
    assert ledger.by() == {"model": 1, "code-override": 1, "code-skill": 1}
    assert ledger.model_share() == pytest.approx(1 / 3)


def test_who_made_a_move_is_a_fixed_vocabulary_a_game_cannot_extend():
    ledger, _ = make()
    with pytest.raises(ValueError):
        ledger.book("reflex-override", "junction")
    with pytest.raises(ValueError):
        ledger.count("code-hold", "park")


def test_the_summary_gives_the_models_own_share():
    ledger, _ = make()
    assert ledger.model_share() is None and ledger.summary() == "no booked moves"
    for _ in range(3):
        ledger.book("model", "junction")
    ledger.book("code-late", "junction")
    assert ledger.summary().endswith("The model's own: 75%.")


def test_every_label_written_before_the_ledger_maps_onto_the_vocabulary():
    assert all(by in BY for by, _ in OLD_LABELS.values())
