# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pool de memoria generica pre-alocada (sparse-set) para um tipo de componente."""
from __future__ import annotations

import numpy as np

from ouroboros.core.constants import INVALID_DENSE_ROW, INVALID_ENTITY_INDEX


class ComponentPool:
    """
    Pool de memoria generica e pre-alocada para UM tipo de componente,
    organizada como "sparse set": um array `dense_data` compactado
    (sem buracos) para iteracao vetorizada O(ativos), enderecado por um
    array esparso `sparse_to_dense` indexado pelo INDICE GLOBAL DE
    ENTIDADE (o mesmo espaco de indices administrado por
    `MemoryManager` -- nunca um contador proprio desta pool).

    Isso resolve, por construcao, um bug classico de esqueletos ECS
    ingenuos sobre NumPy: se cada pool gerasse seu proprio indice de
    forma independente, dois arquetipos com conjuntos de pools
    diferentes acabariam com "o mesmo indice" apontando para entidades
    DIFERENTES em pools distintas. Aqui isso e estruturalmente
    impossivel, pois nenhuma pool emite indices -- ela apenas recebe o
    indice global (ja emitido por `MemoryManager`) e o mapeia para sua
    propria linha densa.

    Invariantes:
        - `dense_data` e um `np.ndarray` estruturado de capacidade FIXA
          `dense_capacity`, alocado uma unica vez em `__init__`.
        - `sparse_to_dense` tem tamanho `entity_capacity`, inicializado
          com `INVALID_DENSE_ROW` em todas as posicoes.
        - `dense_data[:count]` e SEMPRE exatamente o conjunto de
          componentes ativos, compactado e contiguo.
        - `attach`/`detach` nunca redimensionam os arrays; exceder
          `dense_capacity` e um erro fatal de configuracao, nunca um
          gatilho de realocacao dinamica.
    """

    def __init__(self, dtype: np.dtype, dense_capacity: int, entity_capacity: int) -> None:
        """
        Pre-aloca `dense_data` (shape `(dense_capacity,)`, dtype
        estruturado fornecido), `dense_to_sparse` (shape
        `(dense_capacity,)`, inteiro) e `sparse_to_dense` (shape
        `(entity_capacity,)`, inteiro, inicializado com
        `INVALID_DENSE_ROW`). Nao redimensiona nada depois disso.
        """
        self._dtype = dtype
        self._capacity = dense_capacity
        self._entity_capacity = entity_capacity
        self._dense_data = np.zeros(dense_capacity, dtype=dtype)
        self._dense_to_sparse = np.full(dense_capacity, INVALID_ENTITY_INDEX, dtype=np.int64)
        self._sparse_to_dense = np.full(entity_capacity, INVALID_DENSE_ROW, dtype=np.int64)
        self._count = 0

    @property
    def dtype(self) -> np.dtype:
        """Schema (dtype estruturado) armazenado por esta pool."""
        return self._dtype

    @property
    def capacity(self) -> int:
        """Numero maximo fixo de componentes simultaneamente anexados nesta pool."""
        return self._capacity

    @property
    def count(self) -> int:
        """Numero de componentes atualmente ativos (linhas validas em `dense_data[:count]`)."""
        return self._count

    def is_attached(self, entity_index: int) -> bool:
        """Retorna True se a entidade `entity_index` possui uma linha ativa nesta pool."""
        return bool(self._sparse_to_dense[entity_index] != INVALID_DENSE_ROW)

    def attach(self, entity_index: int) -> int:
        """
        Anexa este componente a entidade `entity_index`, alocando a
        proxima linha densa livre (`count`) e atualizando os mapas
        `sparse_to_dense`/`dense_to_sparse`. Retorna a linha densa
        resultante, para o chamador escrever os valores iniciais via
        `pool.active_view()[linha] = ...`. Levanta erro se `entity_index`
        ja estiver anexado ou se `count == capacity`.
        """
        if self.is_attached(entity_index):
            raise ValueError(f"entity_index {entity_index} already attached to this ComponentPool")
        if self._count >= self._capacity:
            raise IndexError("ComponentPool dense capacity exceeded")
        row = self._count
        self._sparse_to_dense[entity_index] = row
        self._dense_to_sparse[row] = entity_index
        self._count += 1
        return row

    def detach(self, entity_index: int) -> None:
        """
        Remove o componente de `entity_index` via swap-remove O(1): a
        ultima linha densa ativa e movida para a posicao liberada e os
        mapas esparsos sao atualizados. No-op seguro se a entidade nao
        possuir este componente.
        """
        row = self._sparse_to_dense[entity_index]
        if row == INVALID_DENSE_ROW:
            return
        last_row = self._count - 1
        if row != last_row:
            last_entity_index = self._dense_to_sparse[last_row]
            self._dense_data[row] = self._dense_data[last_row]
            self._dense_to_sparse[row] = last_entity_index
            self._sparse_to_dense[last_entity_index] = row
        self._dense_to_sparse[last_row] = INVALID_ENTITY_INDEX
        self._sparse_to_dense[entity_index] = INVALID_DENSE_ROW
        self._count -= 1

    def dense_row_of(self, entity_index: int) -> int:
        """Resolve a linha densa correspondente a `entity_index` via `sparse_to_dense`."""
        return int(self._sparse_to_dense[entity_index])

    def dense_rows_of(self, entity_indices: np.ndarray) -> np.ndarray:
        """Variante VETORIZADA de `dense_row_of`: resolve as linhas densas
        de varios `entity_indices` de uma vez via `sparse_to_dense`, sem
        expor o array interno a chamadores externos."""
        return self._sparse_to_dense[entity_indices]

    def active_view(self) -> np.ndarray:
        """View (SEM copia) de `dense_data[:count]`: layout SoA compactado dos componentes ativos."""
        return self._dense_data[: self._count]

    def active_entity_indices(self) -> np.ndarray:
        """
        View (SEM copia) de `dense_to_sparse[:count]`: os indices
        globais de entidade correspondentes, na mesma ordem de
        `active_view()`. Usar com `pack_batch` (ver `handles.py`) para
        obter `PackedEntityId` em lote, sem instanciar `EntityHandle`.
        """
        return self._dense_to_sparse[: self._count]


def intersect_entity_indices(*pools: ComponentPool) -> np.ndarray:
    """
    Retorna os indices globais de entidade presentes simultaneamente em
    TODAS as `pools` fornecidas (ex.: entidades com Transform E
    Velocity, para `PhysicsSystem`). Parte da pool com menor `count` e
    consulta as demais via seus mapas esparsos (O(1) por consulta).

    Nota honesta sobre custo: produz UM array de resultado novo por
    CHAMADA (nao por entidade) -- equivalente ao custo de qualquer
    selecao vetorizada de tamanho variavel em NumPy puro. Nao e o
    padrao de alocacao por entidade que a Constituicao proibe.
    """
    if not pools:
        return np.empty(0, dtype=np.int64)
    smallest = min(pools, key=lambda p: p.count)
    candidate = smallest.active_entity_indices()
    if candidate.size == 0:
        return candidate.copy()
    mask = np.ones(candidate.shape[0], dtype=bool)
    for pool in pools:
        if pool is smallest:
            continue
        rows = pool._sparse_to_dense[candidate]
        mask &= rows != INVALID_DENSE_ROW
    return candidate[mask].copy()
