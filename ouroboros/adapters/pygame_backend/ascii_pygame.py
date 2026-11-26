# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""O modo ASCII no pygame (ROADMAP M22): desenhar uma `TelaAscii` com fonte monoespacada e o
filtro que converte um quadro ja renderizado em caracteres.

Cada glifo (caractere + cor + tamanho) e renderizado uma vez e guardado; o quadro so faz
`fblits`. O fundo da tela ASCII sai numa superficie de uma celula por pixel ampliada por
vizinho mais proximo (um blit, nao um retangulo por celula). O filtro reduz a area por media
(`smoothscale`) para ter a cor de cada celula, monta uma `TelaAscii` reaproveitada com
`preencher_por_luminancia` e a desenha por cima.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pygame

from ouroboros.core.ascii import FiltroAscii, TelaAscii

FONTES_MONO = "consolas,dejavusansmono,menlo,liberationmono,couriernew,monospace"
_CACHE_GLIFOS_MAX = 12000


class DesenhistaAscii:
    """Fontes, glifos e superficies de trabalho do modo ASCII, reaproveitados entre quadros."""

    def __init__(self, cache_max: int = _CACHE_GLIFOS_MAX) -> None:
        self._cache_max = cache_max
        self._fontes: Dict[int, pygame.font.Font] = {}
        self._celulas: Dict[int, Tuple[int, int]] = {}
        self._glifos: Dict[int, Dict[int, pygame.Surface]] = {}
        self._fundos_peq: Dict[tuple, pygame.Surface] = {}
        self._fundos_grd: Dict[tuple, pygame.Surface] = {}
        self._amostras: Dict[tuple, pygame.Surface] = {}
        self._telas_filtro: Dict[tuple, TelaAscii] = {}
        self.ultima_tela_filtro: Optional[TelaAscii] = None  # para teste/inspecao

    # ------------------------------------------------------------ fonte

    def fonte(self, tamanho: int) -> pygame.font.Font:
        f = self._fontes.get(tamanho)
        if f is None:
            if not pygame.font.get_init():
                pygame.font.init()
            f = pygame.font.SysFont(FONTES_MONO, tamanho)
            self._fontes[tamanho] = f
        return f

    def celula(self, tamanho: int) -> Tuple[int, int]:
        c = self._celulas.get(tamanho)
        if c is None:
            f = self.fonte(tamanho)
            c = (max(1, f.size("M")[0]), max(1, f.get_height()))
            self._celulas[tamanho] = c
        return c

    def quantos_cabem(self, largura: int, altura: int, tamanho: int) -> Tuple[int, int]:
        cw, ch = self.celula(tamanho)
        return max(1, largura // cw), max(1, altura // ch)

    # ------------------------------------------------------------ desenhar

    def desenhar(self, alvo: pygame.Surface, tela: TelaAscii, x: float = 0.0, y: float = 0.0,
                 tamanho: int = 16) -> None:
        cw, ch = self.celula(tamanho)
        ox, oy = int(x), int(y)
        cols, rows = tela.colunas, tela.linhas
        if tela.fundos is not None:
            peq = self._fundos_peq.get((cols, rows))
            if peq is None:
                peq = pygame.Surface((cols, rows))
                self._fundos_peq[(cols, rows)] = peq
            pygame.surfarray.blit_array(peq, tela.fundos.transpose(1, 0, 2))
            tam = (cols * cw, rows * ch)
            grd = self._fundos_grd.get(tam)
            if grd is None:
                grd = pygame.Surface(tam)
                self._fundos_grd[tam] = grd
            pygame.transform.scale(peq, tam, grd)
            alvo.blit(grd, (ox, oy))
        car = tela.caracteres
        ys, xs = np.nonzero(car > 32)
        if ys.shape[0] == 0:
            return
        cores = tela.cores[ys, xs].astype(np.int64)
        chaves = ((car[ys, xs].astype(np.int64) << 24) | (cores[:, 0] << 16)
                  | (cores[:, 1] << 8) | cores[:, 2])
        glifos = self._glifos.get(tamanho)
        if glifos is None:
            glifos = {}
            self._glifos[tamanho] = glifos
        fonte = self.fonte(tamanho)
        lista = []
        anexar = lista.append
        for k, px, py in zip(chaves.tolist(), (xs * cw + ox).tolist(), (ys * ch + oy).tolist()):
            g = glifos.get(k)
            if g is None:
                if len(glifos) >= self._cache_max:
                    glifos.clear()
                g = fonte.render(chr(k >> 24), True, ((k >> 16) & 255, (k >> 8) & 255, k & 255))
                glifos[k] = g
            anexar((g, (px, py)))
        alvo.fblits(lista)

    # ------------------------------------------------------------ filtro

    def filtrar(self, alvo: pygame.Surface, filtro: FiltroAscii) -> None:
        """Converte `alvo` (ou `filtro.area` dele) em caracteres, no lugar."""
        cw, ch = self.celula(filtro.tamanho_fonte)
        larg, alt = alvo.get_size()
        ax, ay, aw, ah = filtro.area if filtro.area is not None else (0, 0, larg, alt)
        area = pygame.Rect(ax, ay, aw, ah).clip(alvo.get_rect())
        cols, rows = area.w // cw, area.h // ch
        if cols < 1 or rows < 1:
            return
        sub = alvo.subsurface((area.x, area.y, cols * cw, rows * ch))
        amostra = self._amostras.get((cols, rows, alvo.get_bitsize()))
        if amostra is None:
            amostra = pygame.Surface((cols, rows), 0, alvo)
            self._amostras[(cols, rows, alvo.get_bitsize())] = amostra
        pygame.transform.smoothscale(sub, (cols, rows), amostra)
        del sub
        com_fundo = filtro.fundo > 0.0
        tela = self._telas_filtro.get((cols, rows, com_fundo))
        if tela is None:
            tela = TelaAscii(cols, rows, fundo=(0, 0, 0) if com_fundo else None)
            self._telas_filtro[(cols, rows, com_fundo)] = tela
        rgb = pygame.surfarray.pixels3d(amostra)
        try:
            tela.preencher_por_luminancia(rgb.transpose(1, 0, 2), filtro.rampa, filtro.realce,
                                          filtro.fundo, filtro.niveis_cor)
        finally:
            del rgb  # destrava a superficie
        alvo.fill((0, 0, 0), area)
        self.desenhar(alvo, tela, area.x + (area.w - cols * cw) // 2, area.y + (area.h - rows * ch) // 2,
                      filtro.tamanho_fonte)
        self.ultima_tela_filtro = tela
