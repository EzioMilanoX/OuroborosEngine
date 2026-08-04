# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Grade uniforme de particionamento espacial, usada opcionalmente por CollisionSystem."""
from __future__ import annotations

from typing import Tuple

import numpy as np


class UniformGrid:
    """
    Estrutura auxiliar de particionamento espacial (grade uniforme) para
    reduzir os pares candidatos avaliados por `CollisionSystem` de
    O(n^2) para proximo de O(n) em cenarios tipicos de gameplay.

    Invariantes:
        - `_bucket_counts`, `_bucket_offsets` (tamanho = numero fixo de
          celulas) e `_bucket_entries` (tamanho = `entity_capacity`) sao
          pre-alocados na construcao e nunca redimensionados.
        - Uso opcional: `CollisionSystem` funciona sem grade (varredura
          bruta O(n^2) sobre um `max_pairs` fixo); a grade e uma
          otimizacao de escala que nao muda a interface publica.

    Nota honesta sobre custo: `rebuild()` reescreve o CONTEUDO desses
    buffers a cada frame via operacoes vetorizadas idiomaticas do
    NumPy (contagem por celula + prefix-sum + dispersao dos indices).
    Uma ou duas dessas operacoes podem alocar um array de resultado
    pequeno, de tamanho proporcional ao NUMERO DE CELULAS (fixo), nao
    ao numero de entidades -- um custo de buffer primitivo limitado e
    previsivel, nao a instanciacao de objetos de jogo por entidade que
    a Constituicao proibe.
    """

    def __init__(
        self,
        world_bounds: Tuple[float, float, float, float],
        cell_size: float,
        entity_capacity: int,
        max_candidate_pairs: int,
    ) -> None:
        """Calcula o numero de celulas a partir de `world_bounds`/`cell_size` e pre-aloca todos os buffers internos."""
        min_x, min_y, max_x, max_y = world_bounds
        self._min_x = min_x
        self._min_y = min_y
        self._cell_size = cell_size
        self._cols = max(1, int(np.ceil((max_x - min_x) / cell_size)))
        self._rows = max(1, int(np.ceil((max_y - min_y) / cell_size)))
        self._cell_count = self._cols * self._rows
        self._entity_capacity = entity_capacity
        self._max_candidate_pairs = max_candidate_pairs
        self._bucket_counts = np.zeros(self._cell_count, dtype=np.int64)
        self._bucket_offsets = np.zeros(self._cell_count + 1, dtype=np.int64)
        self._bucket_entries = np.zeros(entity_capacity, dtype=np.int64)
        self._candidate_pairs = np.zeros((max_candidate_pairs, 2), dtype=np.int64)
        self._pair_count = 0
        self._active_count = 0

    def rebuild(self, positions_xy: np.ndarray, entity_indices: np.ndarray) -> None:
        """Reindexa as posicoes ativas (`positions_xy`, paralelo a `entity_indices`) nas celulas da grade, in-place."""
        n = entity_indices.shape[0]
        self._active_count = n
        self._bucket_counts[:] = 0
        if n == 0:
            self._bucket_offsets[:] = 0
            return
        col = np.clip(((positions_xy[:, 0] - self._min_x) / self._cell_size).astype(np.int64), 0, self._cols - 1)
        row = np.clip(((positions_xy[:, 1] - self._min_y) / self._cell_size).astype(np.int64), 0, self._rows - 1)
        cell_ids = row * self._cols + col
        np.add.at(self._bucket_counts, cell_ids, 1)
        np.cumsum(self._bucket_counts, out=self._bucket_offsets[1:])
        self._bucket_offsets[0] = 0
        order = np.argsort(cell_ids, kind="stable")
        self._bucket_entries[:n] = entity_indices[order]

    def query_candidate_pairs(self) -> np.ndarray:
        """
        Retorna a view ativa do buffer pre-alocado de pares candidatos
        (indices globais de entidade, shape `(k, 2)`, `k <=
        max_candidate_pairs`) que compartilham celula ou celulas
        vizinhas, prontos para uma checagem fina de sobreposicao AABB.

        Implementacao de referencia: itera sobre CELULAS (nao sobre
        entidades ativas), emparelhando cada celula com ela mesma e com
        as celulas "adiante" (direita, abaixo, diagonais) para nunca
        gerar o mesmo par duas vezes.
        """
        self._pair_count = 0
        forward_offsets = (1, self._cols, self._cols - 1, self._cols + 1)
        for cell in range(self._cell_count):
            if self._pair_count >= self._max_candidate_pairs:
                break
            start = int(self._bucket_offsets[cell])
            end = int(self._bucket_offsets[cell + 1])
            if start == end:
                continue
            cell_entities = self._bucket_entries[start:end]

            for i in range(len(cell_entities)):
                for j in range(i + 1, len(cell_entities)):
                    if self._pair_count >= self._max_candidate_pairs:
                        return self._candidate_pairs[: self._pair_count]
                    self._candidate_pairs[self._pair_count, 0] = cell_entities[i]
                    self._candidate_pairs[self._pair_count, 1] = cell_entities[j]
                    self._pair_count += 1

            col = cell % self._cols
            for offset in forward_offsets:
                if offset == 1 and col == self._cols - 1:
                    continue
                if offset == self._cols - 1 and col == 0:
                    continue
                neighbor = cell + offset
                if neighbor < 0 or neighbor >= self._cell_count:
                    continue
                n_start = int(self._bucket_offsets[neighbor])
                n_end = int(self._bucket_offsets[neighbor + 1])
                if n_start == n_end:
                    continue
                neighbor_entities = self._bucket_entries[n_start:n_end]
                for a in cell_entities:
                    for b in neighbor_entities:
                        if self._pair_count >= self._max_candidate_pairs:
                            return self._candidate_pairs[: self._pair_count]
                        self._candidate_pairs[self._pair_count, 0] = a
                        self._candidate_pairs[self._pair_count, 1] = b
                        self._pair_count += 1

        return self._candidate_pairs[: self._pair_count]
