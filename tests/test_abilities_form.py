import pytest

from app.abilities.form import AbilityForm, IncreaseForm


def test_scores_blanks_and_junk_become_none():
    form = AbilityForm(strength=" 15 ", dexterity="", constitution="abc", intelligence="-1")
    scores = form.scores()
    assert scores["strength"] == 15
    assert scores["dexterity"] is None
    assert scores["constitution"] is None
    assert scores["intelligence"] == -1
    assert scores["charisma"] is None


def test_digits_int_cant_read_become_none():
    assert AbilityForm(strength="²").scores()["strength"] is None
    assert AbilityForm(rolls=["²"]).roll_values()[0] is None


def test_out_of_range_values_reach_validation():
    assert AbilityForm(strength="100").scores()["strength"] == 100
    assert AbilityForm(rolls=["-3"]).roll_values()[0] == -3


def test_rolls_pad_to_six():
    assert AbilityForm(rolls=["12", "x"]).roll_values() == [12, None, None, None, None, None]


@pytest.mark.parametrize(("method", "shown"), [("point_buy", "point_buy"), ("x", "standard_array")])
def test_editor_method_falls_back_to_the_standard_array(method, shown):
    assert AbilityForm(method=method).editor_method == shown


def test_point_buy_preview_starts_at_8_and_steps():
    form = AbilityForm(method="point_buy", strength="14", step="strength:1")
    scores = form.previewed_scores()
    assert scores["strength"] == 15
    assert scores["charisma"] == 8


def test_reset_clears_the_assignments():
    form = AbilityForm(method="standard_array", strength="15", reset="1")
    assert set(form.previewed_scores().values()) == {None}


@pytest.mark.parametrize(("changed", "kept"), [("plus2", ("STR", "")), ("plus1", ("", "STR"))])
def test_the_column_just_clicked_wins_a_clash(changed, kept):
    form = IncreaseForm(plus2="STR", plus1="STR", changed=changed)
    form.resolve_clash()
    assert (form.plus2, form.plus1) == kept
