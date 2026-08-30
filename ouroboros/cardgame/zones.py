# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Zonas de jogo (deck/mao/descarte/campo) e instancias de carta.

Deliberadamente listas Python puras, NAO `ComponentPool`/ECS: o volume de
cartas em jogo (dezenas, mutado por evento discreto de turno, nao por
frame) e o oposto do que o Pilar 1 foi feito para otimizar (ver ROADMAP
M14)."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional


@dataclass(eq=False)
class CardInstance:
    """Uma copia especifica de uma carta, residente em alguma `Zone`.

    NUNCA confundir `instance_id` (unico por copia, usado como
    `source_id` em `ModifierStack.push`) com `card_def_id` (template
    compartilhado por TODAS as copias da mesma carta) -- usar
    `card_def_id` como `source_id` repetiria o bug que
    `MODIFIER_ENTRY_DTYPE.source_id`/`WeaponLoader.materialize` alertam
    explicitamente contra: um buff em uma copia vazaria para todas as
    outras copias da mesma definicao.

    `attack_attribute_index`: `None` ate esta instancia (se for
    `CREATURE`) entrar em campo -- so entao um atributo e registrado no
    `ModifierStack` compartilhado da partida (ver `MatchScene`).

    `eq=False`: usa identidade de objeto (nao igualdade por campo) --
    necessario para que `Zone.move_specific_to`/`list.remove` localizem
    exatamente a copia pretendida numa lista que pode conter varias
    copias com os mesmos valores de campo (2 copias da mesma carta, ainda
    sem `attack_attribute_index`, seriam indistinguiveis por valor)."""

    instance_id: int
    card_def_id: int
    attack_attribute_index: Optional[int] = None


class Zone:
    """Uma pilha ordenada de `CardInstance` (deck, mao, descarte, ou
    campo). "Topo" = fim da lista (`cards[-1]`) -- comprar sempre atua no
    topo; jogar uma carta especifica de dentro da mao usa
    `move_specific_to` (nao precisa ser a do topo)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.cards: List[CardInstance] = []

    def draw_top(self, count: int = 1) -> List[CardInstance]:
        """Remove ate `count` cartas do topo (fim da lista) e as retorna,
        na ordem em que saem. NUNCA levanta -- se a zona esvaziar antes de
        `count`, retorna uma lista mais curta (contrato de "sem fadiga" do
        v1, ver ROADMAP M14: comprar de um deck vazio simplesmente nao
        adiciona carta nenhuma, sem dano de penalidade)."""
        drawn: List[CardInstance] = []
        for _ in range(count):
            if not self.cards:
                break
            drawn.append(self.cards.pop())
        return drawn

    def move_top_to(self, other: "Zone", count: int = 1) -> List[CardInstance]:
        """`draw_top(count)` desta zona, anexado ao topo de `other`."""
        moved = self.draw_top(count)
        other.cards.extend(moved)
        return moved

    def move_specific_to(self, instance: CardInstance, other: "Zone") -> None:
        """Remove `instance` (por IDENTIDADE, ver `CardInstance.eq=False`)
        desta zona e a anexa ao topo de `other`."""
        self.cards.remove(instance)
        other.cards.append(instance)

    def shuffle(self, rng: random.Random) -> None:
        """Embaralha esta zona in-place via `rng` (injetado -- nao
        `StrictRandom`: fora do hot-path de gameplay, evento unico por
        partida, nao precisa de stream determinístico por proposito)."""
        rng.shuffle(self.cards)
