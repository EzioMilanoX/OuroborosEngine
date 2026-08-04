# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao nula de IRenderer, para testes headless e para o pipeline offline do Pilar 4."""
from __future__ import annotations

from typing import Tuple

import numpy as np

from ouroboros.interfaces.renderer import IRenderer


class NullRenderer(IRenderer):
    """
    Implementacao nula de `IRenderer` para testes headless (Pilar 5) e
    para o pipeline offline do Pilar 4, que nunca deve depender de
    video real. Nenhum metodo produz efeito colateral de janela/GPU.
    """

    def __init__(self) -> None:
        self._width = 0
        self._height = 0
        self.begin_frame_count = 0
        self.end_frame_count = 0
        self.draw_batch_calls = []

    def initialize(self, width: int, height: int, title: str) -> None:
        self._width = width
        self._height = height

    def begin_frame(self) -> None:
        self.begin_frame_count += 1

    def draw_batch(
        self,
        positions_xy: np.ndarray,
        rotations_rad: np.ndarray,
        scales_xy: np.ndarray,
        texture_ids: np.ndarray,
        tint_rgba: np.ndarray,
        layer_z: np.ndarray,
        count: int,
    ) -> None:
        self.draw_batch_calls.append(count)

    def end_frame(self) -> None:
        self.end_frame_count += 1

    def get_viewport_size(self) -> Tuple[int, int]:
        return (self._width, self._height)

    def shutdown(self) -> None:
        pass
