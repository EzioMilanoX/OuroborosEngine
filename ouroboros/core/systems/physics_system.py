"""Integra posicao a partir de velocidade para entidades com Transform e Velocity."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.base_system import ISystem

if TYPE_CHECKING:
    from ouroboros.core.world import World


class PhysicsSystem(ISystem):
    """
    Integra posicao a partir de velocidade (Euler semi-implicito) para
    todas as entidades que possuem Transform E Velocity simultaneamente.

    Invariante: nao possui estado por entidade -- todo estado de
    simulacao vive nas pools do `World`; este objeto guarda apenas as
    referencias de pool resolvidas uma unica vez no construtor.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        transform_pool_name: str = "transform",
        velocity_pool_name: str = "velocity",
    ) -> None:
        """Resolve e guarda `transform_pool`/`velocity_pool` uma unica vez, fora do hot-loop."""
        self._transform_pool = memory_manager.get_pool(transform_pool_name)
        self._velocity_pool = memory_manager.get_pool(velocity_pool_name)

    def update(self, world: "World", delta_time: float) -> None:
        """
        Calcula `entity_indices = intersect_entity_indices(transform_pool, velocity_pool)`,
        resolve as linhas densas correspondentes em cada pool via
        `dense_row_of`, e aplica `position += velocity * delta_time`
        (e `rotation_rad += angular * delta_time`) via slicing
        vetorizado NumPy sobre essas linhas -- sem laco Python por
        entidade.
        """
        entity_indices = intersect_entity_indices(self._transform_pool, self._velocity_pool)
        if entity_indices.size == 0:
            return
        transform_rows = self._transform_pool.dense_rows_of(entity_indices)
        velocity_rows = self._velocity_pool.dense_rows_of(entity_indices)
        transform_view = self._transform_pool.active_view()
        velocity_view = self._velocity_pool.active_view()

        transform_view["position_x"][transform_rows] += velocity_view["linear_x"][velocity_rows] * delta_time
        transform_view["position_y"][transform_rows] += velocity_view["linear_y"][velocity_rows] * delta_time
        transform_view["rotation_rad"][transform_rows] += velocity_view["angular"][velocity_rows] * delta_time
