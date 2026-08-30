# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Definicao de carta (template de catalogo, imutavel) e do efeito que ela resolve."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping, Tuple


class CardType(IntEnum):
    ACTION = 0
    CREATURE = 1


@dataclass(frozen=True)
class CardEffect:
    """Uma operacao de efeito (`EffectOp`) + seus argumentos.

    `args` e deliberadamente `Mapping[str, object]` (tipos mistos) -- ex.:
    BUFF_STAT mistura strings (`"attribute"`, `"operation"`) e float
    (`"magnitude"`) no mesmo dict. Ja validado integralmente por
    `CardLoader` no carregamento (ver `_validate_args`); `apply_effect`
    nunca precisa validar de novo em runtime.
    """

    op: int
    args: Mapping[str, object]


@dataclass(frozen=True)
class CardDefinition:
    """Template de carta (catalogo, imutavel, uma linha por `id` unico do
    JSON) -- NUNCA confundir com uma `CardInstance` (copia especifica
    dentro de uma `Zone`, ver `ouroboros.cardgame.zones`). Varias
    `CardInstance` no mesmo baralho compartilham o mesmo `CardDefinition`.

    `base_attack`: relevante APENAS para `CREATURE` (sempre `0` para
    `ACTION`) -- creatures neste v1 nao tem HP/defesa propria (nada as
    danifica depois de jogadas, ver ROADMAP M14 "fora de escopo: combate
    criatura-vs-criatura com bloqueio"): sao fontes permanentes de ataque
    que disparam no campo a cada fase de combate.
    `effects`: relevante APENAS para `ACTION` (sempre vazio para
    `CREATURE`) -- resolve imediatamente ao jogar a carta.
    """

    card_def_id: int
    card_id: str
    display_name: str
    cost: int
    card_type: int
    base_attack: int
    effects: Tuple[CardEffect, ...]
