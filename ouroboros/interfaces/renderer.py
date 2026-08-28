# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contrato de renderizacao (IRenderer). Implementacoes concretas vivem em ouroboros.adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

import numpy as np

# Formas primitivas resolvidas por `texture_ids` enquanto nao ha pipeline
# de texturas (ROADMAP M3): o backend concreto desenha a forma; ids acima
# de SHAPE_MAX ficam reservados para texturas reais no futuro.
SHAPE_RECT = 0
SHAPE_CIRCLE = 1
SHAPE_RING = 2
SHAPE_MAX = 15


class IRenderer(ABC):
    """
    Contrato de renderizacao. Implementacoes concretas vivem
    exclusivamente em `ouroboros.adapters.*` (ex.: `PygameRenderer`,
    um futuro `GodotRenderer`); nucleo/roguelite/rhythm conhecem apenas
    esta ABC -- nunca um tipo concreto de backend.
    """

    @abstractmethod
    def initialize(self, width: int, height: int, title: str) -> None:
        """Inicializa a janela/contexto grafico do backend concreto. Chamado uma vez, fora do loop de gameplay."""
        ...

    @abstractmethod
    def begin_frame(self) -> None:
        """Prepara o backend para receber comandos de desenho do frame atual (ex.: limpar o back-buffer)."""
        ...

    @abstractmethod
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
        """
        Desenha `count` sprites a partir de arrays SoA CRUS.

        Args:
            positions_xy: shape (N, 2) float32, coordenadas de mundo.
            rotations_rad: shape (N,) float32.
            scales_xy: shape (N, 2) float32.
            texture_ids: shape (N,) inteiro, resolvido pelo backend
                concreto para seu proprio recurso grafico ja carregado
                (o nucleo nao sabe "o que" e uma textura).
            tint_rgba: shape (N, 4) uint8.
            layer_z: shape (N,) inteiro, ordem de desenho.
            count: numero de entradas VALIDAS nos arrays acima (que
                podem ter capacidade maior que `count`, pois normalmente
                sao views de `ComponentPool.active_view()`).

        Invariante: todos os arrays sao paralelos (mesma ordem de
        linhas) e devem ser passados como VIEWS das pools do Pilar 1,
        nunca copias novas montadas a cada frame nem objetos de jogo
        concretos (Entity, Enemy, ...). Este e o UNICO metodo de
        desenho -- nao existe uma variante "desenhar uma entidade" que
        incentivaria um laco Python por entidade no chamador.
        """
        ...

    @abstractmethod
    def end_frame(self) -> None:
        """Apresenta o frame renderizado (flip/present) e sincroniza com vsync, se aplicavel."""
        ...

    @abstractmethod
    def load_texture(self, texture_id: int, file_path: str) -> None:
        """Pre-carrega e cacheia a imagem `file_path` sob o inteiro `texture_id`
        (tipicamente `ouroboros.core.stable_id.stable_id_from_name` de um nome
        amigavel, resolvido por um manifesto de assets -- ROADMAP M3), fora do
        loop de gameplay. Espelha `IAudioEngine.load_sound`: capacidade central
        que todo backend precisa implementar (nao uma extra opcional tipo
        `draw_text`). `texture_id` passa a ser resolvivel por `draw_batch`/
        `draw_effects` -- um `texture_id`/`kind` nunca carregado continua
        caindo no fallback de forma primitiva (SHAPE_RECT/CIRCLE/RING)."""
        ...

    # ------------------------------------------------------------------
    # Camada de APRESENTACAO (ROADMAP M1/M2): metodos NAO-abstratos com
    # default no-op — backends que nao os suportam continuam validos
    # (NullRenderer herda os no-ops). Sao chamados pela camada de cenas/
    # UI, NUNCA de dentro de ISystem.update(): texto e overlays podem
    # alocar (cache no adapter), o que a Constituicao proibe no gameplay.
    # ------------------------------------------------------------------

    def draw_text(self, x: float, y: float, text: str, size: int,
                  rgba: Tuple[int, int, int, int],
                  anchor: str = "topleft") -> None:
        """Desenha texto em coordenadas de TELA (ignora camera offset).
        `anchor`: topleft | center | topright. Default: no-op."""

    def draw_ui_rect(self, x: float, y: float, w: float, h: float,
                     rgba: Tuple[int, int, int, int]) -> None:
        """Retangulo de UI/overlay com alpha, em coordenadas de tela
        (paineis de menu, telegraphs, escurecimento). Default: no-op."""

    def set_camera_offset(self, dx: float, dy: float) -> None:
        """Deslocamento aplicado as posicoes de draw_batch (screen shake).
        Nao afeta draw_text/draw_ui_rect. Default: no-op."""

    def draw_effects(
        self,
        kinds: np.ndarray,
        positions_xy: np.ndarray,
        sizes_wh: np.ndarray,
        tint_rgba: np.ndarray,
        count: int,
    ) -> None:
        """
        Desenha `count` efeitos visuais (pool `fx` do nucleo -- ROADMAP
        M1.3) a partir de arrays SoA CRUS, mesmo espirito de
        `draw_batch` mas sem rotacao/camada de desenho (o dtype `fx`
        nao tem esses campos -- desenha na ordem da pool).

        Args:
            kinds: shape (N,) inteiro, mesma familia de `texture_ids`
                de `draw_batch` (SHAPE_RECT/SHAPE_CIRCLE/SHAPE_RING).
            positions_xy: shape (N, 2) float32, coordenadas de mundo.
            sizes_wh: shape (N, 2) float32, largura/altura.
            tint_rgba: shape (N, 4) uint8.
            count: numero de entradas validas nos arrays acima.

        Default: no-op (backends que nao suportam fx continuam validos).
        """

    def draw_particles(
        self,
        positions_xy: np.ndarray,
        sizes: np.ndarray,
        tint_rgba: np.ndarray,
        count: int,
    ) -> None:
        """
        Desenha `count` particulas (`ouroboros.core.particle_storage.ParticleStorage`
        -- ROADMAP M3) a partir de arrays SoA CRUS, com blend ADITIVO -- visualmente
        diferente de `draw_batch`/`draw_effects` (alpha-blend), tipico de faisca/
        explosao. Sem `kind`/rotacao/camada -- particulas desenham sempre a mesma
        forma simples (um ponto/circulo cheio), na ordem do storage.

        Args:
            positions_xy: shape (N, 2) float32, coordenadas de mundo.
            sizes: shape (N,) float32, diametro em pixels.
            tint_rgba: shape (N, 4) uint8.
            count: numero de entradas validas nos arrays acima.

        Nao ha pool `World`-registrada de particulas (diferente de `fx`) --
        chamar isto e responsabilidade explicita do chamador (tipicamente de
        dentro do callback de `GameLoop.set_on_draw_ui`, ja que nao existe
        cena/gather automatico para particulas). Default: no-op.
        """

    @abstractmethod
    def get_viewport_size(self) -> Tuple[int, int]:
        """Retorna `(largura, altura)` atuais da area de desenho, em pixels."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Libera recursos do backend concreto (janela, contexto grafico, etc.)."""
        ...
