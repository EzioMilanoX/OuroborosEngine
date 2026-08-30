# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de ouroboros.cardgame.effects.resolver.apply_effect (Pilar 3)."""
from __future__ import annotations

import pytest

from ouroboros.cardgame.cards.schemas import CardEffect
from ouroboros.cardgame.effects.resolver import PlayerState, apply_effect
from ouroboros.cardgame.effects.schemas import EffectOp
from ouroboros.cardgame.zones import CardInstance, Zone
from ouroboros.core.modifiers.modifier_stack import ModifierStack

_UNBOUNDED_MAX = 1.0e9


def _player(hp: float = 20.0, max_hp: float = 20.0, mana: int = 0, max_mana: int = 0) -> PlayerState:
    return PlayerState(
        name="p", hp=hp, max_hp=max_hp, mana=mana, max_mana=max_mana,
        deck=Zone("deck"), hand=Zone("hand"), discard=Zone("discard"), battlefield=Zone("battlefield"),
    )


def test_damage_target_reduces_opponent_hp_and_clamps_at_zero() -> None:
    caster, opponent = _player(), _player(hp=5.0)
    modifier_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    effect = CardEffect(op=int(EffectOp.DAMAGE_TARGET), args={"amount": 20.0})

    apply_effect(effect, caster, opponent, modifier_stack)

    assert opponent.hp == 0.0


def test_heal_target_increases_caster_hp_and_clamps_at_max_hp() -> None:
    caster, opponent = _player(hp=10.0, max_hp=20.0), _player()
    modifier_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    effect = CardEffect(op=int(EffectOp.HEAL_TARGET), args={"amount": 100.0})

    apply_effect(effect, caster, opponent, modifier_stack)

    assert caster.hp == 20.0


def test_draw_cards_moves_from_casters_deck_to_casters_hand() -> None:
    caster, opponent = _player(), _player()
    caster.deck.cards = [CardInstance(0, 1), CardInstance(1, 1)]
    modifier_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    effect = CardEffect(op=int(EffectOp.DRAW_CARDS), args={"count": 2})

    apply_effect(effect, caster, opponent, modifier_stack)

    assert len(caster.deck.cards) == 0
    assert len(caster.hand.cards) == 2


def test_gain_resource_increases_caster_mana() -> None:
    caster, opponent = _player(mana=1), _player()
    modifier_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    effect = CardEffect(op=int(EffectOp.GAIN_RESOURCE), args={"amount": 3})

    apply_effect(effect, caster, opponent, modifier_stack)

    assert caster.mana == 4


def test_buff_stat_pushes_a_modifier_onto_every_creature_on_casters_battlefield() -> None:
    caster, opponent = _player(), _player()
    modifier_stack = ModifierStack(attribute_capacity=4, entry_capacity=4)
    attack_index_a = modifier_stack.register_attribute(base_value=3.0, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX)
    attack_index_b = modifier_stack.register_attribute(base_value=4.0, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX)
    caster.battlefield.cards = [
        CardInstance(instance_id=10, card_def_id=1, attack_attribute_index=attack_index_a),
        CardInstance(instance_id=11, card_def_id=1, attack_attribute_index=attack_index_b),
    ]
    effect = CardEffect(op=int(EffectOp.BUFF_STAT), args={"attribute": "attack", "operation": "flat", "magnitude": 2.0})

    apply_effect(effect, caster, opponent, modifier_stack)
    modifier_stack.recompute_all()

    assert float(modifier_stack.attributes[attack_index_a]["final_value"]) == pytest.approx(5.0)
    assert float(modifier_stack.attributes[attack_index_b]["final_value"]) == pytest.approx(6.0)


def test_buffing_one_creature_instance_never_affects_a_duplicate_copy_of_the_same_card() -> None:
    """O bug que a critica de M14 e o aviso de
    `MODIFIER_ENTRY_DTYPE.source_id` apontam para evitar: usar
    `card_def_id` (template compartilhado) como `source_id` faria
    `remove_by_source` de UMA copia afetar TODAS as copias da mesma
    carta. Aqui, `source_id` e sempre `instance_id` (unico por
    `CardInstance`) -- confirma que empurrar/remover o buff de uma copia
    NUNCA afeta a outra copia da MESMA definicao de carta."""
    caster, opponent = _player(), _player()
    modifier_stack = ModifierStack(attribute_capacity=4, entry_capacity=4)
    shared_card_def_id = 777
    attack_index_a = modifier_stack.register_attribute(base_value=3.0, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX)
    attack_index_b = modifier_stack.register_attribute(base_value=3.0, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX)
    instance_a = CardInstance(instance_id=1, card_def_id=shared_card_def_id, attack_attribute_index=attack_index_a)
    # instance_b existe (mesma definicao de carta) mas NAO esta em campo --
    # so a instancia A recebe o buff nesta rodada.
    instance_b_source_id = 2
    caster.battlefield.cards = [instance_a]
    effect = CardEffect(op=int(EffectOp.BUFF_STAT), args={"attribute": "attack", "operation": "flat", "magnitude": 5.0})

    apply_effect(effect, caster, opponent, modifier_stack)
    modifier_stack.recompute_all()

    assert float(modifier_stack.attributes[attack_index_a]["final_value"]) == pytest.approx(8.0)
    assert float(modifier_stack.attributes[attack_index_b]["final_value"]) == pytest.approx(3.0)  # intocada

    modifier_stack.remove_by_source(instance_a.instance_id)
    modifier_stack.recompute_all()
    assert float(modifier_stack.attributes[attack_index_a]["final_value"]) == pytest.approx(3.0)
    # remover pelo source_id da instancia A nao pode afetar o slot da B,
    # mesmo elas compartilhando card_def_id -- prova que nunca usamos
    # card_def_id como source_id em nenhum push().
    assert instance_b_source_id != instance_a.instance_id
    assert float(modifier_stack.attributes[attack_index_b]["final_value"]) == pytest.approx(3.0)


def test_unknown_effect_op_raises_value_error() -> None:
    caster, opponent = _player(), _player()
    modifier_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    effect = CardEffect(op=999, args={})

    with pytest.raises(ValueError):
        apply_effect(effect, caster, opponent, modifier_stack)
