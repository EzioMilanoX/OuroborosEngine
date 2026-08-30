# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bookkeeping PURO de iniciativa (ROADMAP M13) -- nenhum conceito de fase/UI aqui, so "quem joga agora"."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


class TurnQueue:
    """
    Fila de iniciativa: quem joga agora, avancar pro proximo, remover um
    morto. NAO sabe nada sobre fases de turno/UI/input -- isso e
    responsabilidade exclusiva de uma cena (`TacticsBattleScene`), mesmo
    principio de separacao de `UniformGrid` (so indice espacial, nunca
    decide o que fazer com uma colisao).

    `build()` roda uma unica vez no inicio da batalha (fora do hot-path --
    nao ha hot-path aqui, tudo e por evento discreto de turno). `entity_index`
    e o indice GLOBAL de entidade (nao um `PackedEntityId`) -- valido
    enquanto a UNICA suposicao desta classe se mantiver: nenhuma entidade e
    criada durante uma batalha ja em andamento (roster fixo, sem reforcos/
    invocacoes no v1). Se essa suposicao mudar no futuro, o indice de uma
    unidade morta e removida por `MemoryManager` poderia ser reciclado por
    uma entidade totalmente nao relacionada -- `PackedEntityId`
    (`World.pack_current`) seria necessario nesse caso, nao mais um
    `entity_index` bruto.
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._entity_index = np.zeros(capacity, dtype=np.int64)
        self._initiative = np.zeros(capacity, dtype=np.float32)
        self._alive = np.zeros(capacity, dtype=bool)
        self._count = 0
        self._alive_count = 0
        self._current_position = 0

    def build(self, entity_indices: Sequence[int], initiative_values: Sequence[float]) -> None:
        """Popula a fila UMA UNICA VEZ, ordenada por iniciativa
        DESCENDENTE -- `kind="stable"` (mesmo idioma de `UniformGrid.rebuild`)
        garante que unidades com iniciativa EMPATADA mantenham um
        desempate deterministico pela ordem de `entity_indices` recebida
        (ordem de spawn), nao uma ordem arbitraria de um sort instavel."""
        count = len(entity_indices)
        if count > self._capacity:
            raise ValueError(f"TurnQueue capacity excedida: {count} > {self._capacity}")

        # Ordena pelos valores NEGADOS (ascendente estavel) em vez de ordenar
        # ascendente e inverter o resultado -- inverter um sort estavel
        # ascendente da "descendente com o desempate TAMBEM invertido" (o
        # oposto do que se quer), nao "descendente preservando a ordem
        # original nos empates". Bug real achado pelos meus proprios testes.
        order = np.argsort(-np.asarray(initiative_values, dtype=np.float32), kind="stable")
        entity_indices_array = np.asarray(entity_indices, dtype=np.int64)[order]
        initiative_array = np.asarray(initiative_values, dtype=np.float32)[order]

        self._entity_index[:count] = entity_indices_array
        self._initiative[:count] = initiative_array
        self._alive[:count] = True
        self._count = count
        self._alive_count = count
        self._current_position = 0

    @property
    def current_entity_index(self) -> Optional[int]:
        """`entity_index` de quem joga agora, ou `None` se ninguem
        restar vivo (fim de batalha) -- NUNCA le `_current_position`
        cegamente: confirma que a posicao atual esta realmente viva antes
        de devolver algo (defensivo -- no v1 uma unidade so morre no
        turno de OUTRA, nunca no proprio, mas um efeito futuro de
        contra-ataque poderia matar a propria unidade ativa no meio do
        turno dela)."""
        if self._alive_count == 0:
            return None
        if not self._alive[self._current_position]:
            return None
        return int(self._entity_index[self._current_position])

    def advance_to_next(self) -> Optional[int]:
        """Avanca `_current_position` (com wraparound) ate achar uma
        entrada viva, ou desiste apos no maximo `_count` passos (nunca
        um loop sem limite -- se `_alive_count == 0`, retorna `None`
        IMEDIATAMENTE, sem nem tentar escanear a fila inteira morta)."""
        if self._alive_count == 0:
            return None
        for _ in range(self._count):
            self._current_position = (self._current_position + 1) % self._count
            if self._alive[self._current_position]:
                return int(self._entity_index[self._current_position])
        return None  # defensivo: so alcancavel se _alive_count > 0 mas nada foi achado (nao deveria acontecer)

    def remove(self, entity_index: int) -> None:
        """Marca a entrada de `entity_index` como morta (`_alive = False`).
        Nao-op se `entity_index` nao estiver na fila (ex.: chamado duas
        vezes por engano)."""
        matches = np.flatnonzero(self._entity_index[: self._count] == entity_index)
        for position in matches:
            if self._alive[position]:
                self._alive[position] = False
                self._alive_count -= 1
