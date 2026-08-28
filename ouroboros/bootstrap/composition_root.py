# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CompositionRoot: unico ponto (alem de ouroboros.adapters) que conhece World + backends concretos."""
from __future__ import annotations

from typing import Optional

from ouroboros.adapters.pygame_backend.pygame_audio_engine import PygameAudioEngine
from ouroboros.adapters.pygame_backend.pygame_input_provider import PygameInputProvider
from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.components.schemas import COMPONENT_SCHEMAS
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.collision_system import CollisionSystem
from ouroboros.core.systems.physics_system import PhysicsSystem
from ouroboros.core.systems.spatial_grid import UniformGrid
from ouroboros.core.world import World

DEFAULT_MAX_COLLISION_PAIRS: int = 4096
"""Teto padrao de pares de colisao por frame -- dimensionamento de
infraestrutura (analogo a `DEFAULT_ENTITY_CAPACITY` do Pilar 1), nao um
valor de balanceamento de gameplay."""


class CompositionRoot:
    """
    Monta o `World` (Pilar 1), registra as pools genericas e os sistemas
    genericos do nucleo, e escolhe as implementacoes concretas de
    `IRenderer`/`IInputProvider`/`IAudioEngine` (Pygame hoje, importadas
    de `ouroboros.adapters.pygame_backend`; outro backend no futuro) a
    partir de `EngineConfig`. Este e o UNICO ponto do projeto -- alem
    do proprio pacote `ouroboros.adapters` -- que importa um backend
    concreto, mantendo a Regra 2 da Constituicao verificavel por
    `tooling/import_linter_contracts.ini`.

    Arquetipos/sistemas ESPECIFICOS de um produto (Roguelite ou Rhythm)
    nao sao registrados aqui -- isso e responsabilidade de um script de
    composicao proprio do produto, que usa este `CompositionRoot` como
    base e registra por cima (`world.register_archetype`/
    `world.register_system`) antes de chamar `game_loop.run()`.
    """

    def __init__(self, config: EngineConfig) -> None:
        """Guarda `config`; nao constroi nada pesado ainda (ver `build`)."""
        self._config = config

    def build(self, spatial_grid: Optional[UniformGrid] = None) -> GameLoop:
        """
        Constroi `MemoryManager`, `World`, registra as pools genericas
        (Pilar 1) e os sistemas na ordem correta, carrega dificuldade/
        bindings/arquetipos de `data/*.json`, instancia os backends
        concretos escolhidos (Pilar 2 via `ouroboros.adapters`), e
        monta um `GameLoop` pronto para `run()`.

        `spatial_grid`: opcional, repassado direto pro `CollisionSystem`
        (Pilar 1) que este metodo ja constroi -- sem ele, a deteccao de
        colisao roda em forca-bruta O(n^2) (default, preserva o
        comportamento de sempre). Um produto que ja sabe os limites do seu
        mundo (ex.: o Roguelite, a partir de uma `DungeonLayout` ja gerada)
        pode montar seu proprio `UniformGrid` e passar aqui -- `CompositionRoot`
        continua agnostico de QUALQUER conceito especifico de produto
        (nao sabe o que e uma "masmorra"), so aceita um objeto ja pronto do
        Pilar 1.
        """
        memory_manager = MemoryManager(entity_capacity=self._config.entity_capacity)
        for pool_name, dtype in COMPONENT_SCHEMAS.items():
            memory_manager.create_pool(pool_name, dtype)

        world = World(memory_manager)
        world.register_system(PhysicsSystem(memory_manager))
        world.register_system(
            CollisionSystem(
                memory_manager,
                transform_pool_name="transform",
                hitbox_pool_name="hitbox",
                max_pairs=DEFAULT_MAX_COLLISION_PAIRS,
                spatial_grid=spatial_grid,
            )
        )

        renderer = PygameRenderer()
        renderer.initialize(self._config.window_width, self._config.window_height, self._config.window_title)

        input_provider = PygameInputProvider()
        input_provider.load_bindings(self._config.input_bindings_path)

        audio_engine = PygameAudioEngine()

        return GameLoop(world, renderer, input_provider, audio_engine)
