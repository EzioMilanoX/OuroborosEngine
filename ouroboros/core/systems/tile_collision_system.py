# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Resolve colisao AABB contra uma Grid2D solida por eixo (ROADMAP M12)."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ouroboros.core.grid2d import Grid2D
from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.base_system import ISystem

if TYPE_CHECKING:
    from ouroboros.core.world import World

_BOUNDARY_EPSILON = 1e-4
"""Vies de ponto flutuante aplicado aos pontos de amostra antes de
arredondar pra celula -- sem isso, uma borda de AABB muito perto (mas nao
exatamente em cima) de um limite de celula fica sujeita a ruido de ponto
flutuante acumulado apos varios ciclos de snap-resolve, oscilando entre
"tocando"/"nao tocando" de frame a frame.

Dois usos, DIRECOES OPOSTAS de proposito:
- Na borda de AVANCO (na direcao do movimento -- `leading_x`/`leading_y`):
  soma o epsilon (empurra ligeiramente ALEM da borda geometrica exata) --
  garante que um encostar/afundar marginal (ex.: o repouso continuo descrito
  na docstring da classe, onde a gravidade reintroduz uma velocidade Y
  residual minuscula a cada frame) sempre seja classificado como "tocando o
  solido", nunca perdido por erro de arredondamento pra baixo.
- Nas amostras PERPENDICULARES ao movimento (as duas bordas laterais, ex.:
  `prev_y ± half_height` no eixo X): subtrai o epsilon (puxa ligeiramente
  PRA DENTRO da AABB) -- evita capturar por engano uma celula so
  diagonalmente adjacente a um canto que a AABB na verdade nao cobre.
Confundir as duas direcoes quebra o cenario de repouso (a amostra de avanco
perde exatamente o afundamento marginal que deveria detectar)."""


