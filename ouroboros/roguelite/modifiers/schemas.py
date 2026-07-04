"""Schemas SoA de atributos modificaveis e entradas de modificador."""
from __future__ import annotations

from enum import IntEnum

import numpy as np

MODIFIABLE_ATTRIBUTE_DTYPE: np.dtype = np.dtype(
    [
        ("base_value", np.float32),
        ("flat_sum", np.float32),
        ("percent_add_sum", np.float32),
        ("percent_mult_product", np.float32),
        ("min_clamp", np.float32),
        ("max_clamp", np.float32),
        ("final_value", np.float32),
    ]
)
"""Schema de uma linha de atributo modificavel (ex.: dano, velocidade).

Campos:
    base_value: valor base antes de qualquer modificador.
    flat_sum: acumulador de modificadores aditivos flat.
    percent_add_sum: acumulador de modificadores percentuais ADITIVOS
        entre si (+10% e +20% viram +30%, nao *1.1*1.2).
    percent_mult_product: acumulador de modificadores percentuais
        MULTIPLICATIVOS entre si (compostos, ex.: *1.1 * 1.2).
    min_clamp, max_clamp: limites aplicados ao valor final.
    final_value: resultado ja computado por `ModifierStack.recompute_all`,
        pronto para leitura por outros sistemas sem recomputar a formula.
"""


class ModifierOperation(IntEnum):
    """Codigos de operacao de modificador, armazenaveis em `int8`.

    O valor numerico NAO determina ordem de aplicacao por si (a ordem de
    aplicacao -- flat, depois percentual aditivo, depois multiplicativo --
    e fixa na formula de `ModifierStack.recompute_all`/`operations.py`,
    independente destes valores). Assim como `RandomStreamPurpose`, os
    valores sao um contrato estavel: nunca renumerar um membro existente.
    """

    FLAT = 0
    PERCENT_ADD = 1
    PERCENT_MULT = 2


MODIFIER_ENTRY_DTYPE: np.dtype = np.dtype(
    [
        ("attribute_index", np.int32),
        ("operation", np.int8),
        ("magnitude", np.float32),
        ("source_id", np.int64),
        ("is_active", np.bool_),
    ]
)
"""Schema de uma entrada individual dentro de um `ModifierStack`.

Campos:
    attribute_index: linha PERMANENTE (ver `ModifierStack.register_attribute`)
        em `MODIFIABLE_ATTRIBUTE_DTYPE` afetada por este modificador.
    operation: um dos valores de `ModifierOperation`.
    magnitude: valor do modificador (ex.: +5, ou 0.10 para +10%).
    source_id: identificador UNICO da origem que aplicou este modificador
        (ex.: PackedEntityId do item equipado, id de instancia de buff) --
        permite remocao seletiva via `remove_by_source` sem varrer por
        igualdade de valor. NUNCA usar um id de TEMPLATE/definicao
        compartilhado entre multiplas instancias (ex.: o `weapon_id` de
        uma definicao de arma que pode estar equipada em varias entidades
        simultaneamente) -- isso removeria modificadores de todas as
        instancias de uma vez ao desequipar apenas uma.
    is_active: permite "desligar" uma entrada sem liberar seu slot para
        reciclagem imediata (ver invariante de `ModifierStack` sobre
        remocao adiada/compactada).
"""
