# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Julga cliques/arrastes do jogador contra hit-objects Osu! ativos, via IAudioClock + posicao de cursor."""
from __future__ import annotations

from typing import Callable, Optional, Tuple

import numpy as np

from ouroboros.core.memory.handles import NULL_PACKED_HANDLE
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.rhythm.runtime.judgment_system import Judgment
from ouroboros.rhythm.runtime.schemas import OsuObjectKind

_EPSILON = 1.0e-6


class OsuJudgmentSystem(ISystem):
    """
    Julga cliques do jogador (posicao de cursor + tempo) contra
    hit-objects Osu! ativos, e resolve sliders em tracking pela fracao
    de tempo em que o cursor permaneceu dentro do raio de tolerancia com
    o botao pressionado (ROADMAP M15). Reusa o `Judgment` IntEnum de
    `judgment_system.py` (PERFECT/GOOD/MISS vale igual para circulo e
    slider resolvido).

    LIMITACAO CONHECIDA DO V1 (documentada, nao corrigida aqui): ao
    contrario do modo lane (particionado por lane -- 2 notas so podem
    colidir na MESMA lane, o que a cadencia do beatmap de demonstracao
    torna irrelevante na pratica), julgamento por posicao NAO parte de
    nenhuma particao: TODO hit-object ativo e candidato a QUALQUER
    clique, filtrado so por `hit_radius_px` + janela de tempo. Se dois
    hit-objects ficassem simultaneamente dentro de `hit_radius_px` E
    `2 * miss_window_seconds` um do outro (o gerador de posicoes tem um
    teto de tentativas de rejeicao-e-reamostra que, no limite, PODE
    produzir isso), um unico clique poderia ser espacialmente ambiguo
    entre os dois -- `argmin` por delta de tempo credita o mais proximo
    NO TEMPO, nao necessariamente o que o jogador mirou. Nao e um
    problema vivo na musica de demonstracao (gaps de onset reais
    ~0.488-0.511s, bem maiores que `2 * miss_window_seconds = 0.30s`),
    mas nao e estruturalmente impossivel como no modo lane -- fica
    registrado, nao corrigido (ver ROADMAP M15, "fora de escopo").

    USO DELIBERADO E LIMITADO DE `delta_time`: ao contrario de todo o
    resto desta classe (que julga tempo EXCLUSIVAMENTE via
    `effective_time` do `IAudioClock`, nunca `delta_time` acumulado),
    `_judge_slider_tracking` pondera `tracked_time_seconds`/
    `good_time_seconds` por `delta_time` REAL do frame -- NAO para
    decidir QUANDO algo dispara (isso continua 100% audio-clock), so
    para pesar uma METRICA DE QUALIDADE (fracao de tempo com bom
    rastreio). Ponderar por CONTAGEM DE FRAMES em vez de tempo real
    enviesaria essa fracao pela taxa de quadros (achado real da critica
    de M15: uma maquina mais lenta puniria o MESMO comportamento fisico
    do jogador com mais peso por frame perdido).

    Invariante Zero-GC dentro de `update()`: mesma disciplina de
    `JudgmentSystem` -- `_processed_scratch` pre-alocado,
    `world.destroy_entity` sobre `PackedEntityId` primitivos, nenhum
    objeto Python instanciado por hit-object julgado.
    """

    def __init__(
        self,
        audio_clock: IAudioClock,
        input_provider: IInputProvider,
        note_state_pool_name: str,
        entity_capacity: int,
        hit_radius_px: float,
        slider_follow_radius_px: float,
        perfect_window_seconds: float = 0.05,
        good_window_seconds: float = 0.12,
        miss_window_seconds: float = 0.20,
        slider_perfect_fraction: float = 0.9,
        slider_good_fraction: float = 0.5,
        points_by_judgment: Tuple[int, int, int] = (300, 100, 0),
        click_action_name: str = "click",
        audio_engine: Optional[IAudioEngine] = None,
        sfx_ids_by_judgment: Optional[Tuple[str, str, str]] = None,
        on_judgment: Optional[Callable[[Judgment, int, float, float], None]] = None,
    ) -> None:
        """`hit_radius_px`: distancia maxima cursor<->cabeca para um
        clique contar como candidato a um CIRCLE ou a iniciar o
        tracking de um SLIDER. `slider_follow_radius_px`: distancia
        maxima cursor<->posicao-esperada-interpolada para um frame de
        tracking contar como "bom". `slider_perfect_fraction`/
        `slider_good_fraction`: limiares de `good_time_seconds /
        tracked_time_seconds` (MAIOR-e-melhor -- direcao de comparacao
        INVERSA de `_classify`, que e menor-delta-e-melhor).

        `on_judgment` (opcional, default `None`): chamado UMA VEZ por
        hit-object julgado, como `(judgment, layer, x, y)` -- `x`/`y` sao
        a posicao REAL do proprio objeto (nao um indice de lane com
        tabela de lookup: aqui a posicao ja e dado nativo do objeto
        julgado, mais simples que o modo lane precisar de
        `lane_x_positions`)."""
        self._audio_clock = audio_clock
        self._input_provider = input_provider
        self._note_state_pool_name = note_state_pool_name
        self._hit_radius_px = hit_radius_px
        self._slider_follow_radius_px = slider_follow_radius_px
        self._perfect_window_seconds = perfect_window_seconds
        self._good_window_seconds = good_window_seconds
        self._miss_window_seconds = miss_window_seconds
        self._slider_perfect_fraction = slider_perfect_fraction
        self._slider_good_fraction = slider_good_fraction
        self._points_by_judgment = points_by_judgment
        self._click_action_name = click_action_name
        self._audio_engine = audio_engine
        self._sfx_ids_by_judgment = sfx_ids_by_judgment
        self._on_judgment = on_judgment
        self._processed_scratch = np.zeros(entity_capacity, dtype=bool)

        self._score = 0
        self._combo = 0
        self._max_combo = 0
        self._perfect_count = 0
        self._good_count = 0
        self._miss_count = 0

    @property
    def score(self) -> int:
        return self._score

    @property
    def combo(self) -> int:
        return self._combo

    @property
    def max_combo(self) -> int:
        return self._max_combo

    @property
    def judged_count(self) -> int:
        return self._perfect_count + self._good_count + self._miss_count

    @property
    def accuracy(self) -> float:
        total = self.judged_count
        if total == 0:
            return 1.0
        return (self._perfect_count + self._good_count) / total

    def update(self, world: World, delta_time: float) -> None:
        """Julga cliques/arrastes do jogador e auto-erra hit-objects
        nunca clicados vencidos. `delta_time` e usado APENAS para
        ponderar a metrica de qualidade de tracking (ver docstring da
        classe) -- toda decisao de TEMPO continua exclusivamente via
        `IAudioClock`."""
        note_state_pool = world.get_pool(self._note_state_pool_name)
        count = note_state_pool.count
        self._processed_scratch[:] = False
        if count == 0:
            return

        entity_indices = note_state_pool.active_entity_indices()
        view = note_state_pool.active_view()
        effective_time = max(
            0.0,
            self._audio_clock.now_seconds() - self._audio_clock.get_output_latency_seconds(),
        )
        cursor_x, cursor_y = self._input_provider.get_cursor_position()

        self._judge_click(world, effective_time, entity_indices, view, cursor_x, cursor_y)
        self._judge_slider_tracking(view, effective_time, cursor_x, cursor_y, delta_time)
        self._resolve_finished_sliders(world, effective_time, entity_indices, view)
        self._auto_miss_never_clicked(world, effective_time, entity_indices, view)

    def _judge_click(
        self,
        world: World,
        effective_time: float,
        entity_indices: np.ndarray,
        view: np.ndarray,
        cursor_x: float,
        cursor_y: float,
    ) -> None:
        """No clique: acha o candidato mais proximo NO TEMPO dentre os
        hit-objects dentro de `hit_radius_px` e da janela de erro (ver
        limitacao de ambiguidade posicional na docstring da classe).
        CIRCLE -> julga e destroi na hora. SLIDER -> inicia tracking,
        destroi so o anel (a bola fica visivel), ainda sem pontuar."""
        if not self._input_provider.is_action_pressed(self._click_action_name):
            return

        distances_sq = (view["x"] - cursor_x) ** 2 + (view["y"] - cursor_y) ** 2
        time_deltas = np.abs(view["timestamp_seconds"] - effective_time)
        candidate_mask = (
            (distances_sq <= self._hit_radius_px * self._hit_radius_px)
            & (time_deltas <= self._miss_window_seconds)
            & (~view["is_tracking"])
        )
        if not candidate_mask.any():
            return  # whiff: sem candidato proximo o bastante -- sem penalidade no v1 (mesmo criterio do modo lane)

        candidate_positions = np.flatnonzero(candidate_mask)
        best_local = int(np.argmin(time_deltas[candidate_positions]))
        position = int(candidate_positions[best_local])
        entity_index = int(entity_indices[position])

        if int(view["object_kind"][position]) == OsuObjectKind.SLIDER:
            view["is_tracking"][position] = True
            view["tracked_time_seconds"][position] = 0.0
            view["good_time_seconds"][position] = 0.0

            ring_packed = int(view["ring_entity_id"][position])
            if ring_packed != NULL_PACKED_HANDLE:
                world.destroy_entity(ring_packed)
                # Reset IMEDIATO pro sentinela (achado real da critica de M15):
                # MemoryManager recicla indices livres em LIFO -- sem isso, este
                # campo manteria um handle rapidamente reaproveitado por uma
                # entidade NOVA e nao-relacionada, e OsuPresentationSystem
                # escreveria (silenciosamente) na entidade errada.
                view["ring_entity_id"][position] = NULL_PACKED_HANDLE
            return  # ainda nao julgado -- resolve em _resolve_finished_sliders

        best_delta = float(time_deltas[position])
        judgment = self._classify(best_delta)
        self._apply_judgment(
            world, judgment, entity_index, position, view,
            x=float(view["x"][position]), y=float(view["y"][position]),
        )

    def _judge_slider_tracking(
        self,
        view: np.ndarray,
        effective_time: float,
        cursor_x: float,
        cursor_y: float,
        delta_time: float,
    ) -> None:
        """A cada frame, para todo slider em tracking: acumula
        `tracked_time_seconds`/`good_time_seconds` ponderados por
        `delta_time` real (ver docstring da classe), nunca contagem de
        frames."""
        tracking_mask = view["is_tracking"]
        if not tracking_mask.any():
            return

        is_held = self._input_provider.is_action_held(self._click_action_name)

        timestamps = view["timestamp_seconds"][tracking_mask]
        durations = np.maximum(view["duration_seconds"][tracking_mask], _EPSILON)
        fraction = np.clip((effective_time - timestamps) / durations, 0.0, 1.0)
        expected_x = view["x"][tracking_mask] + fraction * (view["end_x"][tracking_mask] - view["x"][tracking_mask])
        expected_y = view["y"][tracking_mask] + fraction * (view["end_y"][tracking_mask] - view["y"][tracking_mask])
        within = is_held & (
            (expected_x - cursor_x) ** 2 + (expected_y - cursor_y) ** 2 <= self._slider_follow_radius_px ** 2
        )

        view["tracked_time_seconds"][tracking_mask] += delta_time
        view["good_time_seconds"][tracking_mask] += np.where(within, delta_time, 0.0)

    def _resolve_finished_sliders(
        self, world: World, effective_time: float, entity_indices: np.ndarray, view: np.ndarray
    ) -> None:
        """Quando `duration_seconds` de um slider em tracking se esgota,
        resolve seu julgamento holistico pela fracao `good_time_seconds
        / tracked_time_seconds` (ver `_classify_slider`) e destroi
        (cabeca + bola -- o anel ja foi destruido/anulado no clique)."""
        tracking_mask = view["is_tracking"]
        if not tracking_mask.any():
            return
        elapsed = effective_time - view["timestamp_seconds"]
        finished_mask = tracking_mask & (elapsed >= view["duration_seconds"])
        if not finished_mask.any():
            return

        for position in np.flatnonzero(finished_mask):
            entity_index = int(entity_indices[position])
            tracked = float(view["tracked_time_seconds"][position])
            good = float(view["good_time_seconds"][position])
            good_fraction = good / tracked if tracked > _EPSILON else 0.0
            judgment = self._classify_slider(good_fraction)
            self._apply_judgment(
                world, judgment, entity_index, position, view,
                x=float(view["x"][position]), y=float(view["y"][position]),
            )

    def _auto_miss_never_clicked(
        self, world: World, effective_time: float, entity_indices: np.ndarray, view: np.ndarray
    ) -> None:
        """Auto-erra (e destroi cabeca + qualquer companheira ainda
        viva) todo hit-object NUNCA clicado (circulo, ou slider ainda
        `is_tracking == False`) vencido ha mais de `miss_window_seconds`,
        ainda nao processado nesta chamada."""
        never_clicked_mask = ~view["is_tracking"]
        expired_mask = ((effective_time - view["timestamp_seconds"]) > self._miss_window_seconds) & never_clicked_mask
        if not expired_mask.any():
            return

        for position in np.flatnonzero(expired_mask):
            entity_index = int(entity_indices[position])
            if self._processed_scratch[entity_index]:
                continue
            self._apply_judgment(
                world, Judgment.MISS, entity_index, position, view,
                x=float(view["x"][position]), y=float(view["y"][position]),
            )

    def _classify(self, delta_seconds: float) -> Judgment:
        """Classifica um desvio de tempo absoluto (CIRCLE) pelos thresholds configurados."""
        if delta_seconds <= self._perfect_window_seconds:
            return Judgment.PERFECT
        if delta_seconds <= self._good_window_seconds:
            return Judgment.GOOD
        return Judgment.MISS

    def _classify_slider(self, good_fraction: float) -> Judgment:
        """Classifica a fracao holistica de tracking de um SLIDER --
        MAIOR-e-melhor, direcao INVERSA de `_classify`."""
        if good_fraction >= self._slider_perfect_fraction:
            return Judgment.PERFECT
        if good_fraction >= self._slider_good_fraction:
            return Judgment.GOOD
        return Judgment.MISS

    def _apply_judgment(
        self,
        world: World,
        judgment: Judgment,
        entity_index: int,
        position: int,
        view: np.ndarray,
        x: float,
        y: float,
    ) -> None:
        """Aplica um julgamento ja decidido: atualiza score/combo, marca
        a entidade como processada, destroi a cabeca E qualquer
        companheira (anel/bola) AINDA VIVA (`!= NULL_PACKED_HANDLE`) --
        cobre os 3 caminhos de destino de uma vez: CIRCLE (so anel),
        SLIDER resolvido (so bola -- anel ja foi destruido+anulado no
        clique), SLIDER nunca clicado (anel E bola, ambos ainda vivos)."""
        self._processed_scratch[entity_index] = True
        layer = int(view["layer"][position])
        world.destroy_entity(int(view["packed_entity_id"][position]))

        ring_packed = int(view["ring_entity_id"][position])
        if ring_packed != NULL_PACKED_HANDLE:
            world.destroy_entity(ring_packed)
        ball_packed = int(view["ball_entity_id"][position])
        if ball_packed != NULL_PACKED_HANDLE:
            world.destroy_entity(ball_packed)

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

        if self._on_judgment is not None:
            self._on_judgment(judgment, layer, x, y)
