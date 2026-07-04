"""Funcoes vetorizadas puras de algebra de modificadores, seguras para uso dentro de ISystem.update() com `out=`."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ouroboros.roguelite.modifiers.schemas import ModifierOperation


def sum_flat(base: np.ndarray, flat_sum: np.ndarray, out: Optional[np.ndarray] = None) -> np.ndarray:
    """Retorna `base + flat_sum`, elemento a elemento (`np.add`).

    Uso dentro do hot-path (`ModifierStack.recompute_all`) SEMPRE passa
    `out` apontando para um buffer pre-alocado do proprio
    `ModifierStack` -- omitir `out` ali reintroduziria uma alocacao
    por frame silenciosamente (sem erro, so regressao de performance).
    """
    return np.add(base, flat_sum, out=out)


def apply_percent_additive(
    value: np.ndarray, percent_add_sum: np.ndarray, out: Optional[np.ndarray] = None
) -> np.ndarray:
    """Retorna `value * (1.0 + percent_add_sum)`, vetorizado.

    Ver `sum_flat` quanto a obrigatoriedade de `out` no hot-path.
    """
    factor = percent_add_sum + 1.0
    return np.multiply(value, factor, out=out)


def apply_percent_multiplicative(
    value: np.ndarray, percent_mult_product: np.ndarray, out: Optional[np.ndarray] = None
) -> np.ndarray:
    """Retorna `value * percent_mult_product`, vetorizado (o produto ja
    vem pre-acumulado em `percent_mult_product` por `accumulate_entries_into`).

    Ver `sum_flat` quanto a obrigatoriedade de `out` no hot-path.
    """
    return np.multiply(value, percent_mult_product, out=out)


def clamp(
    value: np.ndarray, min_value: np.ndarray, max_value: np.ndarray, out: Optional[np.ndarray] = None
) -> np.ndarray:
    """Restringe `value` ao intervalo [`min_value`, `max_value`], vetorizado.

    Ver `sum_flat` quanto a obrigatoriedade de `out` no hot-path.
    """
    return np.clip(value, min_value, max_value, out=out)


def accumulate_entries_into(
    attributes: np.ndarray,
    entries: np.ndarray,
    scratch_flat: np.ndarray,
    scratch_percent_add: np.ndarray,
    scratch_percent_mult: np.ndarray,
) -> None:
    """Recalcula in-place `flat_sum`/`percent_add_sum`/`percent_mult_product`
    de `attributes` a partir das `entries` ativas.

    Passo 0 (OBRIGATORIO, primeira coisa que esta funcao faz): reseta
    `scratch_flat`/`scratch_percent_mult` para seus elementos NEUTROS
    (`0.0`, `0.0` e `1.0` respectivamente) via atribuicao direta
    (`scratch_flat[:] = 0.0`, etc.) -- NUNCA assume que o chamador ja
    zerou os buffers. Sem esse reset, entradas desativadas em frames
    anteriores (`remove_by_source`) deixariam residuo acumulado
    "fantasma" no calculo do frame atual.

    Passo 1: filtra `entries` por `is_active` e por `operation`, e
    reduz por `attribute_index` usando reducoes vetorizadas por indice
    (`np.add.at` para FLAT/PERCENT_ADD, `np.multiply.at` para
    PERCENT_MULT) escrevendo nos buffers de scratch -- nunca um loop
    Python por entrada.

    Passo 2: copia os buffers de scratch para os campos correspondentes
    de `attributes` (`attributes['flat_sum'] = scratch_flat` etc.).

    `scratch_flat`, `scratch_percent_add` e `scratch_percent_mult`
    sao buffers pre-alocados (mesmo `shape` de `attributes`)
    fornecidos pelo chamador (`ModifierStack.__init__`) para servir de
    acumulador temporario -- nenhuma alocacao de array ocorre dentro
    desta funcao quando chamada a cada frame.

    Invariante Zero-GC: nenhum objeto Python e instanciado por entrada;
    as unicas escritas sao em buffers NumPy ja existentes.
    """
    # Passo 0: reset dos scratches para os elementos neutros de cada operacao.
    scratch_flat[:] = 0.0
    scratch_percent_add[:] = 0.0
    scratch_percent_mult[:] = 1.0

    active_mask = entries["is_active"]
    attribute_index = entries["attribute_index"]
    operation = entries["operation"]
    magnitude = entries["magnitude"]

    # Passo 1: reducoes vetorizadas por indice, uma por operacao.
    flat_mask = active_mask & (operation == ModifierOperation.FLAT)
    np.add.at(scratch_flat, attribute_index[flat_mask], magnitude[flat_mask])

    percent_add_mask = active_mask & (operation == ModifierOperation.PERCENT_ADD)
    np.add.at(scratch_percent_add, attribute_index[percent_add_mask], magnitude[percent_add_mask])

    percent_mult_mask = active_mask & (operation == ModifierOperation.PERCENT_MULT)
    np.multiply.at(scratch_percent_mult, attribute_index[percent_mult_mask], magnitude[percent_mult_mask])

    # Passo 2: publica os scratches nos campos correspondentes de `attributes`.
    attributes["flat_sum"] = scratch_flat
    attributes["percent_add_sum"] = scratch_percent_add
    attributes["percent_mult_product"] = scratch_percent_mult
