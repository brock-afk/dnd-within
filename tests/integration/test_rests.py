from app.sheet.models import CharacterHpEffect
from app.sheet.rests import long_rest
from app.sheet.service import hp_view, play_state


def test_long_rest_ends_max_hp_effects_and_restores_hp(db, character):
    db.add_all(
        [
            CharacterHpEffect(character_id=character.id, label="Wight drain", max_hp_delta=-3),
            CharacterHpEffect(character_id=character.id, label="Aid", max_hp_delta=5),
        ]
    )
    play_state(db, character).current_hp = 2
    db.flush()
    assert hp_view(db, character).maximum == 10

    long_rest(db, character)
    db.flush()

    hp = hp_view(db, character)
    assert hp.effects == []
    assert (hp.current, hp.maximum) == (8, 8)
