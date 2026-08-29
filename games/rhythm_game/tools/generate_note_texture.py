"""
Gera a textura real de nota do Jogo Musical (ROADMAP M11.3): um PNG
original (desenhado por numpy/pygame, sem risco de direito autoral) --
um disco branco com falloff radial suave de alpha (RGB quase-branco de
proposito: `PygameRenderer._draw_texture` aplica o tint por-nota via
`BLEND_RGBA_MULT`, que so reproduz a cor exata quando a base e branca --
ver docstring do metodo).

Roda uma vez (resultado vai commitado); nao faz parte do jogo em si.
Uso: `python games/rhythm_game/tools/generate_note_texture.py` (script
solto, nao importa nada de `games.rhythm_game.*`).
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame

SIZE = 64
FALLOFF_EXPONENT = 1.6
"""Expoente do falloff radial -- >1 concentra o alpha mais perto do
centro (disco com borda mais definida em vez de uma mancha difusa)."""

_TOOLS_DIR = Path(__file__).resolve().parent
_GAME_DIR = _TOOLS_DIR.parent
TEXTURE_OUTPUT_PATH = _GAME_DIR / "assets" / "textures" / "note.png"


def _build_note_surface() -> pygame.Surface:
    surface = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    center = (SIZE - 1) / 2.0
    radius = SIZE / 2.0

    row, col = np.mgrid[0:SIZE, 0:SIZE]
    distance = np.sqrt((col - center) ** 2 + (row - center) ** 2)
    normalized = np.clip(1.0 - distance / radius, 0.0, 1.0)
    alpha = (normalized ** FALLOFF_EXPONENT * 255.0).astype(np.uint8)

    # pygame.surfarray usa eixos (x, y) -- transpoe a grade (row=y, col=x) pra bater.
    rgb = np.full((SIZE, SIZE, 3), 255, dtype=np.uint8)
    pygame.surfarray.pixels3d(surface)[:, :, :] = rgb.transpose(1, 0, 2)
    pygame.surfarray.pixels_alpha(surface)[:, :] = alpha.T
    return surface


def main() -> int:
    pygame.init()
    surface = _build_note_surface()
    TEXTURE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(TEXTURE_OUTPUT_PATH))
    print(f"Textura de nota sintetizada: {TEXTURE_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
