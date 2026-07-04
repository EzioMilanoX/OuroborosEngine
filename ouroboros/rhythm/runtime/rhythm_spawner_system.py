"""Dispara criacao de entidades de ameaca em sincronia com o audio real, via IAudioClock."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ouroboros.core.memory.handles import PackedEntityId, unpack_index
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock


class RhythmSpawnerSystem(ISystem):
    """Dispara a criacao de entidades de ameaca em sincronia com a
    reproducao de audio real, consultando um `IAudioClock` injetado --
    NUNCA o `delta_time` acumulado recebido por `update()`.

    SINCRONIA DE AUDIO E COMPENSACAO DE LATENCIA:
        A unica fonte de verdade de "que horas sao" e
        `self._audio_clock.now_seconds()`. O `delta_time` do
        parametro de `update()` e IGNORADO para decidir o que disparar
        -- jamais e acumulado em um relogio proprio. A cada `update()`,
        o tempo efetivo de comparacao e, SEM AMBIGUIDADE DE SINAL::

            effective_time = max(
                0.0,
                audio_clock.now_seconds() - audio_clock.get_output_latency_seconds(),
            )

        Subtrair `get_output_latency_seconds()` compensa o atraso entre
        o motor de audio decidir tocar um sample e esse sample
        efetivamente chegar ao alto-falante: `now_seconds()` reporta o
        tempo de reproducao no instante da consulta (que ja avancou mais
        rapido do que o que o jogador de fato ouviu), entao subtrair a
        latencia de saida ainda pendente resulta no instante que o
        jogador esta EFETIVAMENTE ouvindo -- e e esse instante que deve
        ser comparado aos timestamps do beatmap (calculados durante a
        analise offline, que nao conhece o hardware de saida do
        jogador). O `max(0.0, ...)` evita tempo efetivo negativo logo
        no inicio da faixa.

    IDEMPOTENCIA VIA CURSOR PRE-ALOCADO -- NUNCA UM `set()`:
        Os eventos do beatmap carregado por `BeatmapLoader` estao
        ordenados por `timestamp_seconds` em um unico array
        pre-alocado. Este sistema mantem um UNICO inteiro pre-alocado,
        `self._next_pending_index`, apontando para o PRIMEIRO evento
        ainda nao disparado -- NUNCA um `set()`/`dict` de "ids de
        eventos ja disparados". A cada `update()`:

            1. Busca vetorizada, via `np.searchsorted` (`side="right"`)
               aplicada a fatia `timestamps[self._next_pending_index:]`,
               do maior deslocamento `k` tal que todos os elementos
               `timestamps[self._next_pending_index : self._next_pending_index + k]`
               sejam `<= effective_time`.
            2. Todo o intervalo de indices
               `[self._next_pending_index, self._next_pending_index + k)`
               e disparado nesta chamada, respeitando o limite opcional
               `max_threats_per_frame` (evita um pico de criacao de
               entidades caso o jogo tenha ficado pausado/atrasado por
               varios segundos).
            3. `self._next_pending_index` avanca exatamente pela
               quantidade de eventos EFETIVAMENTE disparados neste
               `update()` -- NUNCA decrementa. Se o limite de
               `max_threats_per_frame` truncar o lote devido nesta
               chamada, os eventos restantes permanecem pendentes e sao
               disparados em chamadas subsequentes (nenhuma ameaca e
               descartada silenciosamente por causa do limite).

        O cursor e MONOTONICO por construcao: mesmo que
        `effective_time` oscile ligeiramente para tras entre frames
        (ex.: pequena correcao de calibracao via
        `audio_clock.calibrate_latency`), a busca e sempre restrita a
        fatia a partir do cursor atual, entao um evento cujo indice ja
        ficou para tras do cursor jamais e reconsiderado -- cada evento e
        contabilizado exatamente uma vez, sem nenhuma estrutura de dados
        por evento.

    CICLO DE VIDA / REINICIO:
        `reset()` reposiciona o cursor para 0, permitindo reiniciar a
        mesma instancia de sistema para uma nova tentativa/replay da
        mesma faixa (morte do jogador, restart de fase) sem precisar
        reconstruir o sistema nem recarregar o beatmap do disco.

    Invariante Zero-GC dentro de `update()`: os `PackedEntityId`
    retornados por `world.create_entity()` sao inteiros primitivos --
    nenhum `EntityHandle` (`NamedTuple`) e construido neste metodo. O
    intervalo de eventos devidos e obtido inteiramente por slicing/
    aritmetica de indices inteiros sobre arrays NumPy pre-alocados, sem
    list comprehension nem `.append()` em loop quente.
    """

    def __init__(
        self,
        audio_clock: IAudioClock,
        scheduled_threats: np.ndarray,
        threat_archetype_name: str,
        lane_pool_name: str,
        threat_type_pool_name: str,
        max_threats_per_frame: Optional[int] = None,
    ) -> None:
        """Injeta o `IAudioClock` (referencia fixa, nunca trocada apos a
        construcao) e o array `SCHEDULED_THREAT_DTYPE` pre-carregado e
        ordenado (produzido por `BeatmapLoader.load`, fora do
        hot-path). `lane_pool_name`/`threat_type_pool_name` identificam
        as pools ESPECIFICAS do produto Rhythm (nao pools genericas como
        `hitbox`) onde os campos `lane`/`threat_type` de cada
        ameaca disparada sao escritos apos `create_entity`.

        Inicializa `self._next_pending_index = 0`.
        """
        self._audio_clock = audio_clock
        self._scheduled_threats = scheduled_threats
        self._threat_archetype_name = threat_archetype_name
        self._lane_pool_name = lane_pool_name
        self._threat_type_pool_name = threat_type_pool_name
        self._max_threats_per_frame = max_threats_per_frame
        self._next_pending_index = 0

    @property
    def next_pending_index(self) -> int:
        """Indice do proximo evento ainda nao disparado (telemetria/testes
        deterministicos; nunca mutado de fora).
        """
        return self._next_pending_index

    @property
    def is_finished(self) -> bool:
        """Verdadeiro quando `next_pending_index` alcancou o fim do
        array de eventos agendados (todos ja disparados).
        """
        return self._next_pending_index >= self._scheduled_threats.shape[0]

    def update(self, world: World, delta_time: float) -> None:
        """Dispara todos os eventos devidos desde a ultima chamada,
        consultando exclusivamente `self._audio_clock` (ver docstring
        da classe para a formula de compensacao de latencia e o
        mecanismo de cursor). O parametro `delta_time` e recebido
        apenas para respeitar a assinatura de `ISystem.update` e e
        explicitamente ignorado na decisao de disparo.
        """
        del delta_time  # deliberadamente ignorado -- ver docstring da classe

        if self.is_finished:
            return

        effective_time = self._compute_effective_time()
        due_count = self._count_due_events(effective_time)
        if due_count <= 0:
            return

        if self._max_threats_per_frame is not None:
            due_count = min(due_count, self._max_threats_per_frame)

        first_index = self._next_pending_index
        last_index = first_index + due_count
        self._spawn_due_events(world, first_index, last_index)
        self._next_pending_index = last_index

    def reset(self) -> None:
        """Reposiciona `self._next_pending_index` para 0, para reiniciar
        a mesma faixa/fase sem reconstruir o sistema nem recarregar o
        beatmap do disco.
        """
        self._next_pending_index = 0

    def _compute_effective_time(self) -> float:
        """Retorna
        `max(0.0, audio_clock.now_seconds() - audio_clock.get_output_latency_seconds())`.
        """
        return max(0.0, self._audio_clock.now_seconds() - self._audio_clock.get_output_latency_seconds())

    def _count_due_events(self, effective_time: float) -> int:
        """Busca vetorizada (`np.searchsorted`, sem loop Python) sobre
        `self._scheduled_threats['timestamp_seconds']`, restrita a
        fatia a partir de `self._next_pending_index`, retornando quantos
        eventos consecutivos a partir do cursor tem
        `timestamp_seconds <= effective_time`.
        """
        remaining_timestamps = self._scheduled_threats["timestamp_seconds"][self._next_pending_index :]
        if remaining_timestamps.shape[0] == 0:
            return 0
        return int(np.searchsorted(remaining_timestamps, effective_time, side="right"))

    def _spawn_due_events(self, world: World, first_index: int, last_index: int) -> None:
        """Para cada indice em `[first_index, last_index)`, delega a
        `_create_threat_entity` a criacao da entidade correspondente.
        Itera por indice inteiro puro (`range`), sem list comprehension
        nem acumulo em lista Python.
        """
        for row_index in range(first_index, last_index):
            self._create_threat_entity(world, row_index)

    def _create_threat_entity(self, world: World, row_index: int) -> PackedEntityId:
        """Cria UMA entidade de ameaca para a linha `row_index` de
        `self._scheduled_threats`, via `world.create_entity` (que ja
        retorna um `PackedEntityId` primitivo -- este metodo nunca o
        envolve em um `EntityHandle`), e escreve os campos
        `lane`/`threat_type` dessa linha nas pools do arquetipo
        recem-criado. Retorna o `PackedEntityId` bruto.

        Contrato assumido (nao imposto por dtype algum aqui) sobre as
        pools identificadas por `self._lane_pool_name`/
        `self._threat_type_pool_name`: cada uma possui, respectivamente,
        um campo `lane` (inteiro) e um campo `threat_type` (inteiro) no
        seu dtype estruturado -- essas pools sao especificas do produto
        Rhythm e devem ser criadas (via `memory_manager.create_pool`)
        pela composicao do jogo/cenario de teste antes deste sistema
        rodar.
        """
        packed_entity_id = world.create_entity(self._threat_archetype_name)
        entity_index = unpack_index(packed_entity_id)

        lane_pool = world.get_pool(self._lane_pool_name)
        threat_type_pool = world.get_pool(self._threat_type_pool_name)

        lane_row = lane_pool.dense_row_of(entity_index)
        threat_type_row = threat_type_pool.dense_row_of(entity_index)

        scheduled_row = self._scheduled_threats[row_index]
        lane_pool.active_view()["lane"][lane_row] = scheduled_row["lane"]
        threat_type_pool.active_view()["threat_type"][threat_type_row] = scheduled_row["threat_type"]

        return packed_entity_id
