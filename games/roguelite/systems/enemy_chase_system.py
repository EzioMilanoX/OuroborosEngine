# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Faz todo inimigo perseguir o jogador -- vetorizado, sem lista Python de indices mantida a parte."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ouroboros.core.systems.base_system import ISystem
from ouroboros.roguelite.combat.schemas import EntityKind

if TYPE_CHECKING:
    from ouroboros.core.world import World

_MIN_DISTANCE = 1e-6  # evita divisao por zero quando um inimigo ja esta exatamente sobre o jogador


class EnemyChaseSystem(ISystem):
    """
    A cada `update()`, deriva os indices de inimigo ATUALMENTE vivos
    direto da pool de HP (`entity_kind == ENEMY`, via
    `active_entity_indices()`) -- NUNCA de uma lista Python mantida a
    parte. Isso elimina por construcao o risco de um indice reciclado
    (ex.: um projetil nascendo no mesmo `entity_index` de um inimigo
    morto no frame anterior) ser tratado como "ainda inimigo": o
    discriminador `entity_kind` e sempre consultado no dado ATUAL, e
    `world.create_entity` sempre grava um `entity_kind` novo e correto
    pra quem quer que ocupe aquele indice agora (ver docstring de
    `EntityKind`).

    Calcula direcao-ate-o-jogador e escreve velocidade, tudo VETORIZADO
    sobre os indices de inimigo resolvidos neste mesmo `update()` --
    nao um laco Python por inimigo.
    """

    def __init__(
        self,
        health_pool_name: str,
        transform_pool_name: str,
        velocity_pool_name: str,
        player_entity_index: int,
        chase_speed: float,
    ) -> None:
        self._health_pool_name = health_pool_name
        self._transform_pool_name = transform_pool_name
        self._velocity_pool_name = velocity_pool_name
        self._player_entity_index = player_entity_index
        self._chase_speed = float(chase_speed)

    def update(self, world: "World", delta_time: float) -> None:
        del delta_time
        transform_pool = world.get_pool(self._transform_pool_name)
        if not transform_pool.is_attached(self._player_entity_index):
            return  # jogador morto -- inimigos param (nada de perseguicao sem alvo)

        health_pool = world.get_pool(self._health_pool_name)
        health_view = health_pool.active_view()
        enemy_mask = health_view["entity_kind"] == EntityKind.ENEMY
        if not enemy_mask.any():
            return
        enemy_entity_indices = health_pool.active_entity_indices()[enemy_mask]

        player_row = transform_pool.dense_row_of(self._player_entity_index)
        player_view = transform_pool.active_view()
        player_x = float(player_view["position_x"][player_row])
        player_y = float(player_view["position_y"][player_row])

        velocity_pool = world.get_pool(self._velocity_pool_name)
        t_rows = transform_pool.dense_rows_of(enemy_entity_indices)
        v_rows = velocity_pool.dense_rows_of(enemy_entity_indices)
        t_view = transform_pool.active_view()
        v_view = velocity_pool.active_view()

        dx = player_x - t_view["position_x"][t_rows]
        dy = player_y - t_view["position_y"][t_rows]
        distance = np.sqrt(dx * dx + dy * dy)
        distance[distance < _MIN_DISTANCE] = _MIN_DISTANCE
        v_view["linear_x"][v_rows] = (dx / distance) * self._chase_speed
        v_view["linear_y"][v_rows] = (dy / distance) * self._chase_speed
