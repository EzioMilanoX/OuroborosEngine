# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contrato de renderizacao 3D (ROADMAP M21). Implementacoes concretas vivem em
ouroboros.adapters (hoje `gl_backend`, ModernGL/OpenGL 3.3).

Um "servidor de render 3D" separado do `IRenderer` 2D, como no estudo da Fase 9: o jogo
cria MALHAS (triangulos com cor por vertice) uma vez, e a cada quadro define camera, luz
e estilo e pede `desenhar(malha, modelo)`. A luz e calculada por vertice (como o PS1 e as
GPUs antigas): hemisferica (ceu/chao) mais ate `MAX_LUZES` luzes direcionais, pontuais ou
foco. O `Estilo3D` decide a apresentacao: resolucao interna, tremor de vertice, modo de
cor (Gouraud, afim ou chapado), neblina, bits de cor com pontilhado, grao e vinheta -- o
mesmo pipeline faz low poly limpo ou terror de PS1.

O 2D continua no `IRenderer`: um backend com 3D devolve este contrato em
`IRenderer.renderer_3d()` e desenha a UI 2D por cima do 3D.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

MAX_LUZES = 8
Vec3 = Tuple[float, float, float]

COR_GOURAUD = 0  # cor interpolada com correcao de perspectiva (o padrao das GPUs)
COR_AFIM = 1  # interpolada na tela, sem correcao (o PS1: a cor "escorrega" em faces grandes)
COR_CHAPADA = 2  # uma cor por face (o low poly classico)


@dataclass(frozen=True)
class Luz3D:
    """`tipo`: "dir" (`vetor` = direcao PARA a luz), "ponto" (`vetor` = posicao) ou "foco"
    (`vetor` = posicao, `direcao` = para onde aponta, `cone` = (cos da borda, cos do miolo)).
    `cor` em 0..1, pode passar de 1 (intensidade). `alcance`: onde a luz pontual/foco zera."""

    tipo: str
    vetor: Vec3
    cor: Vec3
    alcance: float = 10.0
    direcao: Vec3 = (0.0, 0.0, -1.0)
    cone: Tuple[float, float] = (0.9, 0.97)


@dataclass(frozen=True)
class Iluminacao3D:
    ceu: Vec3 = (0.35, 0.35, 0.4)  # luz que vem de cima (normais para cima)
    solo: Vec3 = (0.15, 0.15, 0.15)  # luz que vem de baixo
    luzes: Sequence[Luz3D] = field(default_factory=tuple)


@dataclass(frozen=True)
class Estilo3D:
    resolucao: Optional[Tuple[int, int]] = None  # None: a da janela; senao, ampliada sem suavizar
    tremor: bool = False  # vertices grudados no pixel inteiro da resolucao interna
    modo_cor: int = COR_GOURAUD
    fundo: Vec3 = (0.03, 0.03, 0.05)  # cor de limpar (0..1)
    neblina_cor: Vec3 = (0.03, 0.03, 0.05)
    neblina: Tuple[float, float] = (1e6, 1e6 + 1)  # (comeca, cobre tudo), na profundidade da camera
    neblina_max: float = 1.0
    bits_cor: int = 0  # 0: sem quantizar; 5: 15 bits (o PS1)
    pontilhado: bool = False  # Bayer 4x4 antes de quantizar
    grao: float = 0.0  # amplitude do ruido, 0..1
    vinheta: float = 0.0  # 0: nenhuma; 0.5: escurece bem as bordas
    vhs: float = 0.0  # fita VHS, 0..1: cores desalinhadas, linhas tremidas, faixa de tracking, menos cor
    espelhar: bool = False  # a imagem 3D sai espelhada na horizontal (a UI 2D nao)


class IRenderer3D(ABC):
    """Contrato de render 3D. Posicoes em coordenadas de mundo (y para cima); triangulos
    sem indices (3 vertices seguidos por triangulo), virados para fora (anti-horario visto
    de fora) -- faces de costas sao descartadas."""

    @abstractmethod
    def criar_malha(self, posicoes: np.ndarray, cores: np.ndarray, emissivo: Optional[np.ndarray] = None,
                    dinamica: bool = False) -> int:
        """`posicoes` (V, 3) com V multiplo de 3; `cores` (V, 3) em 0..255; `emissivo` (V,)
        bool (ignora luz e neblina). `dinamica`: vai mudar com `atualizar_malha` todo quadro.
        Devolve o id da malha."""

    @abstractmethod
    def atualizar_malha(self, malha_id: int, posicoes: np.ndarray, cores: np.ndarray,
                        emissivo: Optional[np.ndarray] = None) -> None:
        """Troca o conteudo da malha (ex.: um personagem animado)."""

    @abstractmethod
    def remover_malha(self, malha_id: int) -> None: ...

    @abstractmethod
    def definir_camera(self, posicao: Vec3, alvo: Vec3, fov_vertical_graus: float = 60.0,
                       perto: float = 0.1, longe: float = 200.0) -> None: ...

    @abstractmethod
    def definir_iluminacao(self, iluminacao: Iluminacao3D) -> None: ...

    @abstractmethod
    def definir_estilo(self, estilo: Estilo3D) -> None: ...

    @abstractmethod
    def desenhar(self, malha_id: int, modelo: Optional[np.ndarray] = None) -> None:
        """Desenha a malha neste quadro. `modelo`: matriz 4x4 (rotacao + translacao) do
        objeto; None = identidade."""

    def ler_pixels(self) -> Optional[np.ndarray]:
        """O que ja foi desenhado neste quadro 3D (antes de compor), (altura, largura, 3)
        uint8, de cima para baixo -- uma "foto" do jogo. Backend que nao sabe: None."""
        return None


def translacao_e_giro_y(x: float, y: float, z: float, giro: float = 0.0) -> np.ndarray:
    """Matriz de modelo: gira `giro` radianos em volta do eixo y e leva para (x, y, z)."""
    c, s = float(np.cos(giro)), float(np.sin(giro))
    return np.array([[c, 0, s, x], [0, 1, 0, y], [-s, 0, c, z], [0, 0, 0, 1]], dtype=np.float32)


def triangulos_para_arrays(tris: List[tuple]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """De uma lista de (v0, v1, v2, cor, emissivo, ...) para os arrays de `criar_malha`."""
    pos = np.array([t[:3] for t in tris], dtype=np.float32).reshape(-1, 3)
    cores = np.repeat(np.array([t[3] for t in tris], dtype=np.float32), 3, axis=0)
    emiss = np.repeat(np.array([bool(t[4]) for t in tris]), 3)
    return pos, cores, emiss
