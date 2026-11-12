# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao concreta de IRenderer sobre pygame (formas, alpha, texto)."""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

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

    Texto (ROADMAP M2): `draw_text` cacheia fontes por (fonte, tamanho) e
    superficies por (texto, tamanho, cor, fonte), com teto de cache --
    chamavel apenas da camada de cenas/UI, nunca de ISystem.update().
    `load_font` (ROADMAP M16) so registra o caminho; o `pygame.font.Font`
    de cada tamanho e aberto no primeiro uso.

    Primitivas vetoriais de UI (ROADMAP M16): `draw_ui_line/circle/arc/
    polygon` desenham direto na tela quando opacas e passam por uma
    superficie SRCALPHA do tamanho da caixa da forma quando translucidas,
    o mesmo trato de `draw_ui_rect`. Usam antialiasing onde o pygame-ce
    oferece (linha fina, circulo, contorno de poligono).

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
        self._fonts: Dict[tuple, pygame.font.Font] = {}
        self._font_paths: Dict[int, str] = {}
        self._text_cache: Dict[tuple, pygame.Surface] = {}
        self._textures: Dict[int, pygame.Surface] = {}
        self._texture_scale_cache: Dict[tuple, pygame.Surface] = {}
        # Superficies de trabalho de `draw_field`, por tamanho. Um campo e
        # desenhado todo frame; aloca-las por chamada seria trocar o laco de
        # `draw_batch` por pressao de GC.
        self._field_masks: Dict[tuple, pygame.Surface] = {}
        self._field_surfaces: Dict[tuple, pygame.Surface] = {}

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
        # recarregar um id ja usado (ex.: uma foto nova no mesmo slot) invalida as versoes
        # escaladas/espelhadas guardadas da imagem antiga -- senao a tela mostra a velha para sempre
        self._texture_scale_cache = {k: v for k, v in self._texture_scale_cache.items()
                                     if not (k[0] == texture_id or (k[0] == "ui" and k[1] == texture_id))}

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

    def draw_field(
        self,
        rgb: np.ndarray,
        x: float,
        y: float,
        width: float,
        height: float,
        alpha: np.ndarray = None,
    ) -> None:
        """Um campo: cor interpolada, forma nao.

        `smoothscale` faz a bilinear da cor; a mascara de `alpha` sobe por
        `scale`, que e vizinho mais proximo -- e e essa diferenca que deixa a
        parede com aresta reta enquanto a luz sobre ela e lisa.

        As duas superficies de trabalho sao cacheadas por tamanho: um campo e
        desenhado todo frame, e alocar dois `Surface` por frame seria trocar o
        laco de `draw_batch` por pressao de GC.
        """
        target_w = max(1, int(width))
        target_h = max(1, int(height))
        left = int(float(x) + self._cam_dx)
        top = int(float(y) + self._cam_dy)

        colour = pygame.transform.smoothscale(
            pygame.surfarray.make_surface(rgb), (target_w, target_h))
        if alpha is None:
            self._surface.blit(colour, (left, top))
            return

        small = self._field_mask(alpha.shape)
        view = pygame.surfarray.pixels_alpha(small)
        view[:] = alpha
        del view                                  # `pixels_alpha` tranca a surface
        mask = pygame.transform.scale(small, (target_w, target_h))

        field = self._field_surface(target_w, target_h)
        field.fill((0, 0, 0, 0))
        field.blit(colour, (0, 0))
        target = pygame.surfarray.pixels_alpha(field)
        source = pygame.surfarray.pixels_alpha(mask)
        target[:] = source
        del target, source
        self._surface.blit(field, (left, top))

    def _field_mask(self, shape) -> pygame.Surface:
        cols, rows = int(shape[0]), int(shape[1])
        cached = self._field_masks.get((cols, rows))
        if cached is None:
            cached = pygame.Surface((cols, rows), pygame.SRCALPHA)
            self._field_masks[(cols, rows)] = cached
        return cached

    def _field_surface(self, width: int, height: int) -> pygame.Surface:
        cached = self._field_surfaces.get((width, height))
        if cached is None:
            cached = pygame.Surface((width, height), pygame.SRCALPHA)
            self._field_surfaces[(width, height)] = cached
        return cached

    def draw_ui_rect(self, x: float, y: float, w: float, h: float,
                     rgba: Tuple[int, int, int, int]) -> None:
        if rgba[3] >= 255:
            pygame.draw.rect(self._surface, rgba[:3],
                             (int(x), int(y), int(w), int(h)))
            return
        tmp = pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)
        tmp.fill(rgba)
        self._surface.blit(tmp, (int(x), int(y)))

    def load_font(self, font_id: int, file_path: str) -> None:
        # O pygame-ce aceita abrir um arquivo que nao e fonte e so falha no
        # primeiro render; renderizar aqui faz o erro aparecer no carregamento.
        pygame.font.Font(file_path, 12).render("A", True, (0, 0, 0))
        self._font_paths[font_id] = file_path
        self._fonts = {k: f for k, f in self._fonts.items() if k[0] != font_id}
        self._text_cache = {k: s for k, s in self._text_cache.items() if k[3] != font_id}

    def _font(self, font_id: Optional[int], size: int) -> pygame.font.Font:
        if font_id not in self._font_paths:
            font_id = None  # id nunca carregado: fonte padrao, como em load_texture
        font = self._fonts.get((font_id, size))
        if font is None:
            if font_id is None:
                font = pygame.font.SysFont("consolas", size, bold=True)
            else:
                font = pygame.font.Font(self._font_paths[font_id], size)
            self._fonts[(font_id, size)] = font
        return font

    def draw_text(self, x: float, y: float, text: str, size: int,
                  rgba: Tuple[int, int, int, int],
                  anchor: str = "topleft",
                  font_id: Optional[int] = None) -> None:
        if not text:
            return
        if font_id not in self._font_paths:
            font_id = None
        font = self._font(font_id, size)
        key = (text, size, rgba[:3], font_id)
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

    def _ui_target(self, rgba, left: float, top: float, right: float, bottom: float):
        """Superficie onde desenhar uma primitiva de UI e o deslocamento a
        subtrair das coordenadas. Opaca: a propria tela, sem deslocamento.
        Translucida: uma SRCALPHA do tamanho da caixa, composta por
        `_ui_commit`."""
        if rgba[3] >= 255:
            return self._surface, 0, 0
        ox, oy = int(math.floor(left)) - 1, int(math.floor(top)) - 1
        w = int(math.ceil(right)) - ox + 2
        h = int(math.ceil(bottom)) - oy + 2
        return pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA), ox, oy

    def _ui_commit(self, target: pygame.Surface, ox: int, oy: int) -> None:
        if target is not self._surface:
            self._surface.blit(target, (ox, oy))

    def draw_ui_line(self, x1: float, y1: float, x2: float, y2: float,
                     rgba: Tuple[int, int, int, int], width: int = 1) -> None:
        pad = width / 2
        target, ox, oy = self._ui_target(rgba, min(x1, x2) - pad, min(y1, y2) - pad,
                                         max(x1, x2) + pad, max(y1, y2) + pad)
        a, b = (x1 - ox, y1 - oy), (x2 - ox, y2 - oy)
        if width <= 1:
            pygame.draw.aaline(target, rgba, a, b)
        else:
            pygame.draw.line(target, rgba, a, b, width)
        self._ui_commit(target, ox, oy)

    def draw_ui_circle(self, x: float, y: float, radius: float,
                       rgba: Tuple[int, int, int, int], width: int = 0) -> None:
        if radius <= 0:
            return
        target, ox, oy = self._ui_target(rgba, x - radius, y - radius, x + radius, y + radius)
        aacircle = getattr(pygame.draw, "aacircle", pygame.draw.circle)
        aacircle(target, rgba, (x - ox, y - oy), radius, width)
        self._ui_commit(target, ox, oy)

    def draw_ui_arc(self, x: float, y: float, radius: float,
                    start_rad: float, end_rad: float,
                    rgba: Tuple[int, int, int, int], width: int = 1) -> None:
        if radius <= 0:
            return
        target, ox, oy = self._ui_target(rgba, x - radius, y - radius, x + radius, y + radius)
        rect = pygame.Rect(0, 0, int(radius * 2), int(radius * 2))
        rect.center = (round(x - ox), round(y - oy))
        pygame.draw.arc(target, rgba, rect, start_rad, end_rad, max(1, width))
        self._ui_commit(target, ox, oy)

    def draw_ui_polygon(self, points: Sequence[Tuple[float, float]],
                        rgba: Tuple[int, int, int, int], width: int = 0) -> None:
        if len(points) < 3:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        target, ox, oy = self._ui_target(rgba, min(xs), min(ys), max(xs), max(ys))
        local = [(px - ox, py - oy) for px, py in points]
        if width == 0:
            pygame.draw.polygon(target, rgba, local)
            pygame.draw.aalines(target, rgba, True, local)  # borda lisa
        elif width == 1:
            pygame.draw.aalines(target, rgba, True, local)
        else:
            pygame.draw.polygon(target, rgba, local, width)
        self._ui_commit(target, ox, oy)

    def draw_ui_image(self, texture_id: int, x: float, y: float, *,
                      anchor: Tuple[float, float] = (0.5, 0.5), flip_x: bool = False,
                      alpha: int = 255, scale: float = 1.0) -> None:
        base = self._textures.get(texture_id)
        if base is None or alpha <= 0:
            return
        chave = ("ui", texture_id, flip_x, round(scale, 3))
        img = self._texture_scale_cache.get(chave)
        if img is None:  # espelhar e escalar uma vez so por variacao
            img = base
            if scale != 1.0:
                w = max(1, int(round(base.get_width() * scale)))
                h = max(1, int(round(base.get_height() * scale)))
                img = pygame.transform.smoothscale(img, (w, h))
            if flip_x:
                img = pygame.transform.flip(img, True, False)
            self._texture_scale_cache[chave] = img
        px = int(round(x - img.get_width() * anchor[0]))
        py = int(round(y - img.get_height() * anchor[1]))
        if alpha >= 255:
            self._surface.blit(img, (px, py))
        else:
            tmp = img.copy()
            tmp.set_alpha(int(alpha))
            self._surface.blit(tmp, (px, py))

    def end_frame(self) -> None:
        pygame.display.flip()

    def get_viewport_size(self) -> Tuple[int, int]:
        return (self._width, self._height)

    def shutdown(self) -> None:
        pygame.quit()
