# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Move o jogador via 4 acoes discretas (WASD) -- get_axis nao e funcional no backend Pygame real."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ouroboros.core.systems.base_system import ISystem
from ouroboros.interfaces.input_provider import IInputProvider

if TYPE_CHECKING:
    from ouroboros.core.world import World


class PlayerMovementSystem(ISystem):
    """
    Move o jogador escrevendo `velocity` a partir de 4 acoes discretas
    seguradas (`is_action_held`) -- `IInputProvider.get_axis` existe no
    contrato mas nunca e escrito por `PygameInputProvider` (sempre
    retorna `0.0` no backend real), entao um eixo continuo nao esta
    disponivel; 4 acoes discretas + normalizacao manual e o caminho
    real hoje.

    Grava a ultima direcao NAO-NULA em `facing_pool_name` (persiste
    enquanto o jogador fica parado) -- `WeaponFireSystem` le essa pool
    pra saber pra onde atirar, sem nenhuma referencia direta a este
    sistema (mesmo idioma de `NoteScrollSystem`/`JudgmentSystem`
    comunicando-se via a pool `note_state`).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        velocity_pool_name: str,
        facing_pool_name: str,
        player_entity_index: int,
        move_speed: float,
    ) -> None:
        self._input_provider = input_provider
        self._velocity_pool_name = velocity_pool_name
        self._facing_pool_name = facing_pool_name
        self._player_entity_index = player_entity_index
        self._move_speed = float(move_speed)

    def update(self, world: "World", delta_time: float) -> None:
        del delta_time
        velocity_pool = world.get_pool(self._velocity_pool_name)
        if not velocity_pool.is_attached(self._player_entity_index):
            return  # jogador morto -- nada a mover

        direction_x = 0.0
        direction_y = 0.0
        if self._input_provider.is_action_held("move_right"):
            direction_x += 1.0
        if self._input_provider.is_action_held("move_left"):
            direction_x -= 1.0
        if self._input_provider.is_action_held("move_down"):
            direction_y += 1.0
        if self._input_provider.is_action_held("move_up"):
            direction_y -= 1.0

        magnitude = math.sqrt(direction_x * direction_x + direction_y * direction_y)
        v_row = velocity_pool.dense_row_of(self._player_entity_index)
        v_view = velocity_pool.active_view()
        if magnitude > 0.0:
            direction_x /= magnitude
            direction_y /= magnitude
            v_view["linear_x"][v_row] = direction_x * self._move_speed
            v_view["linear_y"][v_row] = direction_y * self._move_speed

            facing_pool = world.get_pool(self._facing_pool_name)
            f_row = facing_pool.dense_row_of(self._player_entity_index)
            f_view = facing_pool.active_view()
            f_view["facing_x"][f_row] = direction_x
            f_view["facing_y"][f_row] = direction_y
        else:
            v_view["linear_x"][v_row] = 0.0
            v_view["linear_y"][v_row] = 0.0
