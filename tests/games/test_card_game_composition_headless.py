# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testa `games.card_game.composition.build_game` de ponta a ponta com o
`CompositionRoot` real (backends Pygame reais, sob
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy ja forcados em tests/conftest.py) --
confirma que o vertical slice builda corretamente e uma partida completa
(compra, custo/mana, jogar carta, resolver efeito, combate, fim de jogo)
roda sem crashar, mesmo padrao de
tests/games/test_platformer_composition_headless.py/
test_tactics_composition_headless.py.
"""
from __future__ import annotations

import random
from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop

from games.card_game.composition import build_game
from games.card_game.match_scene import MatchScene, Phase

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "card_game" / "config.json"


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig.from_json(str(_CONFIG_PATH))


@pytest.fixture
def game_loop(config: EngineConfig):
    loop = build_game(config, rng=random.Random(1234))
    yield loop
    loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def _press(game_loop: GameLoop, action: str) -> None:
    scene = game_loop.current_scene
    game_loop.input_provider.is_action_pressed = lambda name: name == action
    scene.update(game_loop.world, 1.0 / 60.0)
    game_loop.input_provider.is_action_pressed = lambda name: False
    scene.update(game_loop.world, 1.0 / 60.0)


def test_build_game_starts_on_the_match_scene(game_loop: GameLoop) -> None:
    assert isinstance(game_loop.current_scene, MatchScene)


def test_build_game_draws_an_opening_hand_of_three_cards(game_loop: GameLoop) -> None:
    scene = game_loop.current_scene
    assert scene._phase == Phase.DRAW
    assert len(scene._player.hand.cards) == 3
    assert len(scene._player.deck.cards) == 12  # 15 no total - 3 da mao de abertura


def test_first_update_runs_draw_phase_and_advances_to_main(game_loop: GameLoop) -> None:
    scene = game_loop.current_scene
    scene.update(game_loop.world, 1.0 / 60.0)

    assert scene._phase == Phase.MAIN
    assert len(scene._player.hand.cards) == 4  # 3 de abertura + 1 da fase DRAW
    assert scene._player.mana == 1
    assert scene._player.max_mana == 1


def test_next_phase_action_advances_through_combat_and_end_back_to_draw(game_loop: GameLoop) -> None:
    scene = game_loop.current_scene
    world = game_loop.world
    scene.update(world, 1.0 / 60.0)  # DRAW -> MAIN
    assert scene._phase == Phase.MAIN

    _press(game_loop, "next_phase")  # 1a chamada: MAIN -> COMBAT; 2a: COMBAT roda -> END
    assert scene._game_over_message is None  # campo ainda vazio, sem dano
    assert scene._phase == Phase.END

    scene.update(world, 1.0 / 60.0)  # END roda (no-op) -> DRAW
    assert scene._phase == Phase.DRAW


def test_a_full_match_can_be_won_by_playing_affordable_cards_each_turn(game_loop: GameLoop) -> None:
    """Prova de ponta a ponta: em toda fase principal, joga a primeira
    carta afordavel da mao (nesta ordem: dano > criatura > cura/compra/
    buff/recurso, mas aceita qualquer jogada valida) e avanca de fase;
    repete ate o oponente (HP inicial baixo) perder -- exercita compra,
    custo/mana, resolucao de efeito (incluindo buff_stat via
    ModifierStack de verdade), combate de criaturas em campo, e deteccao
    de fim de jogo, tudo junto."""
    scene = game_loop.current_scene
    world = game_loop.world

    for _ in range(300):
        if scene._game_over_message is not None:
            break
        if scene._phase == Phase.MAIN:
            hand_size_before = len(scene._player.hand.cards)
            played_something = False
            for index in range(len(scene._player.hand.cards)):
                scene._hand_cursor = index
                _press(game_loop, "play_card")
                if len(scene._player.hand.cards) != hand_size_before:
                    played_something = True
                    break
            if not played_something:
                _press(game_loop, "next_phase")
        else:
            scene.update(world, 1.0 / 60.0)

    assert scene._game_over_message == "VOCE VENCEU"
    assert scene._opponent.hp <= 0.0
