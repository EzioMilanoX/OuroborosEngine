# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Schema SoA de uma unidade tatica (ROADMAP M13) -- mesmo desenho de ouroboros.roguelite.combat.schemas.HEALTH_DTYPE."""
from __future__ import annotations

from enum import IntEnum

import numpy as np


class Team(IntEnum):
    """Lado a que uma unidade pertence. Contrato estavel -- nunca renumerar."""

    PLAYER = 0
    ENEMY = 1


TACTICS_UNIT_DTYPE: np.dtype = np.dtype(
    [
        ("team", np.int8),
        ("grid_x", np.int16),
        ("grid_y", np.int16),
        ("current_hp", np.float32),
        ("max_hp", np.float32),
        ("attack_attribute_index", np.int32),
        ("defense_attribute_index", np.int32),
        ("move_range_attribute_index", np.int32),
    ]
)
"""Schema de UMA unidade tatica.

Campos:
    team: ver `Team`.
    grid_x, grid_y: posicao ATUAL na `BattlefieldGrid` -- fonte de verdade
        da posicao logica; `transform.position_x/y` (pool generica, Pilar 1,
        usada so pra desenho) e derivada destes dois toda vez que mudam,
        nunca o contrario.
    current_hp/max_hp: campos MUTAVEIS simples, decrementados direto ao
        sofrer dano -- deliberadamente NAO atributos de `ModifierStack`
        (mesmo criterio de `HEALTH_DTYPE.current_hp`/`max_hp` no Roguelite:
        HP-apos-dano e um valor com ESTADO que decresce por evento, o
        oposto do modelo de `ModifierStack`, que RECALCULA um `final_value`
        do zero a partir de base+modificadores ativos a cada chamada de
        `recompute_all` -- nao "acumula dano").
    attack_attribute_index/defense_attribute_index/move_range_attribute_index:
        indices PERMANENTES (ver `ModifierStack.register_attribute`) num
        UNICO `ModifierStack` compartilhado por todas as unidades da
        batalha (mesmo idioma de `WEAPON_DTYPE.damage_attribute_index` --
        uma stackso, um `source_id` UNICO por unidade nas entradas que ela
        push, nunca uma `ModifierStack` por unidade)."""
