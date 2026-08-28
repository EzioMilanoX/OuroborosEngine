# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao concreta de IRenderer sobre pygame (formas, alpha, texto)."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pygame

from ouroboros.interfaces.renderer import IRenderer, SHAPE_CIRCLE, SHAPE_RING

_TEXT_CACHE_MAX = 512
_TEXTURE_SCALE_CACHE_MAX = 512


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

    Formas (ROADMAP M1): sem pipeline de texturas ainda, `texture_ids`/
    `kinds` resolve formas primitivas (SHAPE_RECT/SHAPE_CIRCLE/SHAPE_RING)
    via `_draw_shape`, compartilhado por `draw_batch` (sprites) e
    `draw_effects` (pool `fx`). `tint_rgba[3]` (alpha) e respeitado:
    formas translucidas passam por uma superficie SRCALPHA temporaria
    (custo pago so por quem usa alpha).

    Texto (ROADMAP M2): `draw_text` cacheia fontes por tamanho e
    superficies por (texto, tamanho, cor), com teto de cache -- chamavel
    apenas da camada de cenas/UI, nunca de ISystem.update().

    Texturas (ROADMAP M3): `load_texture` cacheia a imagem crua por
    `texture_id`; `_draw_shape` resolve um `texture_id`/`kind` carregado
    ANTES de cair no fallback de forma primitiva. A superficie ESCALADA
    (por `(texture_id, width, height)`) tambem e cacheada, com o mesmo
    teto-e-limpa de `_text_cache` -- reescalar do zero em todo desenho,
    mesmo opaco/sem tint, seria um gargalo real na escala que o ROADMAP
    pede (milhares de sprites/frame).
    """

    def __init__(self) -> None:
        self._surface = None
        self._width = 0
        self._height = 0
        self._cam_dx = 0.0
        self._cam_dy = 0.0
        self._fonts: Dict[int, pygame.font.Font] = {}
        self._text_cache: Dict[tuple, pygame.Surface] = {}
        self._textures: Dict[int, pygame.Surface] = {}
        self._texture_scale_cache: Dict[tuple, pygame.Surface] = {}

    def initialize(self, width: int, height: int, title: str) -> None:
        pygame.init()
        pygame.font.init()
        self._surface = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        self._width = width
        self._height = height
        self._is_fullscreen = False

    def begin_frame(self) -> None:
        self._surface.fill((8, 8, 14))

    def load_texture(self, texture_id: int, file_path: str) -> None:
        self._textures[texture_id] = pygame.image.load(file_path).convert_alpha()

    def set_camera_offset(self, dx: float, dy: float) -> None:
        self._cam_dx = dx
        self._cam_dy = dy

    def set_fullscreen(self, enabled: bool) -> None:
        # FULLSCREEN sozinho troca a resolucao real pra nativa da tela (ex.:
        # 1024x768 sob o driver dummy mesmo pedindo 800x600) -- SCALED mantem
        # a resolucao logica (self._width/self._height) intacta nos dois
        # modos, escalando a apresentacao em vez de mudar get_viewport_size().
        flags = (pygame.FULLSCREEN | pygame.SCALED) if enabled else 0
        self._surface = pygame.display.set_mode((self._width, self._height), flags)
        self._is_fullscreen = enabled

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
        cam_dx, cam_dy = self._cam_dx, self._cam_dy
        for i in draw_order:
            i = int(i)
            x = float(positions_xy[i, 0]) + cam_dx
            y = float(positions_xy[i, 1]) + cam_dy
            width = max(1, int(8 * max(float(scales_xy[i, 0]), 0.01)))
            height = max(1, int(8 * max(float(scales_xy[i, 1]), 0.01)))
            self._draw_shape(
                int(texture_ids[i]), x, y, width, height,
                int(tint_rgba[i, 0]), int(tint_rgba[i, 1]), int(tint_rgba[i, 2]), int(tint_rgba[i, 3]),
            )

    def draw_effects(
        self,
        kinds: np.ndarray,
        positions_xy: np.ndarray,
        sizes_wh: np.ndarray,
        tint_rgba: np.ndarray,
        count: int,
    ) -> None:
        cam_dx, cam_dy = self._cam_dx, self._cam_dy
        for i in range(count):
            x = float(positions_xy[i, 0]) + cam_dx
            y = float(positions_xy[i, 1]) + cam_dy
            width = max(1, int(sizes_wh[i, 0]))
            height = max(1, int(sizes_wh[i, 1]))
            self._draw_shape(
                int(kinds[i]), x, y, width, height,
                int(tint_rgba[i, 0]), int(tint_rgba[i, 1]), int(tint_rgba[i, 2]), int(tint_rgba[i, 3]),
            )

    def _draw_shape(
        self, shape: int, x: float, y: float, width: int, height: int, r: int, g: int, b: int, a: int
    ) -> None:
        """Desenha UMA forma em `(x, y)` -- textura real se `shape` tiver uma
        carregada via `load_texture` (ROADMAP M3), senao a forma primitiva
        RECT/CIRCLE/RING (ROADMAP M1, fallback). Compartilhado por `draw_batch`
        e `draw_effects` (o mesmo leque de formas/texturas serve sprites e
        efeitos)."""
        if a <= 0:
            return
        texture = self._textures.get(shape)
        if texture is not None:
            self._draw_texture(shape, texture, x, y, width, height, r, g, b, a)
            return
        surf = self._surface
        if a >= 255:                              # opaco: direto
            if shape == SHAPE_CIRCLE:
                pygame.draw.circle(surf, (r, g, b), (int(x), int(y)), max(1, width // 2))
            elif shape == SHAPE_RING:
                radius = max(1, width // 2)
                thickness = max(2, radius // 6)
                pygame.draw.circle(surf, (r, g, b), (int(x), int(y)), radius, thickness)
            else:
                pygame.draw.rect(surf, (r, g, b),
                                 (int(x - width / 2), int(y - height / 2), width, height))
        else:                                     # translucido
            tmp = pygame.Surface((width, height), pygame.SRCALPHA)
            if shape == SHAPE_CIRCLE:
                pygame.draw.circle(tmp, (r, g, b, a), (width // 2, height // 2), max(1, width // 2))
            elif shape == SHAPE_RING:
                radius = max(1, width // 2)
                thickness = max(2, radius // 6)
                pygame.draw.circle(tmp, (r, g, b, a), (width // 2, height // 2), radius, thickness)
            else:
                tmp.fill((r, g, b, a))
            surf.blit(tmp, (int(x - width / 2), int(y - height / 2)))

    def _draw_texture(
        self, shape: int, texture: pygame.Surface, x: float, y: float,
        width: int, height: int, r: int, g: int, b: int, a: int,
    ) -> None:
        """Desenha a textura `texture` (ja carregada por `load_texture` sob `shape`)
        escalada para `width`/`height`, com tint/alpha. A superficie ESCALADA (sem
        tint/alpha aplicado) e cacheada por `(shape, width, height)` -- mesmo idioma
        de tamanho-limitado-e-limpa-quando-cheio de `_text_cache` em `draw_text` --
        e NUNCA mutada em si; tint/alpha sempre operam sobre uma `.copy()` fresca,
        so quando de fato precisam ajustar algo (sprite opaco/sem tint reusa a
        superficie cacheada direto, sem nenhuma copia)."""
        cache_key = (shape, width, height)
        scaled = self._texture_scale_cache.get(cache_key)
        if scaled is None:
            if len(self._texture_scale_cache) >= _TEXTURE_SCALE_CACHE_MAX:
                self._texture_scale_cache.clear()
            scaled = pygame.transform.scale(texture, (width, height))
            self._texture_scale_cache[cache_key] = scaled

        needs_tint = (r, g, b) != (255, 255, 255)
        needs_alpha = a < 255
        if needs_tint or needs_alpha:
            scaled = scaled.copy()
            if needs_tint:
                scaled.fill((r, g, b, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if needs_alpha:
                scaled.set_alpha(a)

        self._surface.blit(scaled, (int(x - width / 2), int(y - height / 2)))

    def draw_particles(
        self,
        positions_xy: np.ndarray,
        sizes: np.ndarray,
        tint_rgba: np.ndarray,
        count: int,
    ) -> None:
        """Desenha `count` particulas como circulos pequenos cheios, com blend
        ADITIVO (`pygame.BLEND_RGBA_ADD`) -- visualmente diferente do alpha-blend
        de `draw_batch`/`draw_effects`, tipico de faisca/explosao."""
        cam_dx, cam_dy = self._cam_dx, self._cam_dy
        surf = self._surface
        for i in range(count):
            a = int(tint_rgba[i, 3])
            if a <= 0:
                continue
            x = float(positions_xy[i, 0]) + cam_dx
            y = float(positions_xy[i, 1]) + cam_dy
            radius = max(1, int(sizes[i]) // 2)
            r, g, b = int(tint_rgba[i, 0]), int(tint_rgba[i, 1]), int(tint_rgba[i, 2])
            tmp = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(tmp, (r, g, b, a), (radius, radius), radius)
            surf.blit(tmp, (int(x - radius), int(y - radius)), special_flags=pygame.BLEND_RGBA_ADD)

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
