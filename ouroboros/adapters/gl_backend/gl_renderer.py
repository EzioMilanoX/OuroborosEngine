# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`GLRenderer` (ROADMAP M21): o `IRenderer` com placa de video.

A janela e do pygame (com OpenGL), a entrada continua no `PygameInputProvider` e todas as
primitivas 2D do `PygameRenderer` continuam valendo: elas sao desenhadas numa camada
transparente que vai para a GPU como textura e e composta POR CIMA do 3D. O 3D e o
`ModernGLRenderer3D`, devolvido em `renderer_3d()`.

Escolhido no `EngineConfig` com `"renderer": "gl"`; precisa de `pip install moderngl`
(o extra `gl` do pacote) e de OpenGL 3.3.
"""
from __future__ import annotations

import moderngl
import pygame

from ouroboros.adapters.gl_backend.gl_renderer3d import ModernGLRenderer3D
from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.interfaces.renderer3d import IRenderer3D

FUNDO = (8 / 255, 8 / 255, 14 / 255)


class GLRenderer(PygameRenderer):
    def initialize(self, width: int, height: int, title: str) -> None:
        pygame.init()
        pygame.font.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.display.set_caption(title)
        self._width, self._height = width, height
        self._is_fullscreen = False
        self._ctx = moderngl.create_context()
        self._surface = pygame.Surface((width, height), pygame.SRCALPHA)  # a camada da UI 2D
        self._r3d = ModernGLRenderer3D(self._ctx, width, height)
        self._tex_ui = self._ctx.texture((width, height), 4)
        self._tex_ui.filter = (moderngl.NEAREST, moderngl.NEAREST)

    def renderer_3d(self) -> IRenderer3D:
        return self._r3d

    def begin_frame(self) -> None:
        self._surface.fill((0, 0, 0, 0))

    def _area(self):
        """Onde a imagem cabe na janela sem distorcer (tarjas pretas no que sobra)."""
        ww, wh = pygame.display.get_window_size()
        k = min(ww / self._width, wh / self._height)
        vw, vh = int(self._width * k), int(self._height * k)
        return ww, wh, ((ww - vw) // 2, (wh - vh) // 2, vw, vh)

    def end_frame(self) -> None:
        tela = self._ctx.screen
        ww, wh, area = self._area()
        if area[2:] != (ww, wh):
            tela.viewport = (0, 0, ww, wh)
            tela.use()
            tela.clear(0.0, 0.0, 0.0, 1.0)
        tela.viewport = area
        tela.use()
        if self._r3d.desenhou:
            self._r3d.compor(tela)
        else:
            tela.clear(*FUNDO, 1.0, viewport=area)
        self._tex_ui.write(pygame.image.tobytes(self._surface, "RGBA", True))
        self._r3d.compor_textura(self._tex_ui)
        pygame.display.flip()

    def set_fullscreen(self, enabled: bool) -> None:
        """Alterna a tela cheia sem recriar o contexto GL (o SDL so troca o modo da
        janela); a imagem e ampliada mantendo a proporcao, com tarjas pretas."""
        if enabled != self._is_fullscreen:
            pygame.display.toggle_fullscreen()
            self._is_fullscreen = enabled

    def shutdown(self) -> None:
        self._r3d.liberar()
        self._tex_ui.release()
        pygame.quit()
