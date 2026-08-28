"""Schema SoA da direcao de mira do jogador -- produto-especifico, nao um pilar (ainda)."""
from __future__ import annotations

import numpy as np

FACING_DTYPE: np.dtype = np.dtype([
    ("facing_x", np.float32),
    ("facing_y", np.float32),
])
"""Ultima direcao NAO-NULA de movimento do jogador (persiste enquanto parado).
`PlayerMovementSystem` escreve; `WeaponFireSystem` le -- comunicacao via pool
compartilhada, mesmo idioma de `NoteScrollSystem`/`JudgmentSystem` (Pilar 4),
que se comunicam via a pool `note_state`, nunca uma referencia direta entre
sistemas."""