class TileCollisionSystem(ISystem):
    """
    Resolve colisao AABB entre entidades com Transform+Velocity+Hitbox e uma
    `Grid2D` solida (ROADMAP M12), eixo por eixo (X primeiro, depois Y --
    evita "pegar" quinas ao mover na diagonal): reconstroi a posicao
    PRE-movimento deste frame (`position - velocity*delta_time`, valido
    porque `PhysicsSystem` acabou de fazer exatamente o oposto com o MESMO
    `delta_time`), testa a borda de AVANCO (na direcao do movimento) contra
    a grade, e se solida, encosta a entidade na borda da celula e zera a
    velocidade daquele eixo.

    **Contrato exigido**: `PhysicsSystem` -> `TileCollisionSystem` ->
    `GravitySystem`, todos no MESMO `World`, nesta ordem exata -- ver
    docstring de `GravitySystem`.

    **Invariante que o algoritmo assume (validada a cada `update()`,
    levanta `ValueError` se violada)**: `hitbox.half_width`/`half_height`
    de toda entidade processada devem ser <= metade do `cell_size` da
    grade -- garante que a AABB nunca cubra mais de 2 colunas/2 linhas,
    entao testar so a borda de avanco (nao os 4 cantos) e suficiente. Uma
    hitbox maior violaria isso SILENCIOSAMENTE (resultado errado, nao
    crash) se nao fosse validada -- rampas/hitboxes maiores que uma
    celula ficam fora de escopo do v1.

    Cada eixo so e testado para entidades com velocidade NAO-NULA naquele
    eixo (uma entidade parada num eixo nao pode ter entrado numa celula
    solida NESTE frame por causa dele). Consequencia aceita: no primeiro
    frame de vida de uma entidade com `velocity.linear_y == 0.0` (ex.: um
    spawn ingenuo com velocidade zerada), o eixo Y e pulado inteiro e
    `is_grounded()` comeca `False` mesmo em repouso sobre o chao --
    corrigido no nivel do PRODUTO (nao aqui): o spawn deve dar a entidade
    uma `velocity.linear_y` inicial pequena e não-nula (ex.: uma fracao de
    `gravity_y`), nao exatamente `0.0`.

    Uma vez em repouso, `grounded` se auto-sustenta frame a frame: como
    `GravitySystem` roda DEPOIS deste sistema, toda vez que a entidade
    fica parada no chao ele reintroduz uma velocidade Y residual pequena
    (pra baixo) antes do frame terminar -- no frame seguinte,
    `PhysicsSystem` integra essa sobra, este sistema a detecta de novo e
    a resolve de novo, marcando `grounded=True` outra vez. Nenhum estado
    "descansando" especial e necessario.

    **Limitacao aceita**: sem colisao continua/varredura -- uma entidade
    rapida o bastante (ou um `delta_time` grande o bastante) pode
    atravessar uma parede fina num unico passo se `velocity*delta_time`
    exceder o tamanho de uma celula. `GameLoop.MAX_DELTA_TIME_SECONDS`
    (ROADMAP M12, achado da critica) reduz bastante o risco do lado do
    `delta_time`; nenhuma protecao equivalente existe do lado da
    velocidade (fora de escopo do v1).
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        grid: Grid2D,
        entity_capacity: int,
        transform_pool_name: str = "transform",
        velocity_pool_name: str = "velocity",
        hitbox_pool_name: str = "hitbox",
    ) -> None:
        self._transform_pool = memory_manager.get_pool(transform_pool_name)
        self._velocity_pool = memory_manager.get_pool(velocity_pool_name)
        self._hitbox_pool = memory_manager.get_pool(hitbox_pool_name)
        self._grid = grid
        self._grounded = np.zeros(entity_capacity, dtype=bool)

    def is_grounded(self, entity_index: int) -> bool:
        """Verdadeiro se esta entidade encostou o chao (colisao Y resolvida
        com velocidade positiva -- caindo) no `update()` mais recente."""
        return bool(self._grounded[entity_index])

    def update(self, world: "World", delta_time: float) -> None:
        del world
        self._grounded[:] = False
        if delta_time <= 0.0:
            return

        entity_indices = intersect_entity_indices(self._transform_pool, self._velocity_pool, self._hitbox_pool)
        if entity_indices.size == 0:
            return

        t_rows = self._transform_pool.dense_rows_of(entity_indices)
        v_rows = self._velocity_pool.dense_rows_of(entity_indices)
        h_rows = self._hitbox_pool.dense_rows_of(entity_indices)
        t_view = self._transform_pool.active_view()
        v_view = self._velocity_pool.active_view()
        h_view = self._hitbox_pool.active_view()

        # Fancy indexing (`[t_rows]`) sempre copia em NumPy -- estes ja sao
        # arrays independentes da pool real, seguros pra mutar localmente
        # abaixo sem afetar `t_view` ate a escrita explicita de volta.
        position_x = t_view["position_x"][t_rows]
        position_y = t_view["position_y"][t_rows]
        velocity_x = v_view["linear_x"][v_rows]
        velocity_y = v_view["linear_y"][v_rows]
        half_width = h_view["half_width"][h_rows]
        half_height = h_view["half_height"][h_rows]

        cell_size = self._grid.cell_size
        half_cell = cell_size / 2.0
        if np.any(half_width > half_cell) or np.any(half_height > half_cell):
            raise ValueError(
                f"TileCollisionSystem: hitbox com half_width/half_height maior que "
                f"metade do cell_size da grade ({half_cell}) -- v1 nao suporta isso"
            )

        # So o eixo Y precisa da posicao PRE-movimento (o eixo X usa a
        # posicao Y de antes deste frame pra nao "pegar" quinas na diagonal
        # -- ver docstring da classe); a posicao X pre-movimento nunca e
        # lida em si (o eixo Y usa a posicao X JA resolvida, nao a antiga).
        prev_y = position_y - velocity_y * delta_time

        # ---- eixo X (usa prev_y -- Y ainda nao se moveu neste frame) ----
        moving_x = velocity_x != 0.0
        if np.any(moving_x):
            direction_x = np.sign(velocity_x)
            leading_x = position_x + direction_x * (half_width + _BOUNDARY_EPSILON)
            solid_top = self._grid.is_solid(leading_x, prev_y - half_height + _BOUNDARY_EPSILON)
            solid_bottom = self._grid.is_solid(leading_x, prev_y + half_height - _BOUNDARY_EPSILON)
            blocked_x = moving_x & (solid_top | solid_bottom)
            if np.any(blocked_x):
                blocked = np.flatnonzero(blocked_x)
                col, _row = self._grid.world_to_cell(leading_x[blocked], prev_y[blocked])
                left_edge = self._grid.origin_x + col * cell_size
                dir_blocked = direction_x[blocked]
                snapped_x = np.where(
                    dir_blocked > 0.0,
                    left_edge - half_width[blocked],
                    left_edge + cell_size + half_width[blocked],
                )
                position_x[blocked] = snapped_x
                final_t_rows = t_rows[blocked]
                final_v_rows = v_rows[blocked]
                t_view["position_x"][final_t_rows] = snapped_x
                v_view["linear_x"][final_v_rows] = 0.0

        # ---- eixo Y (usa a posicao X ja resolvida acima) ----
        moving_y = velocity_y != 0.0
        if np.any(moving_y):
            direction_y = np.sign(velocity_y)
            leading_y = position_y + direction_y * (half_height + _BOUNDARY_EPSILON)
            solid_left = self._grid.is_solid(position_x - half_width + _BOUNDARY_EPSILON, leading_y)
            solid_right = self._grid.is_solid(position_x + half_width - _BOUNDARY_EPSILON, leading_y)
            blocked_y = moving_y & (solid_left | solid_right)
            if np.any(blocked_y):
                blocked = np.flatnonzero(blocked_y)
                _col, row = self._grid.world_to_cell(position_x[blocked], leading_y[blocked])
                top_edge = self._grid.origin_y + row * cell_size
                dir_blocked = direction_y[blocked]
                snapped_y = np.where(
                    dir_blocked > 0.0,
                    top_edge - half_height[blocked],
                    top_edge + cell_size + half_height[blocked],
                )
                final_t_rows = t_rows[blocked]
                final_v_rows = v_rows[blocked]
                t_view["position_y"][final_t_rows] = snapped_y
                v_view["linear_y"][final_v_rows] = 0.0

                falling = dir_blocked > 0.0
                if np.any(falling):
                    self._grounded[entity_indices[blocked[falling]]] = True
