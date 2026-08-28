# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Screen shake como estado de cena/apresentacao (ROADMAP M3) -- nao do nucleo."""
from __future__ import annotations

import random
from typing import Callable, Optional, Tuple


class ScreenShake:
    """
    Estado de CENA/apresentacao, nao do nucleo (texto explicito do
    ROADMAP): nunca importa `IRenderer` nem chama `set_camera_offset`
    sozinho -- so devolve um offset `(dx, dy)` decaindo linearmente ao
    longo da duracao disparada; o chamador (uma cena/script de
    composicao) e quem aplica isso via `renderer.set_camera_offset(dx, dy)`
    a cada frame.

    Fonte de aleatoriedade injetavel (default `random.uniform(-1, 1)`
    da stdlib) -- deliberadamente NAO usa
    `ouroboros.roguelite.generation.random.StrictRandom` (Pilar 3):
    `ScreenShake` e generico, e `ouroboros.bootstrap` nao deveria
    depender de um pilar de produto especifico. Um produto que queira
    determinismo injeta seu proprio gerador via `rng`.
    """

    def __init__(self, rng: Optional[Callable[[], float]] = None) -> None:
        self._rng = rng if rng is not None else (lambda: random.uniform(-1.0, 1.0))
        self._intensity = 0.0
        self._duration_seconds = 0.0
        self._remaining_seconds = 0.0

    def trigger(self, intensity: float, duration_seconds: float) -> None:
        """Inicia (ou reinicia) um shake de `intensity` (magnitude maxima do
        offset) decaindo linearmente ao longo de `duration_seconds`."""
        self._intensity = intensity
        self._duration_seconds = duration_seconds
        self._remaining_seconds = duration_seconds

    def update(self, delta_time: float) -> Tuple[float, float]:
        """Avanca o decaimento e retorna o offset `(dx, dy)` deste frame --
        `(0.0, 0.0)` se nenhum shake estiver ativo ou ja tiver expirado."""
        if self._remaining_seconds <= 0.0:
            return (0.0, 0.0)
        self._remaining_seconds -= delta_time
        if self._remaining_seconds <= 0.0:
            self._remaining_seconds = 0.0
            return (0.0, 0.0)
        decay = self._remaining_seconds / self._duration_seconds
        magnitude = self._intensity * decay
        return (self._rng() * magnitude, self._rng() * magnitude)
