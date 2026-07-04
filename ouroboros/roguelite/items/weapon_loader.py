"""Le data/weapons/*.json e materializa definicoes (template) e instancias equipadas de arma."""
from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ouroboros.roguelite.items.inventory_pool import InventoryPool
from ouroboros.roguelite.items.schemas import INVENTORY_SLOT_DTYPE, WEAPON_DTYPE
from ouroboros.roguelite.modifiers.modifier_stack import ModifierStack
from ouroboros.roguelite.modifiers.schemas import ModifierOperation

_REQUIRED_FIELDS = ("id", "display_name", "base_damage", "fire_rate_per_second", "projectile_speed")

_OPERATION_BY_NAME = {
    "flat": ModifierOperation.FLAT,
    "percent_add": ModifierOperation.PERCENT_ADD,
    "percent_mult": ModifierOperation.PERCENT_MULT,
}

_ATTRIBUTE_KEY_BY_NAME = ("damage", "cooldown", "range")

# Limite superior de folga usado como clamp "sem teto pratico" para atributos
# de arma cujo JSON nao especifica um teto explicito.
_UNBOUNDED_MAX = float(np.finfo(np.float32).max)


def _stable_weapon_def_id(text_id: str) -> int:
    """Deriva um `weapon_def_id` inteiro (int32) estavel a partir do `id`
    textual do JSON, via CRC32 -- puro e deterministico entre execucoes
    (ao contrario de `hash()` nativo, que e aleatorizado por processo)."""
    return zlib.crc32(text_id.encode("utf-8")) & 0x7FFFFFFF


class WeaponDefinitionError(Exception):
    """Levantado quando um arquivo de definicao de arma esta malformado,
    referencia um campo obrigatorio ausente, ou tem valores fora do
    intervalo esperado.
    """


