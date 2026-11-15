# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A cena da vitrine: a grade com os estilos de uma cena lado a lado (3x2 para o espadachim,
3x2 tambem para os tons de Biogenia), ou um estilo em tela cheia (teclas 1-6; G volta para a grade;
A/D passa de um para outro; C troca de cena; ESC sai)."""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from games.vitrine_estilos import biogenia
from games.vitrine_estilos.arte import ALTURA, ESTILOS, FPS, LARGURA, NOMES
from ouroboros.bootstrap.scene import IScene
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

# (titulo, estilos): cada cena e a mesma imagem pintada de varios jeitos
CENAS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("a mesma cena, seis jeitos de pintar", ESTILOS),
    ("Biogenia (GAM-13): o fim do Cretaceo em seis tons", biogenia.ESTILOS),
)
TODOS_OS_NOMES = {**NOMES, **biogenia.NOMES}

FPS_ANIMACAO = FPS
BRANCO = (240, 236, 230, 255)
SOMBRA = (0, 0, 0, 170)


class VitrineScene(IScene):
    def __init__(self, entrada: IInputProvider, texturas: Dict[str, List[int]],
                 ao_sair: Optional[Callable[[], None]] = None, cena: int = 0) -> None:
        self.entrada = entrada
        self.cena = cena  # o indice em CENAS
        self.texturas = texturas
        self.ao_sair = ao_sair
        self.foco: Optional[int] = None  # None: a grade; senao, o indice do estilo
        self.relogio = 0.0

    @property
    def estilos(self) -> Tuple[str, ...]:
        return CENAS[self.cena][1]

    def update(self, world: World, delta_time: float) -> None:
        self.relogio += delta_time
        e = self.entrada
        if e.is_action_pressed("sair") and self.ao_sair is not None:
            self.ao_sair()
            return
        if e.is_action_pressed("cena"):
            self.cena, self.foco = (self.cena + 1) % len(CENAS), None
        for i in range(len(self.estilos)):
            if e.is_action_pressed(f"estilo_{i + 1}"):
                self.foco = i
        if e.is_action_pressed("grade"):
            self.foco = None
        passo = int(e.is_action_pressed("proximo")) - int(e.is_action_pressed("anterior"))
        if passo:
            n = len(self.estilos)
            self.foco = ((self.foco if self.foco is not None else -1 if passo > 0 else 0) + passo) % n

    def quadro(self) -> int:
        return int(self.relogio * FPS_ANIMACAO)

    def render(self, world: World, renderer: IRenderer) -> None:
        if self.foco is None:
            self._grade(renderer)
        else:
            self._cheia(renderer, self.estilos[self.foco], self.foco)

    def _rotulo(self, r: IRenderer, x: float, y: float, estilo: str, numero: int, tamanho: int) -> None:
        nome, desc = TODOS_OS_NOMES[estilo]
        r.draw_ui_rect(x, y, len(desc) * tamanho * 0.62 + 28, tamanho * 2.9, SOMBRA)
        r.draw_text(x + 12, y + 6, f"{numero}  {nome}", int(tamanho * 1.2), BRANCO)
        r.draw_text(x + 12, y + 6 + tamanho * 1.4, desc, tamanho, (200, 196, 190, 255))

    def _cheia(self, r: IRenderer, estilo: str, i: int) -> None:
        ids = self.texturas[estilo]
        r.draw_ui_image(ids[self.quadro() % len(ids)], 0, 0, anchor=(0.0, 0.0))
        self._rotulo(r, 16, 16, estilo, i + 1, 14)
        r.draw_text(LARGURA - 16, ALTURA - 26, "1-6 estilo  A/D troca  G grade  C cena  ESC sai", 13, BRANCO,
                    anchor="topright")

    def _grade(self, r: IRenderer) -> None:
        """3 colunas para seis estilos, 2 para quatro; cada um reduzido para caber na sua celula."""
        titulo, estilos = CENAS[self.cena]
        colunas = 3 if len(estilos) > 4 else 2
        linhas = math.ceil(len(estilos) / colunas)
        cw, ch, k = LARGURA / colunas, ALTURA / linhas, 1 / colunas
        r.draw_ui_rect(0, 0, LARGURA, ALTURA, (10, 9, 14, 255))
        for i, estilo in enumerate(estilos):
            ids = self.texturas[estilo]
            x, y = (i % colunas) * cw, (i // colunas) * ch + (ch - ALTURA * k) / 2
            r.draw_ui_image(ids[self.quadro() % len(ids)], x, y, anchor=(0.0, 0.0), scale=k)
            nome, _ = TODOS_OS_NOMES[estilo]
            r.draw_text(x + 8, (i // colunas) * ch + 12, f"{i + 1}  {nome}", 14, BRANCO)
        r.draw_ui_rect(0, ALTURA - 26, LARGURA, 26, SOMBRA)
        r.draw_text(LARGURA / 2, ALTURA - 13, f"{titulo}  |  1-{len(estilos)} abre  A/D troca  C outra cena  ESC sai",
                    13, (200, 196, 190, 255), anchor="center")
