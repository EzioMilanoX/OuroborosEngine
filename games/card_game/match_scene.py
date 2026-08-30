# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""MatchScene: ciclo de turno compra->principal->combate->fim de uma unica partida (ROADMAP M14)."""
from __future__ import annotations

from enum import IntEnum
from typing import Dict, Optional, Tuple

import numpy as np

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import IScene
from ouroboros.cardgame.cards.schemas import CardDefinition, CardType
from ouroboros.cardgame.effects.resolver import PlayerState, apply_effect
from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

_TITLE_COLOR = (255, 255, 255, 255)
_HAND_COLOR = (170, 170, 190, 255)
_CURSOR_COLOR = (255, 220, 120, 255)
_UNAFFORDABLE_COLOR = (110, 90, 90, 255)
_HINT_COLOR = (150, 150, 170, 255)
_WIN_COLOR = (120, 240, 150, 255)

_MAX_MANA_CAP = 10

# Limite superior de folga usado como clamp "sem teto pratico" pro atributo
# de ataque de uma criatura -- mesmo idioma de WeaponLoader._UNBOUNDED_MAX.
_UNBOUNDED_MAX = float(np.finfo(np.float32).max)


class Phase(IntEnum):
    DRAW = 0
    MAIN = 1
    COMBAT = 2
    END = 3


