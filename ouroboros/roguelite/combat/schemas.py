# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Schema SoA de HP/dano de contato (ROADMAP M6), compartilhado por jogador/inimigo/projetil."""
from __future__ import annotations

from enum import IntEnum

import numpy as np


class EntityKind(IntEnum):
    """Discrimina o PAPEL da linha de `HEALTH_DTYPE` -- contrato estavel, nunca renumerar.

    Necessario porque `MemoryManager` reaproveita uma unica free-list de indices GLOBAL
    entre arquetipos: o `entity_index` de um inimigo morto pode ser reciclado por um
    projetil futuro em qualquer frame seguinte. Sem este campo, um sistema que guardasse
    "quais indices sao inimigos" a parte (numa lista Python, por exemplo) arriscaria
    contar esse projetil reciclado como "o inimigo ainda vivo" -- um bug de corrupcao
    silenciosa, nao hipotetico (ver `DamageOnCollisionSystem`/`EnemyChaseSystem`, que
    resolvem "quem e inimigo agora" sempre consultando este campo no dado atual, nunca
    um indice bruto cacheado a parte)."""

    PLAYER = 0
    ENEMY = 1
    PROJECTILE = 2


HEALTH_DTYPE: np.dtype = np.dtype([
    ("entity_kind", np.int8),
    ("current_hp", np.float32),
    ("max_hp", np.float32),
    ("contact_damage", np.float32),
    ("destroy_on_hit", np.bool_),
])
"""Schema de HP/dano-de-contato de UMA entidade, compartilhado por jogador/inimigo/
projetil (mesmo idioma ja aceito de `HITBOX_DTYPE`, um schema generico usado por
qualquer papel de entidade).

Campos:
    entity_kind: ver `EntityKind`.
    current_hp/max_hp: irrelevantes/nao usados por projeteis (nada jamais causa dano A
        um projetil -- as mascaras de colisao garantem que projetil so colide com
        inimigo, nunca com outro projetil nem com quem o disparou).
    contact_damage: dano causado a quem colidir com esta entidade (`0.0` = nao causa
        dano por contato -- ex.: o jogador nesta v1, que so causa dano via projetil).
    destroy_on_hit: `True` para projeteis (consumidos ao acertar, independente de
        `current_hp`); `False` para jogador/inimigo (que so morrem por `current_hp <= 0`).
"""
