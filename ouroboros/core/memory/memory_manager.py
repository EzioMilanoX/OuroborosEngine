# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Autoridade unica sobre indices/geracoes de entidade e registro de ComponentPool."""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from ouroboros.core.constants import DEFAULT_ENTITY_CAPACITY
from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.core.memory.handles import (
    EntityHandle,
    PackedEntityId,
    unpack_batch,
    unpack_generation,
    unpack_index,
)


class MemoryManager:
    """
    Autoridade UNICA sobre o espaco de indices/geracoes de entidade e
    sobre o registro de `ComponentPool` genericas e reutilizaveis
    (Transform, Velocity, Hitbox, SpriteData, etc. -- nunca uma pool
    especifica de gameplay como um hipotetico "BulletPool").

    Invariantes:
        - `entity_capacity` e fixo desde a construcao.
        - `_entity_generations` (uint32) e `_entity_free_slots` (pilha
          de indices livres) sao `np.ndarray` pre-alocados de tamanho
          `entity_capacity` -- nunca uma `list` Python com
          append/pop dinamico.
        - `create_pool` so pode ser chamado durante a fase de
          composicao do jogo (antes do primeiro `World.step`); o
          conjunto de pools e suas capacidades sao imutaveis durante o
          gameplay.
        - E este objeto -- e SOMENTE ele -- quem emite indices de
          entidade novos, via `acquire_entity`. Nenhuma `ComponentPool`
          gera seu proprio indice.
        - Zero-GC estrito do handle: `acquire_entity`, `release_entity`
          e `is_alive` (e variantes `_raw`/`_batch`) trafegam
          exclusivamente `PackedEntityId` (int primitivo) ou pares
          `(index, generation)` primitivos -- NUNCA `EntityHandle`.
          Isso e o que torna seguro chama-los de dentro de
          `ISystem.update()`.
    """

    def __init__(self, entity_capacity: int = DEFAULT_ENTITY_CAPACITY) -> None:
        """
        Pre-aloca `_entity_generations`, `_entity_free_slots` (pilha
        cheia com `0..entity_capacity-1` no topo) e inicializa o
        registro vazio de pools. Nao cria nenhuma `ComponentPool` --
        isso e feito via `create_pool` durante a composicao.
        """
        self._entity_capacity = entity_capacity
        self._entity_generations = np.zeros(entity_capacity, dtype=np.uint32)
        self._free_slots = np.arange(entity_capacity, dtype=np.int64)
        self._free_count = entity_capacity
        self._pools: Dict[str, ComponentPool] = {}

    def create_pool(
        self,
        name: str,
        dtype: np.dtype,
        dense_capacity: Optional[int] = None,
    ) -> ComponentPool:
        """
        Cria e registra uma nova `ComponentPool` sob `name`, com
        `dense_capacity` (ou `entity_capacity`, se omitido) enderecada
        pelo espaco de `entity_capacity` deste `MemoryManager`. So pode
        ser chamado durante a composicao; levanta erro se `name` ja
        estiver registrado ou se chamado apos o inicio do gameplay.
        """
        if name in self._pools:
            raise ValueError(f"pool '{name}' ja registrada neste MemoryManager")
        pool = ComponentPool(
            dtype=dtype,
            dense_capacity=dense_capacity if dense_capacity is not None else self._entity_capacity,
            entity_capacity=self._entity_capacity,
        )
        self._pools[name] = pool
        return pool

    def get_pool(self, name: str) -> ComponentPool:
        """Retorna a MESMA instancia de `ComponentPool` registrada sob `name` (nunca uma copia)."""
        return self._pools[name]

    def has_pool(self, name: str) -> bool:
        """Indica se ja existe uma pool registrada sob `name`."""
        return name in self._pools

    def acquire_entity(self) -> PackedEntityId:
        """
        Retira o topo de `_entity_free_slots` (O(1), sem alocacao de
        array novo), le a geracao atual primitiva daquele indice, e
        retorna `EntityHandle.pack_raw(index, generation)` -- um UNICO
        `PackedEntityId`. Zero-GC estrito: em NENHUM momento uma
        instancia de `EntityHandle` e construida, mesmo quando chamado
        de dentro de `ISystem.update()` (ex.: `RhythmSpawnerSystem`,
        `DungeonStreamingSystem`). Levanta erro se a capacidade maxima
        de entidades foi atingida.
        """
        if self._free_count == 0:
            raise IndexError("MemoryManager entity capacity exceeded")
        self._free_count -= 1
        index = int(self._free_slots[self._free_count])
        generation = int(self._entity_generations[index])
        return EntityHandle.pack_raw(index, generation)

    def release_entity(self, packed_handle: PackedEntityId) -> None:
        """
        Extrai `index`/`generation` primitivos de `packed_handle` (sem
        instanciar `EntityHandle`) e delega a `release_entity_raw`.
        Chamar com um handle ja obsoleto e um no-op seguro.
        """
        self.release_entity_raw(unpack_index(packed_handle), unpack_generation(packed_handle))

    def release_entity_raw(self, index: int, generation: int) -> None:
        """
        Variante primitiva usada por `World.flush()`, que ja mantem
        `index`/`generation` separados desde `destroy_entity`. Se
        `generation` nao casar com a atual, e no-op seguro. Caso
        contrario: incrementa `_entity_generations[index]`
        (invalidando qualquer handle antigo), devolve `index` a
        free-list, e desanexa esse indice de TODAS as pools registradas
        (`pool.detach`, no-op se ausente) -- O(numero de tipos de pool),
        nunca O(entidades ativas).
        """
        if not self.is_alive_raw(index, generation):
            return
        self._entity_generations[index] = (self._entity_generations[index] + 1) & 0xFFFFFFFF
        self._free_slots[self._free_count] = index
        self._free_count += 1
        for pool in self._pools.values():
            pool.detach(index)

    def is_alive(self, packed_handle: PackedEntityId) -> bool:
        """Extrai `index`/`generation` primitivos e delega a `is_alive_raw`."""
        return self.is_alive_raw(unpack_index(packed_handle), unpack_generation(packed_handle))

    def is_alive_raw(self, index: int, generation: int) -> bool:
        """Compara `generation` com a geracao atual armazenada em `_entity_generations[index]`."""
        return bool(self._entity_generations[index] == generation)

    def is_alive_batch(self, packed_handles: np.ndarray) -> np.ndarray:
        """
        Variante VETORIZADA de `is_alive`: recebe um array de
        `PackedEntityId` (ex.: `pool.active_view()["owner_handle"]`) e
        retorna um array booleano paralelo, via `unpack_batch` seguido
        de comparacao vetorizada contra `_entity_generations` -- sem
        laco Python por entidade e sem instanciar `EntityHandle`. API
        que Systems DEVEM usar para checar liveness em massa por frame.
        """
        indices, generations = unpack_batch(packed_handles)
        return self._entity_generations[indices] == generations
