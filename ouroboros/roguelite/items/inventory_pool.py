"""Fachada sobre ComponentPool (Pilar 1) para slots de inventario equipados."""
from __future__ import annotations

import numpy as np

from ouroboros.core.memory.component_pool import ComponentPool


class InventoryPool:
    """Fachada sobre uma `ComponentPool` (Pilar 1) para slots de inventario equipados.

    Reuso deliberado do Pilar 1 em vez de reinventar uma maquina propria
    de sparse/dense: `attach()`/`detach()`/`is_attached()`/
    `active_view()` ja modelam exatamente "este slot esta ocupado?" e
    "compacte os ocupados sem copia". `ComponentPool` exige uma relacao
    1-para-1 entre seu `entity_index` e uma linha densa; para permitir
    MULTIPLOS slots por dono (arma primaria + secundaria, por exemplo)
    sem violar essa invariante, um slot logico `(owner_local_index,
    slot_index)` e achatado em um unico inteiro antes de virar o
    `entity_index` da pool:

        flat_slot_id = owner_local_index * max_slots_per_owner + slot_index

    Cada `flat_slot_id` so pode estar ocupado por, no maximo, UMA arma
    por vez -- preservando exatamente a relacao 1-para-1 que
    `ComponentPool` pressupoe, sem forcar uma relacao muitos-para-um
    onde ela nao existe de fato (um slot especifico de um dono especifico
    nunca contem mais de um item).
    """

    def __init__(self, pool: ComponentPool, max_slots_per_owner: int) -> None:
        """Recebe a `ComponentPool` (dtype `INVENTORY_SLOT_DTYPE`) ja
        criada via `MemoryManager.create_pool` e o numero fixo de slots
        de equipamento suportados por dono, usado para achatar
        `(owner_local_index, slot_index)` em um `entity_index` unico.
        """
        self._pool = pool
        self._max_slots_per_owner = int(max_slots_per_owner)

    @staticmethod
    def compute_flat_slot_id(owner_local_index: int, slot_index: int, max_slots_per_owner: int) -> int:
        """Calcula `owner_local_index * max_slots_per_owner + slot_index`.

        Funcao pura, sem estado -- usada tanto internamente quanto por
        chamadores que precisem pre-calcular um `flat_slot_id` antes de
        chamar `equip`/`unequip`.
        """
        return owner_local_index * max_slots_per_owner + slot_index

    def equip(self, owner_local_index: int, slot_index: int, weapon_row: np.void) -> int:
        """Ocupa o slot achatado de `(owner_local_index, slot_index)` com
        os campos de `weapon_row` (uma linha `INVENTORY_SLOT_DTYPE` ja
        preenchida pelo chamador, tipicamente por `WeaponLoader.materialize`).

        Delega a `ComponentPool.attach`; retorna a linha densa alocada.
        Nao aloca objeto Python -- apenas escreve em uma linha de array
        ja existente.
        """
        flat_slot_id = self.compute_flat_slot_id(owner_local_index, slot_index, self._max_slots_per_owner)
        row = self._pool.attach(flat_slot_id)
        self._pool.active_view()[row] = weapon_row
        return row

    def unequip(self, owner_local_index: int, slot_index: int) -> None:
        """Libera o slot achatado de `(owner_local_index, slot_index)`
        (delega a `ComponentPool.detach`).

        NAO remove modificadores por si so -- o chamador deve invocar
        `ModifierStack.remove_by_source(slot['modifier_source_id'])`
        separadamente antes ou depois de desequipar.
        """
        flat_slot_id = self.compute_flat_slot_id(owner_local_index, slot_index, self._max_slots_per_owner)
        self._pool.detach(flat_slot_id)

    def active_view(self) -> np.ndarray:
        """Fatia compactada (sem copia) de todos os slots atualmente ocupados."""
        return self._pool.active_view()
