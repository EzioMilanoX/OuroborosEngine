# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Chama ParticleStorage.update() a cada frame -- ROADMAP M3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ouroboros.core.particle_storage import ParticleStorage
from ouroboros.core.systems.base_system import ISystem

if TYPE_CHECKING:
    from ouroboros.core.world import World


class ParticleUpdateSystem(ISystem):
    """
    Registrado via `world.register_system(...)` como qualquer outro
    sistema (nao ha pool `World`-registrada de particulas, entao nada
    aqui interage com `world` alem de receber o parametro obrigatorio
    de `ISystem.update`) -- roda automaticamente a cada `world.step()`,
    inclusive fica congelado durante uma cena de pausa (ex.:
    `games.rhythm_game.pause_scene.PauseScene`), mesma semantica de
    qualquer outro `ISystem` registrado.
    """

    def __init__(self, particle_storage: ParticleStorage) -> None:
        self._particle_storage = particle_storage

    def update(self, world: "World", delta_time: float) -> None:
        del world
        self._particle_storage.update(delta_time)
