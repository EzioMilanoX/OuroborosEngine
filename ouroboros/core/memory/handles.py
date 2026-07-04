"""
Handles de entidade Zero-GC.

`PackedEntityId` (int primitivo de 64 bits) e o tipo que trafega em TODO
caminho alcancavel a partir de `ISystem.update()`/`World.step()`.
`EntityHandle` (NamedTuple) e um tipo de CONVENIENCIA para inspecao
legivel de `index`/`generation`, com uso restrito a codigo FORA do loop
de gameplay (testes, telemetria, ferramentas de editor/composicao) --
nunca deve ser instanciado dentro de `ISystem.update()` nem de qualquer
metodo por ele chamado transitivamente.
"""
from __future__ import annotations

from typing import NamedTuple, Tuple

import numpy as np

from ouroboros.core.constants import INVALID_ENTITY_INDEX

PackedEntityId = int
"""Alias semantico para um handle de entidade empacotado como um unico
`int` primitivo de 64 bits (layout: ver `EntityHandle`). Retorno/
parametro de `MemoryManager.acquire_entity/release_entity/is_alive`
(e variantes `_raw`/`_batch`) e de `World.create_entity/destroy_entity/
is_alive`. Nenhuma dessas chamadas instancia `EntityHandle`."""


class EntityHandle(NamedTuple):
    """
    Identificador legivel e imutavel de uma entidade (indice global +
    geracao) -- tipo de CONVENIENCIA, nao um tipo de hot-path.

    ATENCAO -- uso restrito FORA do loop de gameplay: por ser um
    NamedTuple, construir uma instancia aciona um construtor de classe
    Python, exatamente o padrao que a Constituicao proibe durante o
    loop de gameplay. `MemoryManager`/`World` nunca instanciam
    `EntityHandle` em nenhum metodo alcancavel a partir de
    `ISystem.update()`/`World.step()`.

    Invariantes:
        - `index` e um indice dentro do espaco GLOBAL de entidades
          gerenciado exclusivamente por `MemoryManager` -- o MESMO
          espaco de indices para todas as `ComponentPool` do `World`.
        - `generation` deve casar com a geracao atual armazenada por
          `MemoryManager` para `index`; caso contrario o handle esta
          obsoleto ("stale") e deve ser tratado como invalido.
        - Layout de empacotamento: 64 bits, sendo os 32 bits menos
          significativos o `index` (uint32) e os 32 bits mais
          significativos a `generation` (uint32):
          `packed == (generation << 32) | (index & 0xFFFFFFFF)`.
    """

    index: int
    generation: int

    def is_null(self) -> bool:
        """Retorna True se `index == INVALID_ENTITY_INDEX` (handle sentinela)."""
        return self.index == INVALID_ENTITY_INDEX

    def pack(self) -> PackedEntityId:
        """
        Empacota esta instancia (`index`, `generation`) em um unico
        `PackedEntityId`, para ser armazenado como CAMPO PRIMITIVO
        dentro de outra `ComponentPool` (ex.: `owner_handle: np.uint64`
        num pool de projeteis) sem introduzir um dtype de objeto Python
        na pool. Equivalente a `EntityHandle.pack_raw(self.index, self.generation)`.
        """
        return EntityHandle.pack_raw(self.index, self.generation)

    @staticmethod
    def pack_raw(index: int, generation: int) -> PackedEntityId:
        """
        Empacota os PRIMITIVOS `index`/`generation` diretamente em um
        `PackedEntityId`, SEM construir nenhuma instancia de
        `EntityHandle`. Esta e a operacao que
        `MemoryManager.acquire_entity` usa internamente.
        """
        return ((int(generation) & 0xFFFFFFFF) << 32) | (int(index) & 0xFFFFFFFF)

    @staticmethod
    def unpack(packed: PackedEntityId) -> "EntityHandle":
        """
        Reconstroi uma instancia de `EntityHandle` a partir de
        `packed`. USO RESTRITO A CODIGO FORA DO LOOP DE GAMEPLAY
        (testes, telemetria, ferramentas de editor/composicao) -- esta
        chamada instancia um objeto Python. Para o hot-path, use as
        funcoes escalares `unpack_index`/`unpack_generation` (uma
        entidade) ou `unpack_batch` (vetorizado, em lote).
        """
        return EntityHandle(index=unpack_index(packed), generation=unpack_generation(packed))


NULL_HANDLE: EntityHandle = EntityHandle(index=INVALID_ENTITY_INDEX, generation=0)
"""Handle sentinela de CONVENIENCIA, construido UMA UNICA VEZ no
carregamento do modulo (fora de qualquer loop de gameplay). Para
comparacoes de sentinela dentro do hot-path, use `NULL_PACKED_HANDLE`."""

NULL_PACKED_HANDLE: PackedEntityId = EntityHandle.pack_raw(INVALID_ENTITY_INDEX, 0)
"""Equivalente primitivo de `NULL_HANDLE`, calculado uma unica vez via
`pack_raw` (sem instanciar `EntityHandle`). E o valor que Systems devem
comparar dentro do hot-path para detectar um handle 'vazio'."""


def unpack_index(packed: PackedEntityId) -> int:
    """Extrai apenas o `index` primitivo (uint32) via mascara de bits
    (`packed & 0xFFFFFFFF`), sem instanciar `EntityHandle`. Seguro para
    uso escalar dentro do hot-path."""
    return int(packed) & 0xFFFFFFFF


def unpack_generation(packed: PackedEntityId) -> int:
    """Extrai apenas a `generation` primitiva (uint32) via deslocamento
    de bits (`packed >> 32`), sem instanciar `EntityHandle`."""
    return (int(packed) >> 32) & 0xFFFFFFFF


def pack_batch(indices: np.ndarray, generations: np.ndarray) -> np.ndarray:
    """
    Variante VETORIZADA de `EntityHandle.pack_raw`: recebe dois arrays
    NumPy paralelos `indices`/`generations` (inteiros sem sinal, mesmo
    shape) e retorna um array de `PackedEntityId` (dtype `np.uint64`)
    via deslocamento/OR de bits do NumPy, sem laco Python e sem
    instanciar `EntityHandle`. Uso tipico: inicializar em massa um
    campo `owner_handle` de uma `ComponentPool` a partir de arrays de
    `index`/`generation` ja resolvidos.
    """
    idx = indices.astype(np.uint64) & np.uint64(0xFFFFFFFF)
    gen = generations.astype(np.uint64) & np.uint64(0xFFFFFFFF)
    return (gen << np.uint64(32)) | idx


def unpack_batch(packed: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Variante VETORIZADA de `unpack_index`/`unpack_generation`: recebe
    um array de `PackedEntityId` (dtype `np.uint64`) -- tipicamente
    `pool.active_view()["owner_handle"]` -- e retorna dois arrays
    paralelos `(indices, generations)` via mascara/deslocamento de bits
    vetorizados, sem laco Python e sem instanciar `EntityHandle`. Base
    de `MemoryManager.is_alive_batch`.
    """
    packed_u64 = packed.astype(np.uint64)
    indices = (packed_u64 & np.uint64(0xFFFFFFFF)).astype(np.int64)
    generations = (packed_u64 >> np.uint64(32)).astype(np.int64)
    return indices, generations
