# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Aplica uma aceleracao constante a toda entidade com Velocity (ROADMAP M12)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.base_system import ISystem

if TYPE_CHECKING:
    from ouroboros.core.world import World


class GravitySystem(ISystem):
    """
    Soma `gravity_y * delta_time` em `velocity.linear_y` de TODA entidade
    com a pool `velocity` anexada -- generico o bastante pra qualquer genero
    futuro com queda (nao especifico de Platformer), mas puramente opt-in:
    Roguelite/Jogo Musical nunca o registram.

    Aplica cegamente ao pool inteiro (sem filtrar por `transform`/`hitbox`
    como `PhysicsSystem`/`TileCollisionSystem` fazem) -- correto enquanto
    TODA entidade com `velocity` neste `World` deve mesmo cair (o caso do
    vertical slice do M12, so o jogador). Um produto que precise de ALGUMAS
    entidades imunes a gravidade (ex.: um projetil reto) precisaria de uma
    pool `velocity` separada ou de um filtro por camada -- fora de escopo
    do M12.

    **Ordem de registro obrigatoria** (ver `TileCollisionSystem`): depois
    de `TileCollisionSystem` no mesmo `World`. `TileCollisionSystem`
    reconstroi a posicao pre-movimento como `position - velocity*delta_time`
    assumindo que SO `PhysicsSystem` mexeu em `velocity` neste frame --
    `GravitySystem` rodando antes corromperia essa reconstrucao.
    """

    def __init__(self, memory_manager: MemoryManager, gravity_y: float, velocity_pool_name: str = "velocity") -> None:
        self._velocity_pool = memory_manager.get_pool(velocity_pool_name)
        self._gravity_y = gravity_y

    def update(self, world: "World", delta_time: float) -> None:
        del world
        view = self._velocity_pool.active_view()
        view["linear_y"] += self._gravity_y * delta_time
