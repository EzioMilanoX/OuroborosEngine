# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sistema minimo especifico deste jogo: pulo, so permitido enquanto TileCollisionSystem reporta grounded."""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider


class PlayerJumpSystem(ISystem):
    """
    Ao apertar `jump` (borda -- uma vez por pressao) COM o jogador
    `TileCollisionSystem.is_grounded()`, define `velocity.linear_y` pra um
    valor negativo (impulso pra cima, ja que +y = baixo nesta engine --
    ver `GravitySystem`) de uma vez. Sem checar `is_grounded()`, o jogador
    poderia pular infinitamente no ar (fora de escopo do M12 permitir).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        tile_collision_system: TileCollisionSystem,
        jump_velocity_y: float,
        player_entity_index: int,
        velocity_pool_name: str = "velocity",
    ) -> None:
        self._input_provider = input_provider
        self._tile_collision_system = tile_collision_system
        self._jump_velocity_y = jump_velocity_y
        self._player_entity_index = player_entity_index
        self._velocity_pool_name = velocity_pool_name

    def update(self, world: World, delta_time: float) -> None:
        del delta_time
        if not self._input_provider.is_action_pressed("jump"):
            return
        if not self._tile_collision_system.is_grounded(self._player_entity_index):
            return

        velocity_pool = world.get_pool(self._velocity_pool_name)
        row = velocity_pool.dense_row_of(self._player_entity_index)
        velocity_pool.active_view()["linear_y"][row] = self._jump_velocity_y
