# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Schema SoA de uma ameaca pre-agendada (materializado pelo BeatmapLoader)."""
from __future__ import annotations

from enum import IntEnum

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
        ("layer", np.int8),
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
    layer: copiado de `SCHEDULED_THREAT_DTYPE['layer']` no momento do
        spawn (ROADMAP M11.4) -- permite a `JudgmentSystem` saber a
        camada de extracao da nota no momento do julgamento (hit/miss),
        para influenciar feedback visual/sonoro por camada, sem precisar
        de um caminho de volta pra `scheduled_threats` (mesmo motivo de
        `timestamp_seconds` acima).

Diferenca deliberada de `DungeonStreamingSystem.ROOM_INSTANCE_DTYPE`
(Pilar 3): aquela e uma `ComponentPool` PRIVADA do proprio sistema,
enderecada por um `room_id` de dominio, nunca registrada no `World` nem
parte de nenhum arquetipo. Esta pool (`note_state`) e, ao contrario,
uma pool COMPARTILHADA e registrada no `World`, parte do arquetipo da
propria nota -- anexada/desanexada automaticamente por
`World.create_entity`/`destroy_entity` junto de `transform`/`sprite`/
`lane`/`threat_type`. A motivacao (evitar reconstruir um handle a partir
de so um indice) e a mesma; o mecanismo nao e."""


class OsuObjectKind(IntEnum):
    """Tipo de hit-object do modo Osu! (ROADMAP M15) -- contrato estavel
    (como `Judgment`/`ModifierOperation`): um valor existente nunca deve
    ser renumerado."""

    CIRCLE = 0
    SLIDER = 1


OSU_SCHEDULED_HIT_DTYPE: np.dtype = np.dtype(
    [
        ("timestamp_seconds", np.float64),
        ("threat_type", np.int16),
        ("x", np.float32),
        ("y", np.float32),
        ("end_x", np.float32),
        ("end_y", np.float32),
        ("duration_seconds", np.float32),
        ("strength", np.float32),
        ("layer", np.int8),
        ("has_spawned", np.bool_),
    ]
)
"""Schema de UM hit-object pre-agendado do modo Osu! (ROADMAP M15),
materializado pelo `OsuBeatmapLoader` a partir de `*.beatmap.json` --
schema PARALELO a `SCHEDULED_THREAT_DTYPE` (nao uma extensao dela): o
modo lane e o modo Osu! nao compartilham nenhum caminho de codigo em
runtime, so o formato NEUTRO de beatmap (`ouroboros.rhythm.
beatmap_format`).

Campos:
    timestamp_seconds: instante de disparo (CIRCLE) ou instante em que
        o jogador deve iniciar o arraste (SLIDER, cabeca) -- mesma base
        de tempo de `IAudioClock.now_seconds`.
    threat_type: um dos valores de `OsuObjectKind`, mapeado de string
        (JSON) para inteiro pelo `OsuBeatmapLoader` no momento do
        carregamento -- mesmo idioma de `SCHEDULED_THREAT_DTYPE.threat_type`.
    x, y: posicao da CABECA do hit-object, em pixels de tela.
    end_x, end_y: posicao da CAUDA (SLIDER apenas -- `0.0` para CIRCLE).
        Trajeto v1 e sempre uma RETA entre `(x,y)` e `(end_x,end_y)`,
        sem polyline/Bezier (ver ROADMAP M15, "fora de escopo").
    duration_seconds: duracao do arraste (SLIDER apenas -- `0.0` para
        CIRCLE).
    strength: intensidade normalizada (`0.0`-`1.0`), copiada do beatmap
        lane-mode de origem (nao recalculada).
    layer: camada de extracao, mesmo idioma de `SCHEDULED_THREAT_DTYPE.layer`.
    has_spawned: flag de TELEMETRIA/depuracao apenas -- mesma ressalva
        de `SCHEDULED_THREAT_DTYPE.has_spawned` (nunca lida por
        `OsuSpawnerSystem` para decidir o que disparar).
