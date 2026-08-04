# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contrato base de um sistema de gameplay vetorizado."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ouroboros.core.world import World


class ISystem(ABC):
    """
    Contrato base de um sistema de gameplay vetorizado.

    Invariante fundamental (Zero-GC): implementacoes devem resolver as
    `ComponentPool` de que precisam UMA UNICA VEZ em `__init__` (fora do
    loop de gameplay) e, em `update`, operar via slicing/vetorizacao
    NumPy sobre `active_view()`/`intersect_entity_indices(...)` -- nunca
    com um `for entidade in entidades: ...` que instancie objetos
    Python por entidade.

    Esta proibicao cobre QUALQUER objeto Python, incluindo tuplas
    nomeadas/dataclasses de handle -- em particular, `EntityHandle`
    (`ouroboros.core.memory.handles`) NUNCA deve ser instanciado dentro
    de `update()` nem de qualquer metodo por ele chamado
    transitivamente (`World.create_entity`, `World.destroy_entity`,
    `MemoryManager.acquire_entity`, etc.). Essas APIs do nucleo operam
    exclusivamente sobre `PackedEntityId` (um `int` primitivo de 64
    bits) ou sobre `index`/`generation` primitivos separados.
    """

    @abstractmethod
    def update(self, world: "World", delta_time: float) -> None:
        """
        Executa um passo de simulacao vetorizado.

        `delta_time` e o tempo de frame em segundos. Sistemas
        sincronizados ao audio (ex.: `RhythmSpawnerSystem`, Pilar 4)
        DEVEM ignorar este `delta_time` acumulado para decidir O QUE
        disparar, consultando em vez disso um `IAudioClock` (Pilar 2)
        injetado no proprio construtor -- isso evita drift entre audio
        e gameplay exigido pela Constituicao da engine.

        Nenhuma linha de codigo executada a partir desta chamada --
        direta ou transitivamente, incluindo qualquer criacao/
        destruicao de entidade -- pode instanciar um objeto Python por
        entidade processada neste frame. Isso inclui explicitamente
        `EntityHandle`: `World.create_entity`/`destroy_entity` e
        `MemoryManager.acquire_entity`/`release_entity`/`is_alive`
        trafegam exclusivamente `PackedEntityId` justamente para que
        `update()` possa criar/destruir entidades sem jamais alocar um
        objeto de handle.
        """
        ...
