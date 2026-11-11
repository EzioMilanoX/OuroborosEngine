# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A cena da vitrine: a grade 3x2 com os seis estilos lado a lado, ou um estilo em tela
cheia (teclas 1-6; G volta para a grade; A/D passa de um para outro; ESC sai)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ouroboros.bootstrap.scene import IScene
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

from games.vitrine_estilos.arte import ALTURA, ESTILOS, FPS, LARGURA, NOMES

FPS_ANIMACAO = FPS
BRANCO = (240, 236, 230, 255)
SOMBRA = (0, 0, 0, 170)


class VitrineScene(IScene):
    def __init__(self, entrada: IInputProvider, texturas: Dict[str, List[int]],
                 ao_sair: Optional[Callable[[], None]] = None) -> None:
        self.entrada = entrada
        self.texturas = texturas
        self.ao_sair = ao_sair
        self.foco: Optional[int] = None  # None: a grade; senao, o indice do estilo
        self.relogio = 0.0

    def update(self, world: World, delta_time: float) -> None:
        self.relogio += delta_time
        e = self.entrada
        if e.is_action_pressed("sair") and self.ao_sair is not None:
            self.ao_sair()
            return
        for i in range(len(ESTILOS)):
            if e.is_action_pressed(f"estilo_{i + 1}"):
                self.foco = i
        if e.is_action_pressed("grade"):
            self.foco = None
        passo = int(e.is_action_pressed("proximo")) - int(e.is_action_pressed("anterior"))
        if passo:
            self.foco = ((self.foco if self.foco is not None else -1 if passo > 0 else 0) + passo) % len(ESTILOS)

    def quadro(self) -> int:
        return int(self.relogio * FPS_ANIMACAO)

    def render(self, world: World, renderer: IRenderer) -> None:
        if self.foco is None:
            self._grade(renderer)
        else:
            self._cheia(renderer, ESTILOS[self.foco], self.foco)

    def _rotulo(self, r: IRenderer, x: float, y: float, estilo: str, numero: int, tamanho: int) -> None:
        nome, desc = NOMES[estilo]
        r.draw_ui_rect(x, y, len(desc) * tamanho * 0.62 + 28, tamanho * 2.9, SOMBRA)
        r.draw_text(x + 12, y + 6, f"{numero}  {nome}", int(tamanho * 1.2), BRANCO)
        r.draw_text(x + 12, y + 6 + tamanho * 1.4, desc, tamanho, (200, 196, 190, 255))

    def _cheia(self, r: IRenderer, estilo: str, i: int) -> None:
        ids = self.texturas[estilo]
        r.draw_ui_image(ids[self.quadro() % len(ids)], 0, 0, anchor=(0.0, 0.0))
        self._rotulo(r, 16, 16, estilo, i + 1, 14)
        r.draw_text(LARGURA - 16, ALTURA - 26, "1-6 estilo  A/D troca  G grade  ESC sai", 13, BRANCO,
                    anchor="topright")

    def _grade(self, r: IRenderer) -> None:
        """3 colunas x 2 linhas: os seis estilos em 1/3 do tamanho; os comandos no rodape."""
        cw, ch = LARGURA / 3, ALTURA / 2
        r.draw_ui_rect(0, 0, LARGURA, ALTURA, (10, 9, 14, 255))
        for i, estilo in enumerate(ESTILOS):
            ids = self.texturas[estilo]
            x, y = (i % 3) * cw, (i // 3) * ch + (ch - ALTURA / 3) / 2
            r.draw_ui_image(ids[self.quadro() % len(ids)], x, y, anchor=(0.0, 0.0), scale=1 / 3)
            nome, _ = NOMES[estilo]
            r.draw_text(x + 8, (i // 3) * ch + 12, f"{i + 1}  {nome}", 14, BRANCO)
        r.draw_text(LARGURA / 2, ALTURA - 24, "a mesma cena, seis jeitos de pintar   |   1-6 abre um estilo   "
                    "A/D troca   G grade   ESC sai", 13, (200, 196, 190, 255), anchor="midtop")