class WeaponLoader:
    """Le `data/weapons/*.json` e materializa definicoes/instancias de arma.

    Invariante DATA-DRIVEN: 100% dos parametros numericos de balanceamento
    (dano base, cooldown, alcance, clamps) vem do JSON.

    Separa explicitamente dois momentos, para nao confundir TEMPLATE
    (definicao compartilhada de uma arma) com INSTANCIA (uma copia
    especifica equipada por um dono especifico):

      1. `load_all_definitions`: parsing puro, roda no carregamento de
         conteudo, produz apenas dados (`WEAPON_DTYPE`) -- NENHUMA
         interacao com `ModifierStack` ocorre aqui, pois ainda nao ha
         nenhuma instancia equipada por ninguem.
      2. `materialize`: chamado no momento em que uma copia da arma e
         efetivamente equipada por um dono; e AQUI que atributos/entradas
         sao registrados no `ModifierStack` de gameplay, com um
         `source_id` UNICO por instancia (nunca o `weapon_def_id`
         compartilhado), evitando que desequipar uma copia remova os
         modificadores de outra copia da mesma arma.

    Roda fora do loop de gameplay (carregamento de nivel/inventario);
    pode alocar dicts/objetos Python livremente durante o parsing.
    """

    def __init__(self, weapons_directory: Path) -> None:
        """Aponta para o diretorio contendo os arquivos `*.json` de arma."""
        self._weapons_directory = Path(weapons_directory)
        # Populados por `load_all_definitions`: dados crus do JSON (usados
        # por `materialize` para reaplicar os modificadores "de fabrica" da
        # arma a cada nova instancia) e um ModifierStack TEMPLATE que guarda
        # base_value/min_clamp/max_clamp de cada atributo do catalogo -- nunca
        # usado para registrar entradas nem para representar uma instancia
        # equipada (ver docstring de classe e de `WEAPON_DTYPE`).
        self._raw_definitions_by_id: Dict[int, dict] = {}
        self._template_stack: Optional[ModifierStack] = None

    def load_all_definitions(self) -> Dict[int, np.void]:
        """Le e valida todos os `*.json` do diretorio, retorna um dict
        `weapon_def_id -> linha WEAPON_DTYPE` (catalogo, sem nenhuma
        interacao com `ModifierStack`).

        Levanta `WeaponDefinitionError` se um arquivo estiver malformado
        ou faltando campos obrigatorios.
        """
        raw_by_id: Dict[int, dict] = {}
        for path in sorted(self._weapons_directory.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError as exc:
                    raise WeaponDefinitionError(f"JSON invalido em {path}: {exc}") from exc

            for field in _REQUIRED_FIELDS:
                if field not in data:
                    raise WeaponDefinitionError(f"arquivo {path} sem campo obrigatorio '{field}'")

            fire_rate = float(data["fire_rate_per_second"])
            if fire_rate <= 0.0:
                raise WeaponDefinitionError(
                    f"fire_rate_per_second deve ser > 0 em {path} (id='{data['id']}')"
                )

            weapon_def_id = _stable_weapon_def_id(str(data["id"]))
            if weapon_def_id in raw_by_id:
                raise WeaponDefinitionError(
                    f"weapon_def_id colidiu/duplicou para '{data['id']}' em {path}"
                )
            raw_by_id[weapon_def_id] = data

        # ModifierStack usado exclusivamente como TEMPLATE de valores base
        # (ver docstring de `WEAPON_DTYPE`): 3 atributos (dano/cooldown/
        # alcance) por definicao carregada, nenhuma entrada jamais
        # registrada, `recompute_all` jamais chamado.
        template_stack = ModifierStack(
            attribute_capacity=max(1, len(raw_by_id) * 3),
            entry_capacity=1,
        )

        definitions: Dict[int, np.void] = {}
        for weapon_def_id, data in raw_by_id.items():
            damage_index = template_stack.register_attribute(
                base_value=float(data["base_damage"]), min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
            )
            cooldown_index = template_stack.register_attribute(
                base_value=1.0 / float(data["fire_rate_per_second"]), min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
            )
            range_index = template_stack.register_attribute(
                base_value=float(data["projectile_speed"]), min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
            )

            row = np.zeros(1, dtype=WEAPON_DTYPE)[0]
            row["weapon_def_id"] = weapon_def_id
            row["damage_attribute_index"] = damage_index
            row["cooldown_attribute_index"] = cooldown_index
            row["range_attribute_index"] = range_index
            row["projectile_texture_id"] = int(data.get("projectile_texture_id", 0))
            row["tier"] = int(data.get("tier", 0))
            definitions[weapon_def_id] = row

        self._template_stack = template_stack
        self._raw_definitions_by_id = raw_by_id
        return definitions

    def materialize(
        self,
        weapon_def_id: int,
        definitions: Dict[int, np.void],
        inventory: InventoryPool,
        modifier_stack: ModifierStack,
        owner_local_index: int,
        slot_index: int,
        instance_source_id: int,
    ) -> int:
        """Materializa uma INSTANCIA equipada de `weapon_def_id` no slot
        `(owner_local_index, slot_index)` de `inventory`, registrando
        atributos modificaveis PROPRIOS desta instancia (dano/cooldown/
        alcance, com valores base copiados da definicao) em
        `modifier_stack` via `register_attribute`, todos com
        `source_id = instance_source_id`.

        `instance_source_id` deve ser UNICO por instancia equipada (ex.:
        derivado do `PackedEntityId` do dono combinado com
        `slot_index`) -- nunca `weapon_def_id` (ver docstring de
        classe e de `MODIFIER_ENTRY_DTYPE.source_id`).

        Retorna a linha densa alocada em `inventory`.
        """
        if self._template_stack is None:
            raise WeaponDefinitionError("load_all_definitions() deve ser chamado antes de materialize()")
        if weapon_def_id not in definitions:
            raise WeaponDefinitionError(f"weapon_def_id {weapon_def_id} nao encontrado no catalogo")

        catalog_row = definitions[weapon_def_id]
        template_attributes = self._template_stack.attributes

        def _instantiate_attribute(template_index: int) -> int:
            template_row = template_attributes[int(template_index)]
            return modifier_stack.register_attribute(
                base_value=float(template_row["base_value"]),
                min_clamp=float(template_row["min_clamp"]),
                max_clamp=float(template_row["max_clamp"]),
            )

        damage_index = _instantiate_attribute(catalog_row["damage_attribute_index"])
        cooldown_index = _instantiate_attribute(catalog_row["cooldown_attribute_index"])
        range_index = _instantiate_attribute(catalog_row["range_attribute_index"])

        attribute_index_by_name = {
            "damage": damage_index,
            "cooldown": cooldown_index,
            "range": range_index,
        }

        raw_definition = self._raw_definitions_by_id.get(int(weapon_def_id), {})
        modifiers: List[dict] = raw_definition.get("modifiers", []) or []
        for modifier in modifiers:
            attribute_name = modifier["attribute"]
            if attribute_name not in attribute_index_by_name:
                raise WeaponDefinitionError(
                    f"modificador de arma referencia atributo desconhecido '{attribute_name}'"
                )
            operation_name = modifier["operation"]
            if operation_name not in _OPERATION_BY_NAME:
                raise WeaponDefinitionError(
                    f"modificador de arma referencia operacao desconhecida '{operation_name}'"
                )
            modifier_stack.push(
                attribute_index_by_name[attribute_name],
                _OPERATION_BY_NAME[operation_name],
                float(modifier["magnitude"]),
                instance_source_id,
            )

        slot_row = np.zeros(1, dtype=INVENTORY_SLOT_DTYPE)[0]
        slot_row["weapon_def_id"] = weapon_def_id
        slot_row["modifier_source_id"] = instance_source_id
        slot_row["damage_attribute_index"] = damage_index
        slot_row["cooldown_attribute_index"] = cooldown_index
        slot_row["range_attribute_index"] = range_index

        return inventory.equip(owner_local_index, slot_index, slot_row)
