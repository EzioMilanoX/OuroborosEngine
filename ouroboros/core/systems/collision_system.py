"""Deteccao de colisoes AABB entre entidades ativas com Transform e Hitbox."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import numpy as np

from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.systems.spatial_grid import UniformGrid

if TYPE_CHECKING:
    from ouroboros.core.world import World


class CollisionSystem(ISystem):
    """
    Detecta colisoes AABB entre entidades ativas com Transform e
    Hitbox, opcionalmente acelerada por uma `UniformGrid` para reduzir
    pares candidatos.

    Invariantes:
        - O resultado de cada `update` e escrito em
          `self._collision_pairs`, um `np.ndarray` pre-alocado de shape
          `(max_pairs, 2)` (indices GLOBAIS de entidade, nao linhas
          densas) -- nunca uma `list` Python populada via `append`.
        - `self._pair_count` indica quantas linhas do buffer sao
          validas neste frame; pares excedentes a `max_pairs` num unico
          frame sao descartados silenciosamente (teto rigido definido
          na composicao).
        - Como toda destruicao de entidade roteada por
          `World.destroy_entity` e DIFERIDA para o final do `step()`,
          os pares retornados por `get_collision_pairs()` permanecem
          validos durante todo o restante do frame corrente, mesmo que
          outro `ISystem` decida destruir uma das entidades envolvidas.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        transform_pool_name: str,
        hitbox_pool_name: str,
        max_pairs: int,
        spatial_grid: Optional[UniformGrid] = None,
    ) -> None:
        """
        Resolve `transform_pool`/`hitbox_pool` uma unica vez e
        pre-aloca `self._collision_pairs` (shape `(max_pairs, 2)`).
        `spatial_grid`, se fornecida, e usada para limitar os pares
        candidatos antes da checagem fina; caso contrario aplica-se
        varredura bruta O(n^2) sobre as entidades ativas.
        """
        self._transform_pool = memory_manager.get_pool(transform_pool_name)
        self._hitbox_pool = memory_manager.get_pool(hitbox_pool_name)
        self._max_pairs = max_pairs
        self._spatial_grid = spatial_grid
        self._collision_pairs = np.zeros((max_pairs, 2), dtype=np.int64)
        self._pair_count = 0

    def update(self, world: "World", delta_time: float) -> None:
        """
        Calcula `entity_indices = intersect_entity_indices(transform_pool, hitbox_pool)`,
        obtem pares candidatos (via `spatial_grid` ou varredura bruta),
        avalia sobreposicao AABB de forma vetorizada sobre os pares
        candidatos, e escreve os pares efetivamente colidentes em
        `self._collision_pairs` (ate `max_pairs` linhas).
        """
        self._pair_count = 0
        entity_indices = intersect_entity_indices(self._transform_pool, self._hitbox_pool)
        if entity_indices.size < 2:
            return

        transform_view = self._transform_pool.active_view()
        hitbox_view = self._hitbox_pool.active_view()

        if self._spatial_grid is not None:
            rows = self._transform_pool.dense_rows_of(entity_indices)
            positions_xy = np.stack(
                [transform_view["position_x"][rows], transform_view["position_y"][rows]], axis=1
            )
            self._spatial_grid.rebuild(positions_xy, entity_indices)
            candidates = self._spatial_grid.query_candidate_pairs()
        else:
            n = entity_indices.shape[0]
            ii, jj = np.triu_indices(n, k=1)
            candidates = np.stack([entity_indices[ii], entity_indices[jj]], axis=1)

        if candidates.shape[0] == 0:
            return

        a_idx = candidates[:, 0]
        b_idx = candidates[:, 1]
        a_t_rows = self._transform_pool.dense_rows_of(a_idx)
        b_t_rows = self._transform_pool.dense_rows_of(b_idx)
        a_h_rows = self._hitbox_pool.dense_rows_of(a_idx)
        b_h_rows = self._hitbox_pool.dense_rows_of(b_idx)

        ax = transform_view["position_x"][a_t_rows]
        ay = transform_view["position_y"][a_t_rows]
        bx = transform_view["position_x"][b_t_rows]
        by = transform_view["position_y"][b_t_rows]
        aw = hitbox_view["half_width"][a_h_rows]
        ah = hitbox_view["half_height"][a_h_rows]
        bw = hitbox_view["half_width"][b_h_rows]
        bh = hitbox_view["half_height"][b_h_rows]
        a_layer = hitbox_view["collision_layer"][a_h_rows]
        a_mask = hitbox_view["collision_mask"][a_h_rows]
        b_layer = hitbox_view["collision_layer"][b_h_rows]
        b_mask = hitbox_view["collision_mask"][b_h_rows]

        overlap_x = np.abs(ax - bx) <= (aw + bw)
        overlap_y = np.abs(ay - by) <= (ah + bh)
        mask_ok = ((a_mask & b_layer) != 0) | ((b_mask & a_layer) != 0)
        colliding = overlap_x & overlap_y & mask_ok

        colliding_indices = np.flatnonzero(colliding)
        count = min(colliding_indices.shape[0], self._max_pairs)
        if count == 0:
            return
        colliding_indices = colliding_indices[:count]
        self._collision_pairs[:count, 0] = a_idx[colliding_indices]
        self._collision_pairs[:count, 1] = b_idx[colliding_indices]
        self._pair_count = count

    def get_collision_pairs(self) -> np.ndarray:
        """Retorna a view (`self._collision_pairs[:self._pair_count]`) dos pares colidentes do frame corrente, sem copia."""
        return self._collision_pairs[: self._pair_count]
