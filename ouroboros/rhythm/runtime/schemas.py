# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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

NOTE_STATE_DTYPE: np.dtype = np.dtype(
    [
        ("timestamp_seconds", np.float64),
        ("packed_entity_id", np.uint64),
    ]
)
"""Schema de UM registro por-entidade de nota ja instanciada (SoA),
opcionalmente escrito por `RhythmSpawnerSystem` (via `note_state_pool_name`)
no momento do spawn, e consumido por `NoteScrollSystem`/`JudgmentSystem`.

Campos:
    timestamp_seconds: o instante de disparo desta nota especifica,
        copiado de `SCHEDULED_THREAT_DTYPE['timestamp_seconds']` no
        momento do spawn -- permite a sistemas posteriores (scroll,
        julgamento) saber o tempo-alvo de UMA entidade sem precisar
        re-consultar o array estatico `scheduled_threats` (que nao tem
        um caminho de volta de "entidade -> linha original" apos o
        spawn, ja que `World.create_entity` reaproveita indices de uma
        free-list, nao em ordem monotonica).
    packed_entity_id: o `PackedEntityId` (int primitivo de 64 bits) da
        propria entidade, capturado no momento do spawn -- necessario
        porque `MemoryManager` nao expoe um jeito publico de reconstruir
        um handle valido a partir apenas de um indice de entidade
        (`entity_index`); sem isso, sistemas que descobrem uma entidade
        via `ComponentPool.active_entity_indices()` nao teriam como
        chamar `World.destroy_entity()` nela.

Diferenca deliberada de `DungeonStreamingSystem.ROOM_INSTANCE_DTYPE`
(Pilar 3): aquela e uma `ComponentPool` PRIVADA do proprio sistema,
enderecada por um `room_id` de dominio, nunca registrada no `World` nem
parte de nenhum arquetipo. Esta pool (`note_state`) e, ao contrario,
uma pool COMPARTILHADA e registrada no `World`, parte do arquetipo da
propria nota -- anexada/desanexada automaticamente por
`World.create_entity`/`destroy_entity` junto de `transform`/`sprite`/
`lane`/`threat_type`. A motivacao (evitar reconstruir um handle a partir
de so um indice) e a mesma; o mecanismo nao e."""
