# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Decrementa o ttl de efeitos visuais transientes (pool `fx`) e destroi os expirados."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ouroboros.core.systems.base_system import ISystem

if TYPE_CHECKING:
    from ouroboros.core.world import World


class FxTtlSystem(ISystem):
    """
    Decrementa `ttl_seconds` de toda entidade da pool `fx` (ROADMAP
    M1.3) por `delta_time` REAL a cada frame (fx e presentation-only,
    nunca sincronizado a audio -- ao contrario dos Systems do Pilar 4)
    e destroi (via `World.destroy_entity`, diferido ate `flush()`)
    qualquer entidade cujo `ttl_seconds` cruze `<= 0`.

    Registrado pelo script de composicao de um produto (nao pelo
    `CompositionRoot` -- a pool `fx` e generica/automatica, mas o
    arquetipo `"fx"` e este sistema sao opt-in, mesmo padrao de
    `RhythmSpawnerSystem`/`NoteScrollSystem`/`JudgmentSystem` do Pilar
    4): resolve o nome da pool (nunca uma referencia de `MemoryManager`,
    que um script de composicao so tem ANTES de `CompositionRoot.build()`
    devolver o `GameLoop`) fresh a cada `update()`, mesmo idioma dessas
    classes.

    Reconstroi o `PackedEntityId` de cada entidade expirada via
    `World.pack_current(entity_index)` (ROADMAP M5.2) em vez de exigir
    uma coluna `packed_entity_id` dedicada na propria pool `fx`.
    """

    def __init__(self, fx_pool_name: str = "fx") -> None:
        self._fx_pool_name = fx_pool_name

    def update(self, world: "World", delta_time: float) -> None:
        """Decrementa `ttl_seconds` em massa (vetorizado) e destroi as entidades expiradas."""
        fx_pool = world.get_pool(self._fx_pool_name)
        count = fx_pool.count
        if count == 0:
            return

        view = fx_pool.active_view()
        view["ttl_seconds"] -= delta_time
        expired_mask = view["ttl_seconds"] <= 0.0
        if not expired_mask.any():
            return

        entity_indices = fx_pool.active_entity_indices()
        for entity_index in entity_indices[expired_mask]:
            world.destroy_entity(world.pack_current(int(entity_index)))
