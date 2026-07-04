"""Container SoA de atributos modificaveis e dos modificadores que os afetam."""
from __future__ import annotations

from typing import List

import numpy as np

from ouroboros.roguelite.modifiers.operations import (
    accumulate_entries_into,
    apply_percent_additive,
    apply_percent_multiplicative,
    clamp,
    sum_flat,
)
from ouroboros.roguelite.modifiers.schemas import (
    MODIFIABLE_ATTRIBUTE_DTYPE,
    MODIFIER_ENTRY_DTYPE,
    ModifierOperation,
)


class ModifierStack:
    """Container SoA de atributos modificaveis e dos modificadores que os afetam.

    Duas colecoes internas com ciclos de vida DELIBERADAMENTE diferentes
    -- essa assimetria e o que evita um bug classico de referencia
    obsoleta (ver abaixo):

      - ATRIBUTOS (`MODIFIABLE_ATTRIBUTE_DTYPE`, via
        `register_attribute`): APPEND-ONLY e PERMANENTE. Uma vez
        registrado, um `attribute_index` e valido e ESTAVEL pelo resto
        da vida do `ModifierStack` -- nao existe operacao de
        "des-registrar" um atributo, e portanto nenhuma linha de atributo
        e reciclada/realocada para outro dono. Isso e o que torna seguro
        gravar `attribute_index` de forma duradoura em outras
        estruturas (ex.: `WEAPON_DTYPE.damage_attribute_index`) SEM o
        risco -- presente em pools que fazem swap-remove/compactacao --
        de esse indice silenciosamente passar a apontar para o atributo
        de outra entidade apos uma remocao alheia.
      - ENTRADAS de modificador (`MODIFIER_ENTRY_DTYPE`, via `push`/
        `remove_by_source`): RECICLAVEIS. Slots de entrada podem ser
        reaproveitados apos remocao, porque NENHUM codigo externo cacheia
        o indice de linha de uma entrada especifica entre frames -- o
        unico identificador externo estavel de uma entrada e
        `source_id`, usado por `remove_by_source` para localiza-la de
        novo vetorizadamente a cada remocao, nunca por indice cacheado.

    Invariante Zero-GC: `register_attribute`/`push`/`remove_by_source`
    so podem ser chamados FORA do loop de gameplay quente (ex.: ao criar a
    entidade, ao equipar um item, ao aplicar um buff pontual em resposta a
    um evento discreto de input) -- escrevem em linhas JA pre-alocadas dos
    arrays internos, nunca instanciam um objeto Python por modificador.
    Dentro de `ISystem.update()` (via `ModifierApplicationSystem`), o
    unico metodo chamado a cada frame e `recompute_all`, que opera
    inteiramente por slicing/vetorizacao sobre os arrays e buffers de
    scratch ja existentes (pre-alocados em `__init__`).
    """

    def __init__(self, attribute_capacity: int, entry_capacity: int) -> None:
        """Pre-aloca o array de atributos (`MODIFIABLE_ATTRIBUTE_DTYPE`,
        tamanho `attribute_capacity`), o array de entradas
        (`MODIFIER_ENTRY_DTYPE`, tamanho `entry_capacity`) e os tres
        buffers de scratch (mesmo tamanho de `attribute_capacity`) usados
        por `accumulate_entries_into`. Nenhuma realocacao ocorre depois
        da construcao.
        """
        self._attribute_capacity = int(attribute_capacity)
        self._entry_capacity = int(entry_capacity)

        self._attributes = np.zeros(self._attribute_capacity, dtype=MODIFIABLE_ATTRIBUTE_DTYPE)
        self._attribute_count = 0

        self._entries = np.zeros(self._entry_capacity, dtype=MODIFIER_ENTRY_DTYPE)
        self._entry_count = 0
        self._free_entry_slots: List[int] = []

        self._scratch_flat = np.zeros(self._attribute_capacity, dtype=np.float32)
        self._scratch_percent_add = np.zeros(self._attribute_capacity, dtype=np.float32)
        self._scratch_percent_mult = np.ones(self._attribute_capacity, dtype=np.float32)

    @property
    def attributes(self) -> np.ndarray:
        """View SoA de `[0:attribute_count]` atributos registrados (inclui `final_value`)."""
        return self._attributes[: self._attribute_count]

    @property
    def attribute_count(self) -> int:
        """Numero de atributos ja registrados (prefixo denso, append-only)."""
        return self._attribute_count

    @property
    def entry_count(self) -> int:
        """Numero de linhas de entrada atualmente ocupadas (ativas ou nao)."""
        return self._entry_count

    def register_attribute(self, base_value: float, min_clamp: float, max_clamp: float) -> int:
        """Registra um novo atributo modificavel na proxima linha livre e
        PERMANENTE, retorna seu indice.

        So pode ser chamado fora do hot-path. Levanta `IndexError` se
        `attribute_capacity` for excedida.
        """
        if self._attribute_count >= self._attribute_capacity:
            raise IndexError("ModifierStack attribute_capacity excedida")
        index = self._attribute_count
        row = self._attributes[index]
        row["base_value"] = base_value
        row["flat_sum"] = 0.0
        row["percent_add_sum"] = 0.0
        row["percent_mult_product"] = 1.0
        row["min_clamp"] = min_clamp
        row["max_clamp"] = max_clamp
        row["final_value"] = min(max(float(base_value), float(min_clamp)), float(max_clamp))
        self._attribute_count += 1
        return index

    def push(self, attribute_index: int, operation: ModifierOperation, magnitude: float, source_id: int) -> int:
        """Insere uma entrada de modificador em um slot livre (reciclado ou
        novo) do array de entradas, retorna o indice dessa linha.

        Nao aloca objeto Python; apenas escreve campos escalares em uma
        linha de array ja existente. So pode ser chamado fora do
        hot-path. Levanta `IndexError` se `entry_capacity` for
        excedida.
        """
        if self._free_entry_slots:
            index = self._free_entry_slots.pop()
        else:
            if self._entry_count >= self._entry_capacity:
                raise IndexError("ModifierStack entry_capacity excedida")
            index = self._entry_count
            self._entry_count += 1
        row = self._entries[index]
        row["attribute_index"] = attribute_index
        row["operation"] = int(operation)
        row["magnitude"] = magnitude
        row["source_id"] = source_id
        row["is_active"] = True
        return index

    def remove_by_source(self, source_id: int) -> int:
        """Marca `is_active = False` em todas as entradas cujo
        `source_id` corresponda e libera seus slots para reciclagem por
        `push` futuro. Retorna quantas entradas foram desativadas.

        Vetorizado via mascara booleana, sem loop Python por entrada.
        Seguro porque nenhum indice de entrada e cacheado externamente
        (ver docstring de classe).
        """
        used = self._entries[: self._entry_count]
        mask = used["is_active"] & (used["source_id"] == source_id)
        matched_indices = np.flatnonzero(mask)
        if matched_indices.size == 0:
            return 0
        used["is_active"][mask] = False
        self._free_entry_slots.extend(int(index) for index in matched_indices)
        return int(matched_indices.size)

    def recompute_all(self) -> None:
        """Recalcula `final_value` de TODOS os atributos registrados a
        partir das entradas ativas, in-place, usando exclusivamente as
        funcoes puras de `ouroboros.roguelite.modifiers.operations` com
        `out=` apontando para buffers ja pre-alocados.

        Ordem fixa de composicao: `accumulate_entries_into` ->
        `sum_flat` -> `apply_percent_additive` ->
        `apply_percent_multiplicative` -> `clamp`, escrevendo o
        resultado em `final_value`.

        Seguro para chamar a cada frame dentro de
        `ModifierApplicationSystem.update()` -- nao aloca nenhum objeto
        Python nem array novo.
        """
        attributes = self._attributes[: self._attribute_count]
        entries = self._entries[: self._entry_count]
        scratch_flat = self._scratch_flat[: self._attribute_count]
        scratch_percent_add = self._scratch_percent_add[: self._attribute_count]
        scratch_percent_mult = self._scratch_percent_mult[: self._attribute_count]

        accumulate_entries_into(attributes, entries, scratch_flat, scratch_percent_add, scratch_percent_mult)

        final_value = attributes["final_value"]
        sum_flat(attributes["base_value"], attributes["flat_sum"], out=final_value)
        apply_percent_additive(final_value, attributes["percent_add_sum"], out=final_value)
        apply_percent_multiplicative(final_value, attributes["percent_mult_product"], out=final_value)
        clamp(final_value, attributes["min_clamp"], attributes["max_clamp"], out=final_value)
