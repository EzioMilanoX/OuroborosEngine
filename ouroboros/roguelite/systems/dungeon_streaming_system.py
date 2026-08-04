# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Materializa/desmaterializa entidades de sala conforme a proximidade de uma entidade-ancora."""
from __future__ import annotations

import numpy as np

from ouroboros.core.constants import INVALID_DENSE_ROW
from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.core.memory.handles import PackedEntityId, unpack_index
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.roguelite.generation.dungeon_generator import DungeonLayout

ROOM_INSTANCE_DTYPE: np.dtype = np.dtype([("world_entity_id", np.int64)])
"""Schema de UMA linha por sala potencialmente instanciada.

Usado como dtype de uma `ComponentPool` cujo `entity_index` e
reaproveitado como o ORDINAL PERMANENTE da sala em
`DungeonLayout.rooms` (`room_id`, 0..room_count-1) -- nunca um indice
de entidade do `MemoryManager`. Essa reutilizacao evita reinventar um
array de sentinelas do zero: `is_attached(room_id)` ja responde
diretamente "esta sala tem uma entidade instanciada agora?",
`attach(room_id)` reserva a linha onde o `PackedEntityId` da sala
recem-criada e guardado, e `detach(room_id)` libera essa linha quando a
sala e destruida -- sem exigir nenhum valor sentinela artificial (o
proprio `is_attached` e a fonte de verdade, eliminando o risco de um
sentinela colidir com um `PackedEntityId` valido).
"""


class DungeonStreamingSystem(ISystem):
    """Materializa/desmaterializa entidades de sala conforme a proximidade
    de uma entidade-ancora (tipicamente o jogador).

    Usa exclusivamente `PackedEntityId` (inteiro de 64 bits) para
    rastrear quais salas estao materializadas -- NUNCA desempacota para
    `EntityHandle` dentro de `update()` (reservado a testes/
    telemetria fora do hot-path). A posicao da ancora e resolvida a cada
    frame via `unpack_index(self._anchor_entity)` seguido de
    `ComponentPool.dense_row_of()` na pool de transform -- a linha
    densa NUNCA e cacheada entre frames (poderia ser invalidada por um
    `detach` alheio na mesma pool), e sim sempre re-consultada sob
    demanda.

    Usa histerese (`activation_radius` < `deactivation_radius`) para
    evitar instanciar/destruir a mesma sala repetidamente quando a ancora
    oscila perto da fronteira de um unico raio.
    """

    def __init__(
        self,
        layout: DungeonLayout,
        room_archetype_name: str,
        activation_radius: float,
        deactivation_radius: float,
        transform_pool_name: str,
        anchor_entity: PackedEntityId,
    ) -> None:
        """Cria internamente a `ComponentPool(ROOM_INSTANCE_DTYPE,
        dense_capacity=len(layout.rooms), entity_capacity=len(layout.rooms))`
        descrita acima e guarda os demais parametros de streaming.

        `deactivation_radius` deve ser maior que `activation_radius`
        (histerese); o construtor nao valida isso em runtime (esqueleto),
        mas a violacao deve ser tratada como erro de configuracao pelo
        chamador.
        """
        self._layout = layout
        self._room_archetype_name = room_archetype_name
        self._activation_radius = float(activation_radius)
        self._deactivation_radius = float(deactivation_radius)
        self._transform_pool_name = transform_pool_name
        self._anchor_entity = anchor_entity

        room_count = int(layout.rooms.shape[0])
        self._room_instances = ComponentPool(
            dtype=ROOM_INSTANCE_DTYPE, dense_capacity=room_count, entity_capacity=room_count
        )
        # Precomputado uma unica vez (nao por frame): usado para consultar
        # `dense_rows_of` vetorizadamente em `_rooms_to_activate`/`_rooms_to_deactivate`.
        self._room_ids = np.arange(room_count, dtype=np.int64)

    def update(self, world: World, delta_time: float) -> None:
        """A cada frame: resolve a posicao da ancora, calcula (vetorizado)
        a distancia de cada sala a ancora, decide quais salas devem
        entrar/sair de streaming, e para cada TRANSICAO de estado chama
        `world.create_entity` (imediato, grava o `PackedEntityId`
        resultante via `self._room_instances.attach(room_id)`) ou
        `world.destroy_entity` (diferido ate `flush`, seguido de
        `self._room_instances.detach(room_id)`).

        O calculo de QUAIS salas transicionam e inteiramente vetorizado;
        o loop Python remanescente e limitado ao pequeno subconjunto de
        salas que cruzam a fronteira de raio neste frame, e so encaminha
        chamadas a API do Pilar 1 -- nenhum objeto Python adicional e
        instanciado alem dos inteiros (`PackedEntityId`) que essa API
        ja retorna.
        """
        del delta_time  # Streaming depende apenas da posicao atual da ancora.

        anchor_index = unpack_index(self._anchor_entity)
        transform_pool = world.get_pool(self._transform_pool_name)
        dense_row = transform_pool.dense_row_of(anchor_index)
        anchor_row = transform_pool.active_view()[dense_row]
        anchor_position_xy = np.array(
            (anchor_row["position_x"], anchor_row["position_y"]), dtype=np.float64
        )

        activate_mask = self._rooms_to_activate(anchor_position_xy)
        deactivate_mask = self._rooms_to_deactivate(anchor_position_xy)

        for room_id in np.flatnonzero(activate_mask):
            room_id_int = int(room_id)
            packed_entity_id = world.create_entity(self._room_archetype_name)
            row = self._room_instances.attach(room_id_int)
            self._room_instances.active_view()[row] = (packed_entity_id,)

        for room_id in np.flatnonzero(deactivate_mask):
            room_id_int = int(room_id)
            row = self._room_instances.dense_row_of(room_id_int)
            packed_entity_id = int(self._room_instances.active_view()[row]["world_entity_id"])
            world.destroy_entity(packed_entity_id)
            self._room_instances.detach(room_id_int)

    def _rooms_to_activate(self, anchor_position_xy: np.ndarray) -> np.ndarray:
        """Mascara booleana vetorizada: salas dentro de `activation_radius`
        e ainda NAO instanciadas (`is_attached(room_id)` falso).
        """
        dx = self._layout.rooms["center_x"].astype(np.float64) - anchor_position_xy[0]
        dy = self._layout.rooms["center_y"].astype(np.float64) - anchor_position_xy[1]
        within_radius = (dx * dx + dy * dy) <= (self._activation_radius ** 2)
        dense_rows = self._room_instances.dense_rows_of(self._room_ids)
        not_instantiated = dense_rows == INVALID_DENSE_ROW
        return within_radius & not_instantiated

    def _rooms_to_deactivate(self, anchor_position_xy: np.ndarray) -> np.ndarray:
        """Mascara booleana vetorizada: salas fora de `deactivation_radius`
        e atualmente instanciadas (`is_attached(room_id)` verdadeiro).
        """
        dx = self._layout.rooms["center_x"].astype(np.float64) - anchor_position_xy[0]
        dy = self._layout.rooms["center_y"].astype(np.float64) - anchor_position_xy[1]
        beyond_radius = (dx * dx + dy * dy) > (self._deactivation_radius ** 2)
        dense_rows = self._room_instances.dense_rows_of(self._room_ids)
        instantiated = dense_rows != INVALID_DENSE_ROW
        return beyond_radius & instantiated
