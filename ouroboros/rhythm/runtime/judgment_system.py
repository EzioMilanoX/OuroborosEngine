# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Julga acertos do jogador (Perfeito/Bom/Erro) contra notas ativas, via IAudioClock -- nunca delta_time."""
from __future__ import annotations

from enum import IntEnum
from typing import Optional, Tuple

import numpy as np

from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider


class Judgment(IntEnum):
    """Resultado de julgamento de uma nota. Ordem = severidade crescente
    (contrato estavel, como `ModifierOperation`/`RandomStreamPurpose`
    do Pilar 3: nunca renumerar um membro existente)."""

    PERFECT = 0
    GOOD = 1
    MISS = 2


class JudgmentSystem(ISystem):
    """
    Julga o input do jogador contra notas ativas, e auto-julga como Erro
    qualquer nota cujo instante de disparo ja passou da janela de Erro
    sem ter sido pressionada -- consultando exclusivamente
    `self._audio_clock`, NUNCA o `delta_time` acumulado de `update()`
    (mesmo criterio de `RhythmSpawnerSystem`/`NoteScrollSystem`).

    `effective_time` e calculado UMA UNICA VEZ por `update()` (mesma
    formula de compensacao de latencia das outras duas classes) e
    reutilizado nas duas passadas abaixo -- isso e o que torna as duas
    janelas matematicamente MUTUAMENTE EXCLUSIVAS por construcao: a
    passada de pressao so julga notas com
    `abs(timestamp - effective_time) <= miss_window_seconds`; a passada
    de auto-erro so julga notas com
    `(effective_time - timestamp) > miss_window_seconds`. Nenhuma nota
    pode satisfazer as duas ao mesmo tempo NESTA chamada.

    PASSADA DE PRESSAO (por lane, uma lista fixa e pequena -- ex. 4):
        Se `input_provider.is_action_pressed(lane_action_names[lane])`
        (borda: True so no frame exato da pressao), busca a nota mais
        proxima do tempo atual NAQUELA lane (`argmin` de
        `abs(timestamp - effective_time)` sobre o subconjunto ja
        filtrado por lane). Se a mais proxima estiver dentro de
        `miss_window_seconds`, classifica por threshold
        (`<= perfect_window_seconds` -> PERFECT, `<= good_window_seconds`
        -> GOOD, senao MISS) e destroi a entidade. Se nao houver nota
        proxima o suficiente na lane (ou a lane estiver vazia), a
        pressao e um "whiff" -- v1 nao aplica penalidade a isso
        (simplificacao documentada).

    PASSADA DE AUTO-ERRO (sobre TODAS as notas ativas, nao filtrada por
    lane): qualquer nota com `(effective_time - timestamp_seconds) >
    miss_window_seconds` que ainda nao foi processada nesta MESMA
    chamada (ver array de scratch abaixo) e julgada Erro automaticamente
    e destruida.

    ARRAY DE SCRATCH PRE-ALOCADO (`self._processed_scratch`, tamanho
    `entity_capacity`, resetado para `False` no INICIO de cada
    `update()`): marca entidades ja processadas nesta chamada, para a
    passada de auto-erro nunca reprocessar uma nota que a passada de
    pressao ja julgou. Dado que as duas janelas sao matematicamente
    mutuamente exclusivas (paragrafo acima), a colisao que este array
    evita NAO PODE ocorrer hoje -- ele existe como defesa em profundidade
    contra um refactor futuro que quebre essa invariante (ex.: alguem
    passar a chamar `audio_clock.now_seconds()` separadamente em cada
    passada em vez de reusar um `effective_time` ja capturado, o que
    reintroduziria uma janela real de corrida, ja que o relogio pode
    avancar entre as duas chamadas). Mesmo padrao de buffer de scratch
    pre-alocado ja usado por `CollisionSystem`/`UniformGrid`.

    Estado de score/combo/contagens e um UNICO registro global escalar
    (nao um dado por-entidade) -- atributos de instancia simples
    mutados in-place, expostos via propriedades somente-leitura.

    Invariante Zero-GC dentro de `update()`: `intersect_entity_indices`
    e chamado UMA UNICA VEZ por chamada (nao por lane pressionada) --
    um array novo por CHAMADA, nao por entidade, o mesmo padrao ja
    aceito em outros Systems. `world.destroy_entity` opera sobre
    `PackedEntityId` inteiros primitivos, sem instanciar `EntityHandle`.
    Nenhum objeto Python e instanciado por nota julgada.
    """

    def __init__(
        self,
        audio_clock: IAudioClock,
        input_provider: IInputProvider,
        note_state_pool_name: str,
        lane_pool_name: str,
        lane_action_names: Tuple[str, ...],
        entity_capacity: int,
        perfect_window_seconds: float = 0.05,
        good_window_seconds: float = 0.12,
        miss_window_seconds: float = 0.20,
        points_by_judgment: Tuple[int, int, int] = (300, 100, 0),
        audio_engine: Optional[IAudioEngine] = None,
        sfx_ids_by_judgment: Optional[Tuple[str, str, str]] = None,
    ) -> None:
        """Resolve nomes de pool uma unica vez (fora do hot-loop) e
        pre-aloca `self._processed_scratch` (shape `(entity_capacity,)`,
        bool). `points_by_judgment` e `(pontos_perfeito, pontos_bom,
        pontos_erro)`, indexavel por `Judgment` -- parametrizado (nao
        hardcoded) para nao violar a Regra 3 (Data-Driven): o chamador
        tipicamente carrega esses valores de um JSON em `data/`.

        `audio_engine`/`sfx_ids_by_judgment` (opcionais, default `None`,
        omitir preserva 100% o comportamento antigo -- mesmo idioma de
        `note_state_pool_name`/`on_note_spawned` em `RhythmSpawnerSystem`):
        se ambos fornecidos, `_apply_judgment` chama
        `audio_engine.play_one_shot(...)` com o id correspondente ao
        julgamento decidido. `sfx_ids_by_judgment` e
        `(id_perfeito, id_bom, id_erro)`, indexavel por `Judgment` --
        parametrizado, nao hardcoded, mesmo criterio de
        `points_by_judgment`. O chamador e responsavel por garantir que
        esses ids ja foram registrados em `audio_engine` (ex.: via
        `ouroboros.bootstrap.audio_bank_loader.load_audio_bank`) ANTES
        de construir este sistema -- validar isso e responsabilidade da
        composicao, nao deste construtor, para a falha aparecer na
        composicao, nunca dentro do loop de gameplay.

        Nota honesta: `NullAudioEngine.play_one_shot` (usado em testes)
        aloca uma tupla Python por chamada -- inofensivo (contagens
        pequenas, so em teste), mas e a primeira vez que este sistema
        chama algo em `IAudioEngine` de dentro de `update()`, entao vale
        registrar a excecao aqui, mesmo padrao de honestidade ja usado
        no resto desta classe."""
        if sfx_ids_by_judgment is not None and len(sfx_ids_by_judgment) != 3:
            raise ValueError("sfx_ids_by_judgment deve ter exatamente 3 elementos (perfeito, bom, erro)")

        self._audio_clock = audio_clock
        self._input_provider = input_provider
        self._note_state_pool_name = note_state_pool_name
        self._lane_pool_name = lane_pool_name
        self._lane_action_names = tuple(lane_action_names)
        self._perfect_window_seconds = perfect_window_seconds
        self._good_window_seconds = good_window_seconds
        self._miss_window_seconds = miss_window_seconds
        self._points_by_judgment = points_by_judgment
        self._audio_engine = audio_engine
        self._sfx_ids_by_judgment = sfx_ids_by_judgment
        self._processed_scratch = np.zeros(entity_capacity, dtype=bool)

        self._score = 0
        self._combo = 0
        self._max_combo = 0
        self._perfect_count = 0
        self._good_count = 0
        self._miss_count = 0

    @property
    def score(self) -> int:
        """Pontuacao acumulada."""
        return self._score

    @property
    def combo(self) -> int:
        """Sequencia atual de acertos (Perfeito/Bom) sem Erro. Zera a cada Erro (manual ou automatico)."""
        return self._combo

    @property
    def max_combo(self) -> int:
        """Maior combo alcancado na partida."""
        return self._max_combo

    @property
    def judged_count(self) -> int:
        """Total de notas ja julgadas (Perfeito + Bom + Erro), para a UI detectar fim de musica."""
        return self._perfect_count + self._good_count + self._miss_count

    @property
    def accuracy(self) -> float:
        """`(perfeitos + bons) / total_julgado`, ou `1.0` se nada foi julgado ainda."""
        total = self.judged_count
        if total == 0:
            return 1.0
        return (self._perfect_count + self._good_count) / total

    def update(self, world: World, delta_time: float) -> None:
        """Julga pressoes do jogador e auto-erra notas vencidas; `delta_time`
        e recebido apenas para respeitar a assinatura de `ISystem.update`
        e e explicitamente ignorado (ver docstring da classe)."""
        del delta_time  # deliberadamente ignorado -- ver docstring da classe

        note_state_pool = world.get_pool(self._note_state_pool_name)
        lane_pool = world.get_pool(self._lane_pool_name)

        entity_indices = intersect_entity_indices(note_state_pool, lane_pool)
        self._processed_scratch[:] = False
        if entity_indices.size == 0:
            return

        effective_time = max(
            0.0,
            self._audio_clock.now_seconds() - self._audio_clock.get_output_latency_seconds(),
        )

        ns_rows = note_state_pool.dense_rows_of(entity_indices)
        l_rows = lane_pool.dense_rows_of(entity_indices)
        ns_view = note_state_pool.active_view()
        l_view = lane_pool.active_view()
        timestamps = ns_view["timestamp_seconds"][ns_rows]
        lanes = l_view["lane"][l_rows]

        self._judge_presses(world, effective_time, entity_indices, ns_view, ns_rows, timestamps, lanes)
        self._auto_miss_expired(world, effective_time, entity_indices, ns_view, ns_rows, timestamps)

    def _judge_presses(
        self,
        world: World,
        effective_time: float,
        entity_indices: np.ndarray,
        ns_view: np.ndarray,
        ns_rows: np.ndarray,
        timestamps: np.ndarray,
        lanes: np.ndarray,
    ) -> None:
        """Para cada lane pressionada neste frame, julga a nota mais proxima naquela lane."""
        for lane_index, action_name in enumerate(self._lane_action_names):
            if not self._input_provider.is_action_pressed(action_name):
                continue

            lane_mask = lanes == lane_index
            if not lane_mask.any():
                continue  # whiff: nenhuma nota nesta lane, sem penalidade no v1

            candidate_positions = np.flatnonzero(lane_mask)
            deltas = np.abs(timestamps[candidate_positions] - effective_time)
            best_local = int(np.argmin(deltas))
            best_delta = float(deltas[best_local])
            if best_delta > self._miss_window_seconds:
                continue  # whiff: nota mais proxima esta fora da janela, sem penalidade no v1

            position = candidate_positions[best_local]
            self._apply_judgment(
                world,
                self._classify(best_delta),
                entity_index=int(entity_indices[position]),
                packed_entity_id=int(ns_view["packed_entity_id"][ns_rows[position]]),
            )

    def _auto_miss_expired(
        self,
        world: World,
        effective_time: float,
        entity_indices: np.ndarray,
        ns_view: np.ndarray,
        ns_rows: np.ndarray,
        timestamps: np.ndarray,
    ) -> None:
        """Auto-erra (e destroi) qualquer nota vencida ha mais de `miss_window_seconds`, ainda nao processada nesta chamada."""
        expired_mask = (effective_time - timestamps) > self._miss_window_seconds
        if not expired_mask.any():
            return
        for position in np.flatnonzero(expired_mask):
            entity_index = int(entity_indices[position])
            if self._processed_scratch[entity_index]:
                continue
            self._apply_judgment(
                world,
                Judgment.MISS,
                entity_index=entity_index,
                packed_entity_id=int(ns_view["packed_entity_id"][ns_rows[position]]),
            )

    def _classify(self, delta_seconds: float) -> Judgment:
        """Classifica um desvio de tempo absoluto em Perfeito/Bom/Erro pelos thresholds configurados."""
        if delta_seconds <= self._perfect_window_seconds:
            return Judgment.PERFECT
        if delta_seconds <= self._good_window_seconds:
            return Judgment.GOOD
        return Judgment.MISS

    def _apply_judgment(self, world: World, judgment: Judgment, entity_index: int, packed_entity_id: int) -> None:
        """Aplica um julgamento ja decidido: atualiza score/combo, marca a entidade como processada, e destroi (diferido)."""
        self._processed_scratch[entity_index] = True
        world.destroy_entity(packed_entity_id)

        if judgment == Judgment.PERFECT:
            self._perfect_count += 1
            self._combo += 1
        elif judgment == Judgment.GOOD:
            self._good_count += 1
            self._combo += 1
        else:
            self._miss_count += 1
            self._combo = 0

        self._score += self._points_by_judgment[int(judgment)]
        self._max_combo = max(self._max_combo, self._combo)

        if self._audio_engine is not None and self._sfx_ids_by_judgment is not None:
            self._audio_engine.play_one_shot(self._sfx_ids_by_judgment[int(judgment)])
