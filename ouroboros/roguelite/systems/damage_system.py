# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Aplica dano simetrico a partir de CollisionSystem.get_collision_pairs() e resolve mortes (ROADMAP M6)."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.systems.collision_system import CollisionSystem
from ouroboros.roguelite.combat.schemas import EntityKind

if TYPE_CHECKING:
    from ouroboros.core.world import World


class DamageOnCollisionSystem(ISystem):
    """
    Consome `collision_system.get_collision_pairs()` (view crua de
    indices globais de entidade, valida pelo resto do frame -- ver
    docstring de `CollisionSystem`) e aplica dano SIMETRICO: se `b` tem
    `contact_damage > 0`, subtrai de `current_hp` de `a`, e vice-versa.
    Destroi (via `world.destroy_entity(world.pack_current(index))`)
    qualquer lado com `current_hp <= 0` OU `destroy_on_hit`.

    Numero de pares numa vertical slice e pequeno (poucos inimigos/
    projeteis) -- laco Python sobre `get_collision_pairs()` e aceitavel,
    mesmo padrao ja aceito de `JudgmentSystem._auto_miss_expired`
    (Pilar 4). Destruir o mesmo indice duas vezes no mesmo frame (ex.:
    um projetil atinge dois inimigos nos pares deste frame) e seguro
    sem guarda extra -- `World.destroy_entity` e no-op num handle ja
    obsoleto.

    `player_is_dead` fica travado (`True` PERMANENTEMENTE) no momento
    exato em que o `player_entity_index` e destruido -- NUNCA
    recalculado depois via re-checagem de `is_attached` (esse indice
    pode ser reciclado por uma entidade completamente diferente em
    qualquer frame seguinte; ver docstring de `EntityKind`).
    `enemies_remaining` e recalculado do zero a cada `update()` varrendo
    a pool inteira por `entity_kind == ENEMY` -- fonte de verdade a
    partir do dado atual, nunca um contador que possa dessincronizar.
    """

    def __init__(self, collision_system: CollisionSystem, health_pool_name: str, player_entity_index: int) -> None:
        self._collision_system = collision_system
        self._health_pool_name = health_pool_name
        self._player_entity_index = player_entity_index
        self._player_is_dead = False
        self._enemies_remaining = 0

    @property
    def player_is_dead(self) -> bool:
        return self._player_is_dead

    @property
    def enemies_remaining(self) -> int:
        return self._enemies_remaining

    def update(self, world: "World", delta_time: float) -> None:
        del delta_time
        health_pool = world.get_pool(self._health_pool_name)
        pairs = self._collision_system.get_collision_pairs()

        if pairs.shape[0] > 0:
            view = health_pool.active_view()
            for i in range(pairs.shape[0]):
                a_index = int(pairs[i, 0])
                b_index = int(pairs[i, 1])
                if not (health_pool.is_attached(a_index) and health_pool.is_attached(b_index)):
                    continue
                a_row = health_pool.dense_row_of(a_index)
                b_row = health_pool.dense_row_of(b_index)
                a_damage = float(view["contact_damage"][a_row])
                b_damage = float(view["contact_damage"][b_row])
                if b_damage > 0.0:
                    view["current_hp"][a_row] -= b_damage
                if a_damage > 0.0:
                    view["current_hp"][b_row] -= a_damage

                self._destroy_if_needed(world, health_pool, a_index)
                self._destroy_if_needed(world, health_pool, b_index)

        current_view = health_pool.active_view()
        self._enemies_remaining = int(np.count_nonzero(current_view["entity_kind"] == EntityKind.ENEMY))

    def _destroy_if_needed(self, world: "World", health_pool, index: int) -> None:
        if not health_pool.is_attached(index):
            return
        row = health_pool.dense_row_of(index)
        view = health_pool.active_view()
        should_destroy = bool(view["current_hp"][row] <= 0.0) or bool(view["destroy_on_hit"][row])
        if not should_destroy:
            return
        if index == self._player_entity_index:
            self._player_is_dead = True
        world.destroy_entity(world.pack_current(index))
