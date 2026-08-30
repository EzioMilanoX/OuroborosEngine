# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sistema minimo especifico deste jogo: move o jogador na horizontal enquanto move_left/move_right estiver segurado."""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider


class PlayerRunSystem(ISystem):
    """
    Define `velocity.linear_x` do jogador a partir de `move_left`/
    `move_right` SEGURADOS (nao pressionados -- corrida continua enquanto a
    tecla fica apertada, ao contrario de um pulo que dispara uma vez).
    Segurar os dois ao mesmo tempo para (nenhuma prioridade arbitraria).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        move_speed: float,
        player_entity_index: int,
        velocity_pool_name: str = "velocity",
    ) -> None:
        self._input_provider = input_provider
        self._move_speed = move_speed
        self._player_entity_index = player_entity_index
        self._velocity_pool_name = velocity_pool_name

    def update(self, world: World, delta_time: float) -> None:
        del delta_time
        velocity_pool = world.get_pool(self._velocity_pool_name)
        row = velocity_pool.dense_row_of(self._player_entity_index)
        view = velocity_pool.active_view()

        moving_left = self._input_provider.is_action_held("move_left")
        moving_right = self._input_provider.is_action_held("move_right")
        if moving_left and not moving_right:
            view["linear_x"][row] = -self._move_speed
        elif moving_right and not moving_left:
            view["linear_x"][row] = self._move_speed
        else:
            view["linear_x"][row] = 0.0