"""

OSU_NOTE_STATE_DTYPE: np.dtype = np.dtype(
    [
        ("timestamp_seconds", np.float64),
        ("packed_entity_id", np.uint64),
        ("layer", np.int8),
        ("object_kind", np.int8),
        ("x", np.float32),
        ("y", np.float32),
        ("end_x", np.float32),
        ("end_y", np.float32),
        ("duration_seconds", np.float32),
        ("ring_entity_id", np.uint64),
        ("ball_entity_id", np.uint64),
        ("is_tracking", np.bool_),
        ("tracked_time_seconds", np.float32),
        ("good_time_seconds", np.float32),
    ]
)
"""Schema de UM registro por-entidade de hit-object Osu! ja
instanciado (SoA), escrito por `OsuSpawnerSystem` no momento do spawn e
consumido por `OsuPresentationSystem`/`OsuJudgmentSystem`. Schema
PARALELO a `NOTE_STATE_DTYPE` (nao uma extensao dela) -- deliberadamente
sem campo `lane` (nao existe no modo Osu!).

Campos exclusivos deste schema (os demais espelham `NOTE_STATE_DTYPE`):
    object_kind: copia de `OSU_SCHEDULED_HIT_DTYPE.threat_type` (um
        `OsuObjectKind`) -- nomeado diferente aqui deliberadamente: no
        JSON/loader e "que tipo de evento agendado" (mesmo conceito de
        `threat_type`); aqui, ja mapeado para inteiro, e simplesmente
        "que tipo de hit-object e este", um nome mais claro sem custo.
    x, y, end_x, end_y, duration_seconds: copiados de
        `OSU_SCHEDULED_HIT_DTYPE` no momento do spawn -- mesmo motivo de
        `NOTE_STATE_DTYPE.timestamp_seconds` (nenhum caminho de volta de
        "entidade -> linha original" apos o spawn).
    ring_entity_id, ball_entity_id: `PackedEntityId` das entidades
        COMPANHEIRAS puramente visuais (anel de aproximacao / bola de
        slider, arquetipo `osu_visual_marker`), ou `NULL_PACKED_HANDLE`
        (`ouroboros.core.memory.handles`) quando nao existe uma
        companheira (`ball_entity_id` para um CIRCLE, ou qualquer um
        dos dois apos a companheira ja ter sido destruida). ESTE campo
        DEVE ser escrito de volta para `NULL_PACKED_HANDLE` no EXATO
        momento em que a entidade companheira e destruida (nunca
        deixado com o handle antigo ate a proxima leitura) -- `World.
        destroy_entity` e DIFERIDO e `MemoryManager` recicla indices
        livres em ordem LIFO, entao um handle obsoleto aqui seria
        rapidamente reaproveitado por uma entidade NOVA e nao-relacionada,
        e `ComponentPool.dense_row_of` nao faz nenhuma checagem de
        geracao -- ler um `ring_entity_id`/`ball_entity_id` obsoleto
        escreveria silenciosamente no transform de uma entidade errada.
        Todo leitor vetorizado (`OsuPresentationSystem`) DEVE mascarar
        `!= NULL_PACKED_HANDLE` ANTES de resolver via `unpack_batch` --
        `NULL_PACKED_HANDLE` empacota `index = INVALID_ENTITY_INDEX`
        (`-1`), que via mascara de bits vira `0xFFFFFFFF` (um indice
        positivo enorme, NAO `-1`) -- resolver isso sem mascarar antes
        estoura `IndexError` no primeiro frame com qualquer CIRCLE
        (cujo `ball_entity_id` e sempre o sentinela).
    is_tracking: `True` a partir do clique inicial num SLIDER ate ele
        ser resolvido (sempre `False` para CIRCLE, e para um SLIDER
        ainda nao clicado).
    tracked_time_seconds, good_time_seconds: acumuladores PONDERADOS
        POR TEMPO (segundos reais de `delta_time`, nunca contagem de
        frames) de quanto tempo um SLIDER em tracking teve o cursor
        dentro do raio de tolerancia enquanto o botao permanecia
        pressionado -- ponderar por CONTAGEM DE FRAMES em vez de tempo
        enviesaria a fracao final pela taxa de quadros (uma maquina mais
        lenta puniria o MESMO comportamento fisico do jogador com mais
        peso por frame perdido). `good_time_seconds / tracked_time_seconds`
        e a fracao usada por `OsuJudgmentSystem._classify_slider` ao
        resolver o julgamento final do slider.
"""
