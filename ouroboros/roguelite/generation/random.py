# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Portao unico de aleatoriedade do Roguelite: streams de RNG isolados e deterministicos por finalidade."""
from __future__ import annotations

from enum import IntEnum
from typing import Dict, Tuple

import numpy as np


class RandomStreamPurpose(IntEnum):
    """Finalidades de geracao com streams de RNG isolados entre si.

    O valor numerico de cada membro e o "ordinal" usado para derivar a
    entropia do stream (ver `StrictRandom._derive_seed_sequence`) e e um
    CONTRATO ESTAVEL:

      - NUNCA renumerar um membro ja existente -- isso mudaria
        retroativamente o resultado de TODAS as seeds ja distribuidas/
        compartilhadas entre jogadores para essa finalidade.
      - Uma finalidade nova sempre recebe o PROXIMO ordinal inteiro livre,
        nunca reaproveita o ordinal de uma finalidade aposentada.

    Por isso os valores sao atribuidos explicitamente (nunca via
    `enum.auto()`, cujo valor depende da ORDEM textual de declaracao e
    portanto e fragil a reordenacoes acidentais do arquivo-fonte).
    """

    DUNGEON_LAYOUT = 0
    LOOT_TABLE = 1
    ENEMY_PLACEMENT = 2
    MODIFIER_ROLLS = 3


class StrictRandom:
    """Fabrica deterministica de streams de RNG isolados por finalidade.

    Invariante central (reprodutibilidade fim-a-fim): dado o mesmo
    `root_seed`, `stream(purpose, salt)` retorna SEMPRE a mesma sequencia
    de numeros para o mesmo par `(purpose, salt)` -- INDEPENDENTEMENTE de
    quantos numeros ja foram consumidos de OUTROS streams, da ORDEM em
    que os streams foram solicitados pela primeira vez, ou do processo/
    maquina em que o codigo roda.

    Isso e obtido derivando a `numpy.random.SeedSequence` de cada stream
    como uma FUNCAO PURA da tripla `(root_seed, int(purpose), salt)` --
    `np.random.SeedSequence(entropy=(root_seed, int(purpose), salt))`.
    Duas armadilhas conhecidas sao proibidas explicitamente por esta
    classe:

      1. Usar `SeedSequence.spawn()` de forma sequencial/preguicosa para
         derivar sub-streams: `spawn()` mantem um contador interno de
         quantos filhos ja foram gerados a partir da MESMA sequencia-mae,
         portanto o resultado depende da ORDEM/QUANTIDADE de chamadas
         anteriores -- exatamente o tipo de "estado compartilhado entre
         streams" que esta classe existe para eliminar.
      2. Usar `hash()`/`id()` nativos do Python (ou iteracao de
         `dict`/`set`) para transformar `purpose`/`salt` em entropia:
         `hash()` de strings e ALEATORIZADO por processo
         (`PYTHONHASHSEED`) por padrao desde o Python 3.3, entao a mesma
         seed raiz produziria resultados DIFERENTES em execucoes
         diferentes -- quebrando silenciosamente a garantia de
         "compartilhar seed = compartilhar run".

    Por isso `purpose` e tipado como `RandomStreamPurpose` (ordinal
    inteiro estavel, nunca uma string livre) e `salt` e um `int` puro
    (ex.: numero do andar do dungeon, id numerico de uma tabela de loot) --
    nunca uma string cujo hash precisaria ser estabilizado.

    Streams sao cacheados por `(purpose, salt)`: chamadas repetidas com o
    mesmo par retornam o MESMO objeto `Generator` (com o cursor ja
    avancado pelo consumo anterior), nunca um gerador reiniciado do zero.
    """

    def __init__(self, root_seed: int) -> None:
        """Guarda a seed raiz e inicializa vazio o cache de streams.

        Nao deriva nenhuma `SeedSequence` aqui -- a derivacao e
        preguicosa (feita na primeira chamada de `stream()` para cada
        par `(purpose, salt)`), mas sempre pura em relacao a
        `root_seed` (nunca stateful entre pares diferentes).
        """
        self._root_seed = int(root_seed)
        self._streams: Dict[Tuple[int, int], np.random.Generator] = {}

    @property
    def root_seed(self) -> int:
        """Seed raiz imutavel usada para derivar todos os streams."""
        return self._root_seed

    def stream(self, purpose: RandomStreamPurpose, salt: int = 0) -> np.random.Generator:
        """Retorna (criando e cacheando se necessario) o stream isolado de `(purpose, salt)`.

        Args:
            purpose: finalidade estavel da geracao (ver `RandomStreamPurpose`).
            salt: particao deterministica adicional dentro da mesma
                finalidade (ex.: numero do andar, id de tabela de loot).
                Permite sub-streams independentes sem depender da ordem
                das chamadas anteriores -- ao contrario de
                `spawn_child`/`SeedSequence.spawn` sequenciais.

        Invariante: o resultado depende exclusivamente de
            `(self.root_seed, purpose, salt)` -- nunca de streams ja
            consumidos para outros pares.
        """
        key = (int(purpose), int(salt))
        generator = self._streams.get(key)
        if generator is None:
            seed_sequence = self._derive_seed_sequence(purpose, salt)
            generator = np.random.default_rng(seed_sequence)
            self._streams[key] = generator
        return generator

    def _derive_seed_sequence(self, purpose: RandomStreamPurpose, salt: int) -> np.random.SeedSequence:
        """Deriva, de forma pura, `SeedSequence(entropy=(root_seed, int(purpose), salt))`.

        Nao existe nenhum outro caminho de derivacao de entropia nesta
        classe -- em particular, nunca `SeedSequence.spawn()` nem
        `hash()`/`id()` nativos (ver docstring de classe).
        """
        return np.random.SeedSequence(entropy=(self._root_seed, int(purpose), int(salt)))
