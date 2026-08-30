# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le data/cards/*.json e materializa o catalogo de CardDefinition (ver WeaponLoader para o mesmo desenho de validacao)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ouroboros.cardgame.cards.schemas import CardDefinition, CardEffect, CardType
from ouroboros.cardgame.effects.schemas import EffectOp
from ouroboros.core.stable_id import stable_id_from_name

_REQUIRED_FIELDS = ("id", "display_name", "cost", "card_type")

_CARD_TYPE_BY_NAME = {"action": CardType.ACTION, "creature": CardType.CREATURE}

_EFFECT_OP_BY_NAME = {
    "damage_target": EffectOp.DAMAGE_TARGET,
    "heal_target": EffectOp.HEAL_TARGET,
    "draw_cards": EffectOp.DRAW_CARDS,
    "buff_stat": EffectOp.BUFF_STAT,
    "gain_resource": EffectOp.GAIN_RESOURCE,
}

# Vocabulario FECHADO de atributos/operacoes de buff -- so "attack" existe
# como atributo de criatura no v1 (ver docstring de CardDefinition).
_VALID_BUFF_ATTRIBUTES = ("attack",)
_VALID_BUFF_OPERATIONS = ("flat", "percent_add", "percent_mult")


class CardDefinitionError(Exception):
    """Levantado quando um arquivo de definicao de carta esta malformado,
    referencia um campo/operacao/valor obrigatorio ausente ou desconhecido,
    ou colide de id com outra carta ja carregada."""


class CardLoader:
    """Le `data/cards/*.json` e materializa o catalogo de `CardDefinition`.

    Mesma disciplina de `WeaponLoader.load_all_definitions`: 100% dos
    parametros de balanceamento (custo, ataque, argumentos de efeito) vem
    do JSON, e toda validacao de conteudo -- incluindo os ARGUMENTOS de
    cada efeito, nao so o nome da operacao -- acontece aqui, no
    carregamento, nunca em runtime dentro de `apply_effect` (falhar alto
    na composicao, nunca silenciosamente no meio de uma partida).
    """

    def __init__(self, cards_directory: Path) -> None:
        self._cards_directory = Path(cards_directory)

    def load_all(self) -> Dict[int, CardDefinition]:
        """Le e valida todos os `*.json` do diretorio, retorna um dict
        `card_def_id -> CardDefinition`. Levanta `CardDefinitionError` se
        um arquivo estiver malformado, com campos/operacoes/valores
        obrigatorios ausentes ou desconhecidos, com id duplicado, ou se o
        diretorio nao contiver nenhuma carta."""
        definitions: Dict[int, CardDefinition] = {}
        for path in sorted(self._cards_directory.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError as exc:
                    raise CardDefinitionError(f"JSON invalido em {path}: {exc}") from exc

            for field in _REQUIRED_FIELDS:
                if field not in data:
                    raise CardDefinitionError(f"arquivo {path} sem campo obrigatorio '{field}'")

            card_type_name = data["card_type"]
            if card_type_name not in _CARD_TYPE_BY_NAME:
                raise CardDefinitionError(f"card_type desconhecido '{card_type_name}' em {path}")
            card_type = _CARD_TYPE_BY_NAME[card_type_name]

            base_attack = 0
            if card_type == CardType.CREATURE:
                if "base_attack" not in data:
                    raise CardDefinitionError(
                        f"carta 'creature' sem campo obrigatorio 'base_attack' em {path}"
                    )
                base_attack = int(data["base_attack"])

            effects = tuple(self._parse_effect(raw_effect, path) for raw_effect in data.get("effects", []))

            card_def_id = stable_id_from_name(str(data["id"]))
            if card_def_id in definitions:
                raise CardDefinitionError(f"card_def_id colidiu/duplicou para '{data['id']}' em {path}")

            definitions[card_def_id] = CardDefinition(
                card_def_id=card_def_id,
                card_id=str(data["id"]),
                display_name=str(data["display_name"]),
                cost=int(data["cost"]),
                card_type=int(card_type),
                base_attack=base_attack,
                effects=effects,
            )

        if not definitions:
            raise CardDefinitionError(f"nenhuma carta encontrada em {self._cards_directory}")
        return definitions

    def _parse_effect(self, raw_effect: dict, path: Path) -> CardEffect:
        op_name = raw_effect.get("op")
        if op_name not in _EFFECT_OP_BY_NAME:
            raise CardDefinitionError(f"operacao de efeito desconhecida '{op_name}' em {path}")
        op = _EFFECT_OP_BY_NAME[op_name]
        args = dict(raw_effect.get("args", {}))
        self._validate_args(op, args, op_name, path)
        return CardEffect(op=int(op), args=args)

    def _validate_args(self, op: EffectOp, args: dict, op_name: str, path: Path) -> None:
        if op in (EffectOp.DAMAGE_TARGET, EffectOp.HEAL_TARGET):
            self._require_numeric(args, "amount", op_name, path)
        elif op == EffectOp.DRAW_CARDS:
            self._require_numeric(args, "count", op_name, path)
        elif op == EffectOp.GAIN_RESOURCE:
            self._require_numeric(args, "amount", op_name, path)
        elif op == EffectOp.BUFF_STAT:
            attribute = args.get("attribute")
            if attribute not in _VALID_BUFF_ATTRIBUTES:
                raise CardDefinitionError(f"efeito 'buff_stat' com 'attribute' desconhecido '{attribute}' em {path}")
            operation = args.get("operation")
            if operation not in _VALID_BUFF_OPERATIONS:
                raise CardDefinitionError(f"efeito 'buff_stat' com 'operation' desconhecida '{operation}' em {path}")
            self._require_numeric(args, "magnitude", op_name, path)
        else:
            raise CardDefinitionError(f"EffectOp sem validacao de args implementada: {op}")

    @staticmethod
    def _require_numeric(args: dict, key: str, op_name: str, path: Path) -> None:
        value = args.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CardDefinitionError(
                f"efeito '{op_name}' sem argumento numerico obrigatorio '{key}' em {path}"
            )
