"""Implementacao concreta de IRenderer sobre pygame. Detalhamento fica para a fase de implementacao do Pilar 2."""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pygame

from ouroboros.interfaces.renderer import IRenderer


class PygameRenderer(IRenderer):
    """
    Implementacao de `IRenderer` sobre `pygame.display`/`pygame.draw`.

    Nota honesta sobre "batch": `draw_batch` cruza a fronteira core->
    adapter em UMA UNICA chamada por frame (o que evita N chamadas
    Python de gameplay para o backend), mas internamente ainda emite um
    comando de desenho por sprite -- a API 2D por software do pygame
    (`pygame.draw`/`Surface.blit`) nao expoe instanced/batched draw
    calls verdadeiros. Isso nao viola a Constituicao: a Regra 1 (Zero-GC)
    regula o loop de GAMEPLAY (`ouroboros.core`/`roguelite`/`rhythm`),
    nao o adapter de apresentacao.

    Esta implementacao ainda nao tem pipeline de texturas/assets (fora
    do escopo dos 5 pilares iniciais): `texture_ids` e usado apenas
    como semente deterministica de cor de placeholder, para que sprites
    diferentes sejam visualmente distinguiveis antes de haver um
    carregador de imagens real.
    """

    def __init__(self) -> None:
        self._surface = None
        self._width = 0
        self._height = 0

    def initialize(self, width: int, height: int, title: str) -> None:
        pygame.init()
        self._surface = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        self._width = width
        self._height = height

    def begin_frame(self) -> None:
        self._surface.fill((0, 0, 0))

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
        if count == 0:
            return
        draw_order = np.argsort(layer_z[:count], kind="stable")
        for i in draw_order:
            i = int(i)
            x, y = float(positions_xy[i, 0]), float(positions_xy[i, 1])
            scale_x, scale_y = float(scales_xy[i, 0]), float(scales_xy[i, 1])
            width = max(1, int(8 * max(scale_x, 0.01)))
            height = max(1, int(8 * max(scale_y, 0.01)))
            color = (int(tint_rgba[i, 0]), int(tint_rgba[i, 1]), int(tint_rgba[i, 2]))
            rect = pygame.Rect(int(x - width / 2), int(y - height / 2), width, height)
            pygame.draw.rect(self._surface, color, rect)

    def end_frame(self) -> None:
        pygame.display.flip()

    def get_viewport_size(self) -> Tuple[int, int]:
        return (self._width, self._height)

    def shutdown(self) -> None:
        pygame.quit()
