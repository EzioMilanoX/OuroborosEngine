# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Separa 'tempo de spawn' de 'tempo de acerto real' para spawners com antecedencia (approach)."""
from __future__ import annotations

from typing import Tuple

import numpy as np


def split_spawn_and_hit_schedules(
    scheduled_threats: np.ndarray, approach_seconds: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Recebe um `SCHEDULED_THREAT_DTYPE` (ou compativel) cujo
    `timestamp_seconds` representa o instante de ACERTO real (ex.: o
    onset musical detectado pelo pipeline offline), e devolve dois
    arrays paralelos, mesmo indice de linha::

        spawn_threats: copia de `scheduled_threats` com
            `timestamp_seconds` deslocado `approach_seconds` PARA TRAS
            (nunca abaixo de 0.0) -- pronto para ser passado como
            `scheduled_threats` a `RhythmSpawnerSystem`, cujo cursor
            dispara a CRIACAO da entidade quando esse tempo de spawn e
            alcancado.
        hit_times: copia do `timestamp_seconds` ORIGINAL (o instante de
            acerto real, sem deslocamento) -- passado como `hit_times`
            a `RhythmSpawnerSystem`, para sistemas posteriores
            (`NoteScrollSystem`, `JudgmentSystem`) saberem quando a
            nota deve de fato ser julgada.

    Sem essa separacao, uma entidade so nasceria no proprio instante do
    acerto (spawn-time == hit-time), sem nenhum tempo de reacao/scroll
    visivel para o jogador -- exatamente o bug que este helper existe
    para evitar. Nenhum dos dois arrays retornados alias-eia
    `scheduled_threats` (ambos sao copias); o array de entrada nunca e
    mutado.
    """
    hit_times = scheduled_threats["timestamp_seconds"].copy()
    spawn_threats = scheduled_threats.copy()
    np.subtract(spawn_threats["timestamp_seconds"], approach_seconds, out=spawn_threats["timestamp_seconds"])
    np.maximum(spawn_threats["timestamp_seconds"], 0.0, out=spawn_threats["timestamp_seconds"])
    return spawn_threats, hit_times
