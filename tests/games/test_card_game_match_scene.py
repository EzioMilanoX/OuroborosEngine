# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testes isolados de games.card_game.match_scene.MatchScene, sem
CompositionRoot/pygame completo (ver test_card_game_composition_headless.py
para o vertical slice de ponta a ponta). Usa NullInputProvider + um stub
minimo de GameLoop (so precisa de `.stop()`, nunca chamado nestes testes
exceto no de quit) -- MatchScene nunca toca `World` (mesmo idioma de
MenuScene), entao nenhuma fixture de `world` real e necessaria.
"""
from __future__ import annotations

import pytest

from ouroboros.cardgame.cards.schemas import CardDefinition, CardEffect, CardType
from ouroboros.cardgame.effects.resolver import PlayerState
from ouroboros.cardgame.effects.schemas import EffectOp
from ouroboros.cardgame.zones import CardInstance, Zone
from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.interfaces.null.null_input_provider import NullInputProvider

from games.card_game.match_scene import MatchScene, Phase

_UNBOUNDED_MAX = 1.0e9


class _StubGameLoop:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _definition(card_def_id: int, card_id: str, card_type: int, cost: int = 1,
                 base_attack: int = 0, effects=()) -> CardDefinition:
    return CardDefinition(
        card_def_id=card_def_id, card_id=card_id, display_name=card_id,
        cost=cost, card_type=int(card_type), base_attack=base_attack, effects=tuple(effects),
    )


def _player_state(name: str = "p") -> PlayerState:
    return PlayerState(
        name=name, hp=20.0, max_hp=20.0, mana=5, max_mana=5,
        deck=Zone("deck"), hand=Zone("hand"), discard=Zone("discard"), battlefield=Zone("battlefield"),
    )


def _make_scene(definitions, player, opponent, modifier_stack=None):
    input_provider = NullInputProvider()
    game_loop = _StubGameLoop()
    modifier_stack = modifier_stack if modifier_stack is not None else ModifierStack(attribute_capacity=8, entry_capacity=8)
    scene = MatchScene(
        input_provider=input_provider, game_loop=game_loop, definitions=definitions,
        modifier_stack=modifier_stack, player=player, opponent=opponent, viewport_size=(480, 480),
    )
    return scene, input_provider, game_loop, modifier_stack


def test_move_left_and_right_on_an_empty_hand_does_not_raise() -> None:
    definitions = {1: _definition(1, "strike", CardType.ACTION)}
    player, opponent = _player_state(), _player_state("opponent")
    scene, input_provider, _, _ = _make_scene(definitions, player, opponent)
    scene._phase = Phase.MAIN

    input_provider.is_action_pressed = lambda name: name == "move_left"
    scene.update(None, 1.0 / 60.0)  # nao pode levantar ZeroDivisionError com mao vazia
    input_provider.is_action_pressed = lambda name: name == "move_right"
    scene.update(None, 1.0 / 60.0)

    assert scene._hand_cursor == 0


def test_playing_the_last_card_in_hand_leaves_cursor_in_bounds() -> None:
    """O bug que a critica de M14 encontrou: jogar a carta sob o cursor
    quando ele aponta pro ULTIMO indice da mao deixava o cursor "stale"
    (== len(hand) apos a remocao), IndexError na proxima renderizacao/
    jogada."""
    strike = _definition(
        1, "strike", CardType.ACTION, cost=1,
        effects=[CardEffect(op=int(EffectOp.DAMAGE_TARGET), args={"amount": 3})],
    )
    definitions = {1: strike}
    player, opponent = _player_state(), _player_state("opponent")
    player.hand.cards = [CardInstance(instance_id=0, card_def_id=1), CardInstance(instance_id=1, card_def_id=1)]
    scene, input_provider, _, _ = _make_scene(definitions, player, opponent)
    scene._phase = Phase.MAIN
    scene._hand_cursor = 1  # ultimo indice

    input_provider.is_action_pressed = lambda name: name == "play_card"
    scene.update(None, 1.0 / 60.0)

    assert len(player.hand.cards) == 1
    assert scene._hand_cursor == 0  # clampado, nao == len(hand) (1) nem obsoleto


def test_cannot_play_a_card_without_enough_mana() -> None:
    fireball = _definition(
        1, "fireball", CardType.ACTION, cost=99,
        effects=[CardEffect(op=int(EffectOp.DAMAGE_TARGET), args={"amount": 6})],
    )
    definitions = {1: fireball}
    player, opponent = _player_state(), _player_state("opponent")
    player.mana = 2
    player.hand.cards = [CardInstance(instance_id=0, card_def_id=1)]
    scene, input_provider, _, _ = _make_scene(definitions, player, opponent)
    scene._phase = Phase.MAIN

    input_provider.is_action_pressed = lambda name: name == "play_card"
    scene.update(None, 1.0 / 60.0)

    assert len(player.hand.cards) == 1  # carta nao foi jogada
    assert player.mana == 2  # mana nao foi descontada
    assert opponent.hp == pytest.approx(20.0)  # efeito nao resolvido


def test_playing_a_creature_registers_an_attack_attribute_and_moves_to_battlefield() -> None:
    warrior = _definition(1, "warrior", CardType.CREATURE, cost=2, base_attack=3)
    definitions = {1: warrior}
    player, opponent = _player_state(), _player_state("opponent")
    player.hand.cards = [CardInstance(instance_id=0, card_def_id=1)]
    scene, input_provider, _, modifier_stack = _make_scene(definitions, player, opponent)
    scene._phase = Phase.MAIN

    input_provider.is_action_pressed = lambda name: name == "play_card"
    scene.update(None, 1.0 / 60.0)

    assert len(player.hand.cards) == 0
    assert len(player.battlefield.cards) == 1
    creature = player.battlefield.cards[0]
    assert creature.attack_attribute_index is not None
    assert float(modifier_stack.attributes[creature.attack_attribute_index]["final_value"]) == pytest.approx(3.0)


def test_combat_phase_deals_battlefield_attack_to_opponent_and_can_win() -> None:
    warrior = _definition(1, "warrior", CardType.CREATURE, cost=2, base_attack=25)
    definitions = {1: warrior}
    player, opponent = _player_state(), _player_state("opponent")
    opponent.hp = 20.0
    player.hand.cards = [CardInstance(instance_id=0, card_def_id=1)]
    scene, input_provider, _, _ = _make_scene(definitions, player, opponent)
    scene._phase = Phase.MAIN

    input_provider.is_action_pressed = lambda name: name == "play_card"
    scene.update(None, 1.0 / 60.0)
    input_provider.is_action_pressed = lambda name: False
    scene.update(None, 1.0 / 60.0)

    scene._phase = Phase.COMBAT
    scene.update(None, 1.0 / 60.0)

    assert opponent.hp == 0.0
    assert scene._game_over_message == "VOCE VENCEU"


def test_phase_action_and_transition_are_atomic_within_a_single_update_call() -> None:
    """DRAW/COMBAT/END rodam sua acao e transicionam de fase na MESMA
    chamada de update() que primeiro as observa -- nunca ha um frame
    onde uma fase foi "entrada" mas ainda nao processada (o que
    reexecutaria a acao de uma fase duas vezes por ciclo de turno, ver
    achado da critica de M14)."""
    definitions = {1: _definition(1, "strike", CardType.ACTION)}
    player, opponent = _player_state(), _player_state("opponent")
    player.mana = player.max_mana = 0  # estado real de composition.py antes do 1o turno
    player.deck.cards = [CardInstance(0, 1), CardInstance(1, 1)]
    scene, input_provider, _, _ = _make_scene(definitions, player, opponent)
    input_provider.is_action_pressed = lambda name: False

    assert scene._phase == Phase.DRAW
    scene.update(None, 1.0 / 60.0)  # DRAW roda (compra 1) e transiciona pra MAIN, tudo nesta chamada
    assert scene._phase == Phase.MAIN
    assert len(player.hand.cards) == 1
    assert player.mana == 1 and player.max_mana == 1

    scene._phase = Phase.COMBAT
    scene.update(None, 1.0 / 60.0)  # COMBAT roda (campo vazio, sem dano) e transiciona pra END
    assert scene._phase == Phase.END
    assert opponent.hp == pytest.approx(20.0)

    scene.update(None, 1.0 / 60.0)  # END roda (no-op) e transiciona de volta pra DRAW
    assert scene._phase == Phase.DRAW


def test_quit_action_stops_the_game_loop() -> None:
    player, opponent = _player_state(), _player_state("opponent")
    scene, input_provider, game_loop, _ = _make_scene({}, player, opponent)

    input_provider.is_action_pressed = lambda name: name == "quit"
    scene.update(None, 1.0 / 60.0)

    assert game_loop.stopped is True
