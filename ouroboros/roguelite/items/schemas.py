"""Schemas SoA de definicao de arma (catalogo) e slot de inventario ocupado."""
from __future__ import annotations

import numpy as np

WEAPON_DTYPE: np.dtype = np.dtype(
    [
        ("weapon_def_id", np.int32),
        ("damage_attribute_index", np.int32),
        ("cooldown_attribute_index", np.int32),
        ("range_attribute_index", np.int32),
        ("projectile_texture_id", np.int32),
        ("tier", np.int8),
    ]
)
"""Schema de uma DEFINICAO de arma (catalogo, materializada por
`WeaponLoader.load_all_definitions`).

Campos:
    weapon_def_id: identificador estavel correspondente a definicao
        carregada de `data/weapons/*.json`.
    damage_attribute_index, cooldown_attribute_index, range_attribute_index:
        indices, em um `ModifierStack` USADO COMO TEMPLATE de valores
        base (nunca a instancia por-entidade), dos atributos base desta
        arma. A materializacao POR-INSTANCIA (quando um jogador
        efetivamente equipa a arma) ocorre em `InventoryPool.equip`,
        que registra seus PROPRIOS atributos/entradas de modificador
        atrelados a um `source_id` unico de instancia -- nunca
        reaproveitando estes indices de template diretamente no
        `ModifierStack` de gameplay.
    projectile_texture_id: id de textura repassado ao `IRenderer`.
    tier: raridade/tier da arma, usado para exibicao/ordenacao.
"""

INVENTORY_SLOT_DTYPE: np.dtype = np.dtype(
    [
        ("weapon_def_id", np.int32),
        ("modifier_source_id", np.int64),
        ("damage_attribute_index", np.int32),
        ("cooldown_attribute_index", np.int32),
        ("range_attribute_index", np.int32),
    ]
)
"""Schema de um slot de inventario OCUPADO (uma arma efetivamente equipada
em um slot especifico de um dono especifico).

Campos:
    weapon_def_id: referencia a definicao de catalogo (`WEAPON_DTYPE`).
    modifier_source_id: `source_id` UNICO desta instancia de equipamento
        no `ModifierStack` de gameplay -- usado por
        `ModifierStack.remove_by_source` ao desequipar, garantindo que
        remover esta instancia nunca afete outra copia da mesma arma
        equipada em outro dono/slot.
    damage_attribute_index, cooldown_attribute_index, range_attribute_index:
        indices, no `ModifierStack` de gameplay, dos atributos
        registrados especificamente para ESTA instancia equipada.
"""
