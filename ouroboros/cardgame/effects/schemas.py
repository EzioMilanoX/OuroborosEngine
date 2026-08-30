# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Vocabulario fechado de operacoes de efeito de carta (ROADMAP M14)."""
from __future__ import annotations

from enum import IntEnum


class EffectOp(IntEnum):
    """Codigos de operacao de efeito de carta -- vocabulario FECHADO e
    pequeno, nao scripting arbitrario de carta (ver ROADMAP M14, "fora de
    escopo"). Assim como `ModifierOperation`, um valor existente nunca deve
    ser renumerado.

    Alvo de cada operacao e FIXO/implicito, resolvido por
    `ouroboros.cardgame.effects.resolver.apply_effect` -- nao ha selecao de
    alvo pelo jogador em nenhuma delas:
        DAMAGE_TARGET: sempre atinge o HP do OPONENTE de quem jogou a carta.
        HEAL_TARGET: sempre cura o HP de quem jogou a carta.
        DRAW_CARDS: sempre compra do proprio deck de quem jogou a carta.
        BUFF_STAT: sempre empurra um modificador em TODAS as criaturas
            atualmente no campo de quem jogou a carta.
        GAIN_RESOURCE: sempre aumenta a mana de quem jogou a carta.
    """

    DAMAGE_TARGET = 0
    HEAL_TARGET = 1
    DRAW_CARDS = 2
    BUFF_STAT = 3
    GAIN_RESOURCE = 4
