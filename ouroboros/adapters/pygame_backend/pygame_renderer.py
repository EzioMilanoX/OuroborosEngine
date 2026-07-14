"""Implementacao concreta de IRenderer sobre pygame (formas, alpha, texto)."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pygame

from ouroboros.interfaces.renderer import IRenderer, SHAPE_CIRCLE

_TEXT_CACHE_MAX = 512


class PygameRenderer(IRenderer):
    """
    Implementacao de `IRenderer` sobre `pygame.display`/`pygame.draw`.

    Nota honesta sobre "batch": `draw_batch` cruza a fronteira core->
    adapter em UMA UNICA chamada por frame (o que evita N chamadas
    Python de gameplay para o backend), mas internamente ainda emite um
    comando de desenho por sprite -- a API 2D por software do pygame
    nao expoe instanced/batched draw calls verdadeiros. Isso nao viola a
    Constituicao: a Regra 1 (Zero-GC) regula o loop de GAMEPLAY, nao o
    adapter de apresentacao.

    Formas (ROADMAP M1): sem pipeline de texturas ainda, `texture_ids`
    resolve formas primitivas (SHAPE_RECT/SHAPE_CIRCLE). `tint_rgba[3]`
    (alpha) e respeitado: sprites translucidos passam por uma superficie
    SRCALPHA temporaria (custo pago so por quem usa alpha).

    Texto (ROADMAP M2): `draw_text` cacheia fontes por tamanho e
    superficies por (texto, tamanho, cor), com teto de cache -- chamavel
    apenas da camada de cenas/UI, nunca de ISystem.update().
    """

    def __init__(self) -> None:
        self._surface = None
        self._width = 0
        self._height = 0
        self._cam_dx = 0.0
        self._cam_dy = 0.0
        self._fonts: Dict[int, pygame.font.Font] = {}
        self._text_cache: Dict[tuple, pygame.Surface] = {}

    def initialize(self, width: int, height: int, title: str) -> None:
        pygame.init()
        pygame.font.init()
        self._surface = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        self._width = width
        self._height = height

    def begin_frame(self) -> None:
        self._surface.fill((8, 8, 14))

    def set_camera_offset(self, dx: float, dy: float) -> None:
        self._cam_dx = dx
        self._cam_dy = dy

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
        surf = self._surface
        cam_dx, cam_dy = self._cam_dx, self._cam_dy
        for i in draw_order:
            i = int(i)
            x = float(positions_xy[i, 0]) + cam_dx
            y = float(positions_xy[i, 1]) + cam_dy
            width = max(1, int(8 * max(float(scales_xy[i, 0]), 0.01)))
            height = max(1, int(8 * max(float(scales_xy[i, 1]), 0.01)))
            r = int(tint_rgba[i, 0]); g = int(tint_rgba[i, 1])
            b = int(tint_rgba[i, 2]); a = int(tint_rgba[i, 3])
            if a <= 0:
                continue
            shape = int(texture_ids[i])
            if a >= 255:                              # opaco: direto
                if shape == SHAPE_CIRCLE:
                    pygame.draw.circle(surf, (r, g, b),
                                       (int(x), int(y)), max(1, width // 2))
                else:
                    pygame.draw.rect(surf, (r, g, b),
                                     (int(x - width / 2), int(y - height / 2),
                                      width, height))
            else:                                     # translucido
                tmp = pygame.Surface((width, height), pygame.SRCALPHA)
                if shape == SHAPE_CIRCLE:
                    pygame.draw.circle(tmp, (r, g, b, a),
                                       (width // 2, height // 2),
                                       max(1, width // 2))
                else:
                    tmp.fill((r, g, b, a))
                surf.blit(tmp, (int(x - width / 2), int(y - height / 2)))

    def draw_ui_rect(self, x: float, y: float, w: float, h: float,
                     rgba: Tuple[int, int, int, int]) -> None:
        if rgba[3] >= 255:
            pygame.draw.rect(self._surface, rgba[:3],
                             (int(x), int(y), int(w), int(h)))
            return
        tmp = pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)
        tmp.fill(rgba)
        self._surface.blit(tmp, (int(x), int(y)))

    def draw_text(self, x: float, y: float, text: str, size: int,
                  rgba: Tuple[int, int, int, int],
                  anchor: str = "topleft") -> None:
        if not text:
            return
        font = self._fonts.get(size)
        if font is None:
            font = pygame.font.SysFont("consolas", size, bold=True)
            self._fonts[size] = font
        key = (text, size, rgba[:3])
        rendered = self._text_cache.get(key)
        if rendered is None:
            if len(self._text_cache) >= _TEXT_CACHE_MAX:
                self._text_cache.clear()
            rendered = font.render(text, True, rgba[:3])
            self._text_cache[key] = rendered
        if rgba[3] < 255:
            rendered = rendered.copy()
            rendered.set_alpha(rgba[3])
        rect = rendered.get_rect()
        if anchor == "center":
            rect.center = (int(x), int(y))
        elif anchor == "topright":
            rect.topright = (int(x), int(y))
        else:
            rect.topleft = (int(x), int(y))
        self._surface.blit(rendered, rect)

    def end_frame(self) -> None:
        pygame.display.flip()

    def get_viewport_size(self) -> Tuple[int, int]:
        return (self._width, self._height)

    def shutdown(self) -> None:
        pygame.quit()
