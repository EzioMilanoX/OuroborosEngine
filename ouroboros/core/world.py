"""Registry central: orquestra MemoryManager, Systems e arquetipos data-driven."""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.core.memory.handles import PackedEntityId, unpack_generation, unpack_index
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.base_system import ISystem


class World:
    """
    Registry central: orquestra o `MemoryManager`, a lista ordenada de
    `ISystem` e os arquetipos data-driven (nome -> conjunto de pools)
    usados por `create_entity`.

    Invariante critica sobre mutacao estrutural em tempo de gameplay:
        - `create_entity` e IMEDIATO: um "append" no final de um array
          denso (`ComponentPool.attach`) nunca invalida linhas densas
          ja resolvidas por outro `ISystem` no MESMO frame -- por isso
          e seguro que sistemas como `RhythmSpawnerSystem` (Pilar 4) ou
          `DungeonStreamingSystem` (Pilar 3) chamem `create_entity`
          dentro do proprio `update()`. Isso e Zero-GC de fato:
          `create_entity` devolve um `PackedEntityId` (int primitivo de
          64 bits) produzido por `MemoryManager.acquire_entity`, sem
          jamais instanciar `EntityHandle`.
        - `destroy_entity`, ao contrario, e DIFERIDO: enfileira o par
          `(index, generation)`, extraido de forma primitiva do
          `PackedEntityId` recebido, num buffer pre-alocado
          (`_pending_destroy_*`, tamanho fixo `max_structural_commands`)
          e so e efetivado em `flush()`, chamado automaticamente uma
          unica vez ao final de `step()`. Isso existe porque destruir
          no meio do frame aciona um swap-remove que PODE mover o
          conteudo da ultima linha densa para a posicao liberada,
          invalidando silenciosamente indices/linhas densas que um
          `ISystem` anterior no mesmo frame ja tenha capturado (ex.:
          pares de `CollisionSystem.get_collision_pairs()`).
    """

    def __init__(self, memory_manager: MemoryManager, max_structural_commands: int = 4096) -> None:
        """
        Guarda `memory_manager`, inicializa a lista vazia de sistemas, o
        registro vazio de arquetipos, e pre-aloca o buffer de
        destruicoes pendentes (`_pending_destroy_indices`,
        `_pending_destroy_generations`, ambos shape
        `(max_structural_commands,)`, dtype inteiro primitivo).
        """
        self._memory_manager = memory_manager
        self._systems: List[ISystem] = []
        self._archetypes: Dict[str, Tuple[str, ...]] = {}
        self._max_structural_commands = max_structural_commands
        self._pending_destroy_indices = np.zeros(max_structural_commands, dtype=np.int64)
        self._pending_destroy_generations = np.zeros(max_structural_commands, dtype=np.uint32)
        self._pending_destroy_count = 0

    def register_system(self, system: ISystem) -> None:
        """Adiciona `system` ao final da lista de execucao. So deve ser chamado durante a composicao."""
        self._systems.append(system)

    def register_archetype(self, name: str, pool_names: Tuple[str, ...]) -> None:
        """
        Associa um nome de arquetipo (carregado de JSON pelo Pilar 3/4
        -- ex.: `data/archetypes/enemy_goblin.json` -- nunca hardcoded
        em codigo de gameplay) as pools que uma entidade desse tipo
        deve ter anexadas ao ser criada.
        """
        self._archetypes[name] = tuple(pool_names)

    def create_entity(self, archetype_name: str) -> PackedEntityId:
        """
        Aciona `memory_manager.acquire_entity()` (que retorna um
        `PackedEntityId` primitivo -- NENHUMA instancia de
        `EntityHandle` e construida neste caminho) e, para cada pool do
        arquetipo `archetype_name`, `pool.attach(index)`, onde `index`
        e extraido do `PackedEntityId` via `unpack_index` (operacao
        primitiva de bits, sem alocacao).

        Retorna o `PackedEntityId` resultante. Este e o UNICO valor de
        identidade de entidade que atravessa `ISystem.update()`. O
        chamador e responsavel por escrever os valores iniciais dos
        componentes anexados via `world.get_pool(nome).active_view()[...]`.
        """
        packed = self._memory_manager.acquire_entity()
        index = unpack_index(packed)
        for pool_name in self._archetypes[archetype_name]:
            self._memory_manager.get_pool(pool_name).attach(index)
        return packed

    def destroy_entity(self, packed_handle: PackedEntityId) -> None:
        """
        Enfileira a destruicao de `packed_handle` (ver nota de classe)
        -- NAO aciona `ComponentPool.detach` imediatamente. Extrai
        `index`/`generation` primitivos via `unpack_index`/
        `unpack_generation` (sem instanciar `EntityHandle`) e grava-os
        nas proximas posicoes livres de `_pending_destroy_indices`/
        `_pending_destroy_generations`. Retorna sem erro mesmo se
        `packed_handle` ja estiver obsoleto. Levanta erro apenas se a
        fila de comandos estruturais deste frame estiver saturada.
        """
        if self._pending_destroy_count >= self._max_structural_commands:
            raise IndexError("World structural command queue (max_structural_commands) exceeded")
        self._pending_destroy_indices[self._pending_destroy_count] = unpack_index(packed_handle)
        self._pending_destroy_generations[self._pending_destroy_count] = unpack_generation(packed_handle)
        self._pending_destroy_count += 1

    def is_alive(self, packed_handle: PackedEntityId) -> bool:
        """Atalho primitivo para `self._memory_manager.is_alive(packed_handle)` -- nao instancia `EntityHandle`."""
        return self._memory_manager.is_alive(packed_handle)

    def get_pool(self, name: str) -> ComponentPool:
        """Atalho para `self._memory_manager.get_pool(name)`, usado por Systems e pela camada de composicao."""
        return self._memory_manager.get_pool(name)

    def has_pool(self, name: str) -> bool:
        """Atalho para `self._memory_manager.has_pool(name)`, usado por loaders (ex.: `ArchetypeLoader`) para validar referencias antes de registrar."""
        return self._memory_manager.has_pool(name)

    def has_archetype(self, name: str) -> bool:
        """Indica se `name` ja foi registrado via `register_archetype`."""
        return name in self._archetypes

    def step(self, delta_time: float) -> None:
        """
        Executa `system.update(self, delta_time)` para cada sistema
        registrado, na ordem de registro, e entao chama `self.flush()`
        exatamente uma vez. Este e o UNICO ponto de entrada do loop de
        gameplay por frame.
        """
        for system in self._systems:
            system.update(self, delta_time)
        self.flush()

    def flush(self) -> None:
        """
        Efetiva, via `memory_manager.release_entity_raw(index,
        generation)` para cada par armazenado em
        `_pending_destroy_indices`/`_pending_destroy_generations` (na
        ordem de enfileiramento), todas as destruicoes enfileiradas
        desde o ultimo `flush`, e zera `_pending_destroy_count` (sem
        desalocar os arrays do buffer).
        """
        for i in range(self._pending_destroy_count):
            index = int(self._pending_destroy_indices[i])
            generation = int(self._pending_destroy_generations[i])
            self._memory_manager.release_entity_raw(index, generation)
        self._pending_destroy_count = 0
