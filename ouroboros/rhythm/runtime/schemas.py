"""Schema SoA de uma ameaca pre-agendada (materializado pelo BeatmapLoader)."""
from __future__ import annotations

import numpy as np

SCHEDULED_THREAT_DTYPE: np.dtype = np.dtype(
    [
        ("timestamp_seconds", np.float64),
        ("threat_type", np.int16),
        ("lane", np.int8),
        ("strength", np.float32),
        ("layer", np.int8),
        ("has_spawned", np.bool_),
    ]
)
"""Schema de UMA ameaca pre-agendada, materializada em array contiguo
pelo `BeatmapLoader` a partir de `beatmap.json`.

Campos:
    timestamp_seconds: instante de disparo, relativo ao inicio da
        reproducao da faixa (mesma base de tempo de
        `IAudioClock.now_seconds`).
    threat_type: tipo de ameaca, mapeado de string (JSON) para inteiro
        pelo `BeatmapLoader` no momento do carregamento.
    lane: indice de lane/pista onde a ameaca deve aparecer.
    strength: intensidade normalizada (`0.0`-`1.0`).
    layer: camada de extracao (Perfis de Extracao multi-layer), mapeada
        de string opcional do JSON ("" -> 0, "kick" -> 0, "vocal" -> 1
        por padrao) para inteiro pelo `BeatmapLoader`. Produtos roteiam
        o spawn por ela (ex.: kicks nas extremidades, vocais no centro).
    has_spawned: flag de TELEMETRIA/depuracao apenas -- espelha se o
        evento ja foi disparado, mas NAO e a fonte de verdade de
        idempotencia do runtime. A fonte de verdade e o cursor inteiro
        `RhythmSpawnerSystem._next_pending_index`; este campo existe so
        para inspecao externa (ex.: overlay de debug), nunca e lido por
        `RhythmSpawnerSystem` para decidir o que disparar.
"""
