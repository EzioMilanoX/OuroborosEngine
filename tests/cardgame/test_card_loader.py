# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de CardLoader (Pilar 3): carga real de data/cards e validacao de arquivos malformados."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.cardgame.cards.card_loader import CardDefinitionError, CardLoader
from ouroboros.cardgame.cards.schemas import CardType
from ouroboros.cardgame.effects.schemas import EffectOp
from ouroboros.core.stable_id import stable_id_from_name

_REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_CARDS_DIR = _REPO_ROOT / "data" / "cards"


def test_load_all_reads_the_real_catalog() -> None:
    loader = CardLoader(REAL_CARDS_DIR)
    definitions = loader.load_all()

    assert len(definitions) == 7
    strike_id = stable_id_from_name("strike")
    assert strike_id in definitions
    assert definitions[strike_id].display_name == "Investida"
    assert definitions[strike_id].card_type == CardType.ACTION
    assert definitions[strike_id].effects[0].op == EffectOp.DAMAGE_TARGET


def test_load_all_reads_a_creature_definition() -> None:
    loader = CardLoader(REAL_CARDS_DIR)
    definitions = loader.load_all()
    warrior_id = stable_id_from_name("warrior")

    assert definitions[warrior_id].card_type == CardType.CREATURE
    assert definitions[warrior_id].base_attack == 3
    assert definitions[warrior_id].effects == ()


def test_load_all_reads_the_buff_stat_effect_args() -> None:
    loader = CardLoader(REAL_CARDS_DIR)
    definitions = loader.load_all()
    war_cry_id = stable_id_from_name("war_cry")

    effect = definitions[war_cry_id].effects[0]
    assert effect.op == EffectOp.BUFF_STAT
    assert dict(effect.args) == {"attribute": "attack", "operation": "flat", "magnitude": 2}


def _write(tmp_path: Path, filename: str, data: dict) -> Path:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir(exist_ok=True)
    (cards_dir / filename).write_text(json.dumps(data), encoding="utf-8")
    return cards_dir


def test_missing_required_field_raises(tmp_path: Path) -> None:
    cards_dir = _write(tmp_path, "broken.json", {"id": "broken", "display_name": "Broken"})
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_unknown_card_type_raises(tmp_path: Path) -> None:
    cards_dir = _write(
        tmp_path, "broken.json",
        {"id": "broken", "display_name": "Broken", "cost": 1, "card_type": "spell"},
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_creature_without_base_attack_raises(tmp_path: Path) -> None:
    cards_dir = _write(
        tmp_path, "broken.json",
        {"id": "broken", "display_name": "Broken", "cost": 1, "card_type": "creature"},
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_unknown_effect_op_raises(tmp_path: Path) -> None:
    cards_dir = _write(
        tmp_path, "broken.json",
        {
            "id": "broken", "display_name": "Broken", "cost": 1, "card_type": "action",
            "effects": [{"op": "smite", "args": {}}],
        },
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_damage_target_effect_missing_amount_raises(tmp_path: Path) -> None:
    cards_dir = _write(
        tmp_path, "broken.json",
        {
            "id": "broken", "display_name": "Broken", "cost": 1, "card_type": "action",
            "effects": [{"op": "damage_target", "args": {}}],
        },
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_damage_target_effect_with_boolean_amount_raises(tmp_path: Path) -> None:
    """`bool` e subclasse de `int` em Python -- sem a exclusao explicita
    em `CardLoader._require_numeric`, `{"amount": true}` passaria
    despercebido pela validacao numerica."""
    cards_dir = _write(
        tmp_path, "broken.json",
        {
            "id": "broken", "display_name": "Broken", "cost": 1, "card_type": "action",
            "effects": [{"op": "damage_target", "args": {"amount": True}}],
        },
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_buff_stat_with_unknown_attribute_raises(tmp_path: Path) -> None:
    cards_dir = _write(
        tmp_path, "broken.json",
        {
            "id": "broken", "display_name": "Broken", "cost": 1, "card_type": "action",
            "effects": [{"op": "buff_stat", "args": {"attribute": "defense", "operation": "flat", "magnitude": 1}}],
        },
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_buff_stat_with_unknown_operation_raises(tmp_path: Path) -> None:
    cards_dir = _write(
        tmp_path, "broken.json",
        {
            "id": "broken", "display_name": "Broken", "cost": 1, "card_type": "action",
            "effects": [{"op": "buff_stat", "args": {"attribute": "attack", "operation": "subtract", "magnitude": 1}}],
        },
    )
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_duplicate_id_raises(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "a.json").write_text(
        json.dumps({"id": "dup", "display_name": "Dup A", "cost": 1, "card_type": "action"}), encoding="utf-8"
    )
    (cards_dir / "b.json").write_text(
        json.dumps({"id": "dup", "display_name": "Dup B", "cost": 1, "card_type": "action"}), encoding="utf-8"
    )

    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()


def test_empty_directory_raises(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    with pytest.raises(CardDefinitionError):
        CardLoader(cards_dir).load_all()
