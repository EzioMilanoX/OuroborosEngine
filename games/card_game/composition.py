# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao do Card Game: monta o catalogo, o baralho hardcoded, e a MatchScene por cima do CompositionRoot generico."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, Optional, Tuple

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.cardgame.cards.card_loader import CardLoader
from ouroboros.cardgame.cards.schemas import CardDefinition, CardType
from ouroboros.cardgame.effects.resolver import PlayerState
from ouroboros.cardgame.effects.schemas import EffectOp
from ouroboros.cardgame.zones import CardInstance, Zone
from ouroboros.core.modifiers.modifier_stack import ModifierStack

from games.card_game.match_scene import MatchScene

_GAME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GAME_DIR.parent.parent
CARDS_DIR = _REPO_ROOT / "data" / "cards"

PLAYER_STARTING_HP = 20.0
OPPONENT_STARTING_HP = 15.0
OPENING_HAND_SIZE = 3

# Baralho hardcoded (1 baralho nao justifica um builder/UI de deck ainda --
# ver ROADMAP M14, "fora de escopo"): 15 copias no total, contagem por
# card_id original do JSON (nao card_def_id -- resolvido contra o catalogo
# dentro de build_game).
DECK_LIST: Tuple[Tuple[str, int], ...] = (
    ("strike", 3),
    ("fireball", 2),
    ("minor_heal", 2),
    ("inspiration", 2),
    ("war_cry", 1),
    ("warrior", 3),
    ("archer", 2),
)


def _build_deck(definitions_by_card_id: Dict[str, CardDefinition], rng: random.Random) -> Zone:
    """Monta e embaralha o deck a partir de `DECK_LIST`."""
    deck = Zone("deck")
    next_instance_id = 0
    for card_id, count in DECK_LIST:
        definition = definitions_by_card_id[card_id]
        for _ in range(count):
            deck.cards.append(CardInstance(instance_id=next_instance_id, card_def_id=definition.card_def_id))
            next_instance_id += 1
    deck.shuffle(rng)
    return deck


def _compute_modifier_stack_capacity(definitions_by_card_id: Dict[str, CardDefinition]) -> Tuple[int, int]:
    """Dimensiona `ModifierStack` a partir da composicao REAL do baralho
    (nao da contagem de `CardDefinition` distintas): como nenhuma criatura
    e removida do campo e nenhum efeito de remocao de buff existe no
    vocabulario do v1 (ver ROADMAP M14), tanto atributos quanto entradas
    se acumulam para sempre ao longo de uma partida -- `attribute_capacity`
    precisa cobrir toda copia de CREATURE que possa vir a ser jogada, e
    `entry_capacity` precisa cobrir o pior caso de toda copia de carta
    BUFF_STAT empurrando um modificador em CADA criatura ja em campo."""
    creature_copy_count = 0
    buff_stat_copy_count = 0
    for card_id, count in DECK_LIST:
        definition = definitions_by_card_id[card_id]
        if definition.card_type == CardType.CREATURE:
            creature_copy_count += count
        elif any(effect.op == EffectOp.BUFF_STAT for effect in definition.effects):
            buff_stat_copy_count += count

    attribute_capacity = max(1, creature_copy_count)
    entry_capacity = max(1, attribute_capacity * buff_stat_copy_count)
    return attribute_capacity, entry_capacity


def build_game(config: EngineConfig, rng: Optional[random.Random] = None) -> GameLoop:
    """
    Monta o Card Game completo: carrega o catalogo (`CardLoader`), monta e
    embaralha o baralho hardcoded (`DECK_LIST`), dimensiona e constroi o
    `ModifierStack` compartilhado da partida, monta os dois
    `PlayerState` (jogador real + oponente estatico/sem IA -- ver
    docstring de `PlayerState`), compra a mao de abertura, e substitui a
    pilha de cenas por uma `MatchScene` ANTES do primeiro frame (mesmo
    truque de `MenuScene`/Platformer/Tactics -- a `GameplayScene` base
    nunca chega a rodar, ja que `MatchScene` nunca chama `world.step()`).

    `rng`: opcional, injetavel para determinismo em teste (`random.Random`
    semeado); `None` (default, jogo real) usa um `random.Random()` sem
    semente.
    """
    game_loop = CompositionRoot(config).build()

    definitions_by_id = CardLoader(CARDS_DIR).load_all()
    definitions_by_card_id = {definition.card_id: definition for definition in definitions_by_id.values()}

    deck = _build_deck(definitions_by_card_id, rng if rng is not None else random.Random())

    attribute_capacity, entry_capacity = _compute_modifier_stack_capacity(definitions_by_card_id)
    modifier_stack = ModifierStack(attribute_capacity=attribute_capacity, entry_capacity=entry_capacity)

    player = PlayerState(
        name="Voce",
        hp=PLAYER_STARTING_HP,
        max_hp=PLAYER_STARTING_HP,
        mana=0,
        max_mana=0,
        deck=deck,
        hand=Zone("hand"),
        discard=Zone("discard"),
        battlefield=Zone("battlefield"),
    )
    opponent = PlayerState(
        name="Oponente",
        hp=OPPONENT_STARTING_HP,
        max_hp=OPPONENT_STARTING_HP,
        mana=0,
        max_mana=0,
        deck=Zone("opponent_deck"),
        hand=Zone("opponent_hand"),
        discard=Zone("opponent_discard"),
        battlefield=Zone("opponent_battlefield"),
    )

    player.deck.move_top_to(player.hand, count=OPENING_HAND_SIZE)

    match_scene = MatchScene(
        input_provider=game_loop.input_provider,
        game_loop=game_loop,
        definitions=definitions_by_id,
        modifier_stack=modifier_stack,
        player=player,
        opponent=opponent,
        viewport_size=(config.window_width, config.window_height),
    )
    game_loop.reset_scenes(match_scene)

    return game_loop
