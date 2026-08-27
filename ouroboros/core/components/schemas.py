# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Descritores de layout de memoria (colunas de uma ComponentPool). NAO
sao classes instanciadas por entidade -- sao `numpy.dtype` estruturados
consumidos por `MemoryManager.create_pool`.
"""
from __future__ import annotations

from typing import Dict

import numpy as np

TRANSFORM_DTYPE: np.dtype = np.dtype([
    ("position_x", np.float32),
    ("position_y", np.float32),
    ("rotation_rad", np.float32),
    ("scale_x", np.float32),
    ("scale_y", np.float32),
])
"""Posicao/rotacao/escala 2D. Consumido por `PhysicsSystem` e pelo `IRenderer` (Pilar 2)."""

VELOCITY_DTYPE: np.dtype = np.dtype([
    ("linear_x", np.float32),
    ("linear_y", np.float32),
    ("angular", np.float32),
])
"""Velocidade linear/angular. Consumido por `PhysicsSystem`."""

HITBOX_DTYPE: np.dtype = np.dtype([
    ("half_width", np.float32),
    ("half_height", np.float32),
    ("collision_layer", np.uint32),
    ("collision_mask", np.uint32),
])
"""Volume de colisao AABB + mascara/camada de colisao (bitmask, para
filtragem vetorizada via operacoes bit-a-bit, sem branch Python por
entidade). Consumido por `CollisionSystem`."""

SPRITE_DATA_DTYPE: np.dtype = np.dtype([
    ("texture_id", np.uint32),
    ("frame_index", np.uint16),
    ("tint_r", np.uint8),
    ("tint_g", np.uint8),
    ("tint_b", np.uint8),
    ("tint_a", np.uint8),
    ("layer_z", np.int16),
])
"""Dados de apresentacao crus (SoA), repassados a `IRenderer.draw_batch`
(Pilar 2) -- apenas um `texture_id` inteiro que o backend concreto
resolve para seu proprio recurso grafico, sem vazar acoplamento."""

FX_DTYPE: np.dtype = np.dtype([
    ("kind", np.uint32),
    ("position_x", np.float32),
    ("position_y", np.float32),
    ("width", np.float32),
    ("height", np.float32),
    ("tint_r", np.uint8),
    ("tint_g", np.uint8),
    ("tint_b", np.uint8),
    ("tint_a", np.uint8),
    ("ttl_seconds", np.float32),
])
"""Efeito visual transiente (ROADMAP M1.3), decrementado por
`ouroboros.core.systems.fx_system.FxTtlSystem` e repassado a
`IRenderer.draw_effects` (Pilar 2). `kind` e um inteiro OPACO -- mesma
largura de `SPRITE_DATA_DTYPE.texture_id` (forward-compatible com um
futuro id crc32), nunca resolvido pelo nucleo: a semantica (qual forma/
textura) e responsabilidade exclusiva do backend concreto/produto, que
importa `ouroboros.interfaces.renderer.SHAPE_*` por conta propria (o
nucleo nunca importa `ouroboros.interfaces` -- ver contrato de camadas
do import-linter). Diferente de transform/velocity/hitbox/sprite, a
pool `fx` (criada automaticamente via `COMPONENT_SCHEMAS`, igual as
demais) NAO tem um arquetipo nem sistema registrados automaticamente
pelo `CompositionRoot` -- um produto que queira usar `fx` registra
`world.register_archetype("fx", ("fx",))` e `FxTtlSystem` do seu
proprio jeito, exatamente como ja faz para arquetipos/sistemas
especificos seus."""

COMPONENT_SCHEMAS: Dict[str, np.dtype] = {
    "transform": TRANSFORM_DTYPE,
    "velocity": VELOCITY_DTYPE,
    "hitbox": HITBOX_DTYPE,
    "sprite": SPRITE_DATA_DTYPE,
    "fx": FX_DTYPE,
}
"""Registro nome-logico -> dtype consultado por `MemoryManager.create_pool`
durante a composicao. Schemas especificos de um unico produto (ex.:
atributos modificaveis do Roguelite) NAO pertencem a este dicionario --
vivem no pacote do produto, para manter o nucleo agnostico dos dois jogos."""
