# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Resolve um CardEffect contra o estado de partida -- dispatcher plano, sem scripting arbitrario."""
from __future__ import annotations

from dataclasses import dataclass

from ouroboros.cardgame.cards.schemas import CardEffect
from ouroboros.cardgame.effects.schemas import EffectOp
from ouroboros.cardgame.zones import Zone
from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.core.modifiers.schemas import ModifierOperation

_MODIFIER_OPERATION_BY_NAME = {
    "flat": ModifierOperation.FLAT,
    "percent_add": ModifierOperation.PERCENT_ADD,
    "percent_mult": ModifierOperation.PERCENT_MULT,
}


@dataclass
class PlayerState:
    """Estado de um lado da partida (HP/mana/zonas).

    Usado tanto para o jogador real quanto para o oponente estatico/sem
    IA do v1 (ver ROADMAP M14): as zonas do oponente simplesmente
    permanecem vazias para sempre e sua `mana` nunca e lida -- tradeoff
    deliberado de uniformidade de interface (uma partida real de 2 lados
    no futuro so precisaria popula-las) em vez de um tipo mais enxuto
    exclusivo do oponente."""

    name: str
    hp: float
    max_hp: float
    mana: int
    max_mana: int
    deck: Zone
    hand: Zone
    discard: Zone
    battlefield: Zone


def apply_effect(effect: CardEffect, caster: PlayerState, opponent: PlayerState, modifier_stack: ModifierStack) -> None:
    """Resolve `effect` contra `caster`/`opponent`. Alvo de cada operacao
    e FIXO/implicito (ver docstring de `EffectOp`) -- nao ha selecao de
    alvo pelo jogador.

    NAO chama `modifier_stack.recompute_all()` -- responsabilidade do
    chamador (`MatchScene`, que roda sem nenhum `ISystem`/`world.step()`
    orientando isso; ver `ModifierStack.recompute_all` docstring)."""
    op = EffectOp(effect.op)
    if op == EffectOp.DAMAGE_TARGET:
        opponent.hp = max(0.0, opponent.hp - float(effect.args["amount"]))
    elif op == EffectOp.HEAL_TARGET:
        caster.hp = min(caster.max_hp, caster.hp + float(effect.args["amount"]))
    elif op == EffectOp.DRAW_CARDS:
        caster.deck.move_top_to(caster.hand, count=int(effect.args["count"]))
    elif op == EffectOp.GAIN_RESOURCE:
        caster.mana += int(effect.args["amount"])
    elif op == EffectOp.BUFF_STAT:
        operation = _MODIFIER_OPERATION_BY_NAME[str(effect.args["operation"])]
        magnitude = float(effect.args["magnitude"])
        for creature in caster.battlefield.cards:
            if creature.attack_attribute_index is not None:
                modifier_stack.push(creature.attack_attribute_index, operation, magnitude, creature.instance_id)
    else:
        raise ValueError(f"EffectOp desconhecido: {effect.op}")
