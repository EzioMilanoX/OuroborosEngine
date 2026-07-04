"""Recalcula final_value de todas as ModifierStack registradas, a cada frame."""
from __future__ import annotations

from typing import Tuple

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.roguelite.modifiers.modifier_stack import ModifierStack


class ModifierApplicationSystem(ISystem):
    """Recalcula `final_value` de todas as `ModifierStack` registradas, a cada frame.

    Mantem uma tupla FIXA de `ModifierStack` (ex.: uma para atributos de
    personagem, outra para atributos de arma), definida no construtor e
    nunca alterada em `update()`. Cada `ModifierStack` ja possui seus
    proprios buffers de scratch pre-alocados (ver
    `ModifierStack.__init__`), entao este sistema em si nao aloca --
    apenas orquestra a chamada vetorizada de `recompute_all()` por
    stack, na ordem fixa de registro.
    """

    def __init__(self, modifier_stacks: Tuple[ModifierStack, ...]) -> None:
        """Guarda as `ModifierStack` a recalcular a cada `update()`."""
        self._modifier_stacks = tuple(modifier_stacks)

    def update(self, world: World, delta_time: float) -> None:
        """Chama `recompute_all()` em cada `ModifierStack` registrada,
        na ordem de registro. Ignora `delta_time`: a recomputacao de
        modificadores e idempotente e deve sempre refletir o estado ATUAL
        das entradas ativas, nao uma integracao ao longo do tempo.
        """
        del world, delta_time
        for modifier_stack in self._modifier_stacks:
            modifier_stack.recompute_all()