class MatchScene(IScene):
    """
    Ciclo continuo de turno de UM UNICO lado real (`player`) contra um
    oponente estatico/sem IA (`opponent`, que nunca joga carta nenhuma --
    ver docstring de `ouroboros.cardgame.effects.resolver.PlayerState`).
    Nao ha "turno do oponente": DRAW->MAIN->COMBAT->END sempre pertencem
    ao `player`, e encadeiam direto de volta pra DRAW.

    Roda SEM nenhum `World`/`ISystem` por baixo (mesmo idioma de
    `MenuScene`, ver `games/rhythm_game/menu_scene.py`) -- `update()`
    nunca chama `world.step()`; o `World` associado ao `GameLoop` neste
    momento e um placeholder generico que nunca e consultado (nenhuma
    entidade ECS existe neste produto -- nem `transform`/`sprite`).

    A ACAO de entrada de uma fase e sua TRANSICAO pra a proxima fase sao
    atomicas dentro da MESMA chamada de `update()` que primeiro observa
    aquela fase -- nunca ha um frame observavel onde uma fase foi
    "entrada" mas ainda nao processada, o que evitaria reexecutar
    `_run_draw_phase`/`_run_combat_phase` duas vezes por um unico ciclo de
    turno (DRAW/COMBAT/END sao automaticas; so MAIN espera input por
    varios frames).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        game_loop: GameLoop,
        definitions: Dict[int, CardDefinition],
        modifier_stack: ModifierStack,
        player: PlayerState,
        opponent: PlayerState,
        viewport_size: Tuple[int, int],
    ) -> None:
        self._input = input_provider
        self._game_loop = game_loop
        self._definitions = definitions
        self._modifier_stack = modifier_stack
        self._player = player
        self._opponent = opponent
        self._viewport_width, self._viewport_height = viewport_size
        self._phase = Phase.DRAW
        self._hand_cursor = 0
        self._game_over_message: Optional[str] = None

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("quit"):
            self._game_loop.stop()
            return
        if self._game_over_message is not None:
            return

        if self._phase == Phase.DRAW:
            self._run_draw_phase()
            self._phase = Phase.MAIN
            return
        if self._phase == Phase.MAIN:
            self._run_main_phase_input()
            return
        if self._phase == Phase.COMBAT:
            self._run_combat_phase()
            if self._game_over_message is not None:
                return
            self._phase = Phase.END
            return
        if self._phase == Phase.END:
            self._run_end_phase()
            self._phase = Phase.DRAW
            return

    def _run_draw_phase(self) -> None:
        self._player.max_mana = min(_MAX_MANA_CAP, self._player.max_mana + 1)
        self._player.mana = self._player.max_mana
        self._player.deck.move_top_to(self._player.hand, count=1)
        self._clamp_hand_cursor()

    def _run_main_phase_input(self) -> None:
        hand = self._player.hand.cards
        if hand:
            if self._input.is_action_pressed("move_left"):
                self._hand_cursor = (self._hand_cursor - 1) % len(hand)
            if self._input.is_action_pressed("move_right"):
                self._hand_cursor = (self._hand_cursor + 1) % len(hand)
            if self._input.is_action_pressed("play_card"):
                self._try_play_card_under_cursor()
        if self._input.is_action_pressed("next_phase"):
            self._phase = Phase.COMBAT

    def _try_play_card_under_cursor(self) -> None:
        hand = self._player.hand.cards
        if not hand:
            return
        instance = hand[self._hand_cursor]
        definition = self._definitions[instance.card_def_id]
        if definition.cost > self._player.mana:
            return
        self._player.mana -= definition.cost

        if definition.card_type == CardType.CREATURE:
            instance.attack_attribute_index = self._modifier_stack.register_attribute(
                base_value=float(definition.base_attack), min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
            )
            self._player.hand.move_specific_to(instance, self._player.battlefield)
        else:
            for effect in definition.effects:
                apply_effect(effect, self._player, self._opponent, self._modifier_stack)
            self._modifier_stack.recompute_all()
            self._player.hand.move_specific_to(instance, self._player.discard)
            self._check_win_condition()

        self._clamp_hand_cursor()

    def _run_combat_phase(self) -> None:
        for creature in self._player.battlefield.cards:
            if creature.attack_attribute_index is not None:
                attack_value = float(self._modifier_stack.attributes[creature.attack_attribute_index]["final_value"])
                self._opponent.hp = max(0.0, self._opponent.hp - attack_value)
        self._check_win_condition()

    def _run_end_phase(self) -> None:
        pass  # nenhum efeito de fim de turno no v1 (ver ROADMAP M14, fora de escopo)

    def _check_win_condition(self) -> None:
        if self._opponent.hp <= 0.0:
            self._game_over_message = "VOCE VENCEU"

    def _clamp_hand_cursor(self) -> None:
        hand_size = len(self._player.hand.cards)
        self._hand_cursor = 0 if hand_size == 0 else min(self._hand_cursor, hand_size - 1)

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        renderer.draw_text(
            20.0, 20.0,
            f"Voce: HP {self._player.hp:.0f}  Mana {self._player.mana}/{self._player.max_mana}",
            20, _TITLE_COLOR,
        )
        renderer.draw_text(20.0, 48.0, f"Oponente: HP {self._opponent.hp:.0f}", 20, _TITLE_COLOR)
        renderer.draw_text(20.0, 76.0, f"Fase: {self._phase.name}", 16, _HINT_COLOR)

        battlefield = self._player.battlefield.cards
        battlefield_y = 112.0
        renderer.draw_text(20.0, battlefield_y, "Campo:", 16, _HINT_COLOR)
        for index, creature in enumerate(battlefield):
            definition = self._definitions[creature.card_def_id]
            attack_value = float(self._modifier_stack.attributes[creature.attack_attribute_index]["final_value"])
            renderer.draw_text(
                20.0, battlefield_y + 22.0 * (index + 1),
                f"  {definition.display_name} (ATQ {attack_value:.0f})",
                14, _HAND_COLOR,
            )

        hand_y = battlefield_y + 22.0 * (len(battlefield) + 2)
        renderer.draw_text(20.0, hand_y, "Mao:", 16, _HINT_COLOR)
        for index, instance in enumerate(self._player.hand.cards):
            definition = self._definitions[instance.card_def_id]
            is_cursor_row = index == self._hand_cursor
            affordable = definition.cost <= self._player.mana
            color = _CURSOR_COLOR if is_cursor_row else (_HAND_COLOR if affordable else _UNAFFORDABLE_COLOR)
            label = f"{'> ' if is_cursor_row else '  '}{definition.display_name} (custo {definition.cost})"
            renderer.draw_text(20.0, hand_y + 22.0 * (index + 1), label, 14, color)

        renderer.draw_text(
            20.0, self._viewport_height - 30.0,
            "Setas: navega mao | ESPACO: joga carta | ENTER: avanca fase | ESC: sai",
            13, _HINT_COLOR,
        )

        if self._game_over_message is not None:
            renderer.draw_text(
                self._viewport_width / 2.0, self._viewport_height / 2.0,
                self._game_over_message, 32, _WIN_COLOR, anchor="center",
            )
