# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao do modo Osu! do Jogo Musical (ROADMAP M15): montagem de uma partida por cima do CompositionRoot generico."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene
from ouroboros.bootstrap.screen_shake import ScreenShake, ScreenShakeUpdateSystem
from ouroboros.core.memory.handles import NULL_PACKED_HANDLE, PackedEntityId, unpack_index
from ouroboros.core.particle_storage import ParticleStorage
from ouroboros.core.systems.fx_system import FxTtlSystem
from ouroboros.core.systems.particle_update_system import ParticleUpdateSystem
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RING
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader
from ouroboros.rhythm.loaders.song_catalog_loader import SongEntry
from ouroboros.rhythm.runtime.approach_schedule import split_spawn_and_hit_schedules
from ouroboros.rhythm.runtime.judgment_system import Judgment
from ouroboros.rhythm.runtime.osu_beatmap_loader import OsuBeatmapLoader
from ouroboros.rhythm.runtime.osu_judgment_system import OsuJudgmentSystem
from ouroboros.rhythm.runtime.osu_presentation_system import OsuPresentationSystem
from ouroboros.rhythm.runtime.osu_spawner_system import OsuSpawnerSystem
from ouroboros.rhythm.runtime.schemas import OSU_NOTE_STATE_DTYPE, OsuObjectKind

from games.rhythm_game.hud import build_hud_callback
from games.rhythm_game.pause_scene import PauseScene
from games.rhythm_game.systems.pause_on_action_system import PauseOnActionSystem
from games.rhythm_game.systems.quit_on_action_system import QuitOnActionSystem

OSU_ARCHETYPE_NAME = "osu_note"
OSU_VISUAL_MARKER_ARCHETYPE_NAME = "osu_visual_marker"
OSU_NOTE_STATE_POOL_NAME = "osu_note_state"

# Strings gravadas no beatmap.json pelo gerador offline
# (`ouroboros/rhythm/offline/osu_placement.py`) -- constante LOCAL deste
# jogo (nao um nome de arquetipo ECS), mesmo espirito de
# BEATMAP_THREAT_TYPE_NAME em games/rhythm_game/composition.py: por
# CONVENCAO (nao import compartilhado) usa os mesmos literais de
# `ouroboros.rhythm.offline.osu_beatmap_schema.OSU_CIRCLE_THREAT_TYPE_NAME`/
# `OSU_SLIDER_THREAT_TYPE_NAME`.
OSU_CIRCLE_TYPE_NAME = "osu_circle"
OSU_SLIDER_TYPE_NAME = "osu_slider"

_GAME_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _GAME_DIR.parent.parent
OSU_ARCHETYPES_DIR = _REPO_ROOT / "data" / "archetypes" / "rhythm_osu"

HEAD_TINT = (230, 230, 255, 255)
RING_TINT = (255, 255, 255, 220)
BALL_TINT = (255, 200, 90, 255)
PATH_MARKER_TINT = (255, 200, 90, 140)
HEAD_SCALE = 1.0
HEAD_LAYER_Z = 10
RING_LAYER_Z = 11
BALL_LAYER_Z = 9

PATH_MARKER_COUNT = 6
PATH_MARKER_SIZE = 10.0

# Particula/screen-shake -- mesmas constantes de games/rhythm_game/composition.py
# (juice por-julgamento, ROADMAP M11.3), reusadas verbatim pro modo Osu!.
HIT_PARTICLE_CAPACITY = 256
HIT_PARTICLE_COUNT_PER_BURST = 12
HIT_PARTICLE_TTL_SECONDS = 0.35
HIT_PARTICLE_SPEED_RANGE = (40.0, 140.0)
HIT_PARTICLE_SIZE = 4.0
LAYER_PARTICLE_TINTS = {0: (255, 190, 90, 255), 1: (120, 220, 255, 255)}

MISS_SHAKE_INTENSITY = 6.0
MISS_SHAKE_CAP = 14.0
MISS_SHAKE_DURATION_SECONDS = 0.18

SFX_IDS_BY_JUDGMENT = ("judgment_perfect", "judgment_good", "judgment_miss")


def _make_on_hit_object_spawned(approach_scale_max: float, approach_seconds: float):
    """Callback passado a `OsuSpawnerSystem`: escreve a aparencia visual
    da CABECA (posicao fixa, nunca rola) e cria as entidades
    companheiras -- anel de aproximacao (todo hit-object) e bola de
    slider (SLIDER apenas) -- escrevendo seus `PackedEntityId` de volta
    na propria linha de `osu_note_state`. Para sliders, tambem semeia um
    pequeno rastro de marcadores na pool `fx` (ja generica, sempre
    presente via `COMPONENT_SCHEMAS`) ao longo da reta cabeca->cauda --
    reusa `FxTtlSystem` ja existente, ZERO codigo novo de renderizacao
    (ver ROADMAP M15)."""

    def on_hit_object_spawned(
        world: World,
        packed_entity_id: PackedEntityId,
        object_kind: int,
        x: float,
        y: float,
        end_x: float,
        end_y: float,
        duration_seconds: float,
        layer: int,
    ) -> None:
        del layer
        head_index = unpack_index(packed_entity_id)
        transform_pool = world.get_pool("transform")
        sprite_pool = world.get_pool("sprite")

        _write_marker_appearance(transform_pool, sprite_pool, head_index, x, y, HEAD_SCALE, SHAPE_CIRCLE, HEAD_TINT, HEAD_LAYER_Z)

        ring_packed = world.create_entity(OSU_VISUAL_MARKER_ARCHETYPE_NAME)
        ring_index = unpack_index(ring_packed)
        _write_marker_appearance(
            transform_pool, sprite_pool, ring_index, x, y, approach_scale_max, SHAPE_RING, RING_TINT, RING_LAYER_Z
        )

        ball_packed = NULL_PACKED_HANDLE
        if object_kind == OsuObjectKind.SLIDER:
            ball_packed = world.create_entity(OSU_VISUAL_MARKER_ARCHETYPE_NAME)
            ball_index = unpack_index(ball_packed)
            _write_marker_appearance(
                transform_pool, sprite_pool, ball_index, x, y, HEAD_SCALE, SHAPE_CIRCLE, BALL_TINT, BALL_LAYER_Z
            )
            _emit_slider_path_markers(world, x, y, end_x, end_y, ttl_seconds=approach_seconds + duration_seconds)

        note_state_pool = world.get_pool(OSU_NOTE_STATE_POOL_NAME)
        note_state_row = note_state_pool.dense_row_of(head_index)
        note_state_view = note_state_pool.active_view()
        note_state_view["ring_entity_id"][note_state_row] = ring_packed
        note_state_view["ball_entity_id"][note_state_row] = ball_packed

    return on_hit_object_spawned


def _write_marker_appearance(transform_pool, sprite_pool, entity_index, x, y, scale, texture_id, tint, layer_z):
    t_row = transform_pool.dense_row_of(entity_index)
    t_view = transform_pool.active_view()
    t_view["position_x"][t_row] = x
    t_view["position_y"][t_row] = y
    t_view["rotation_rad"][t_row] = 0.0
    t_view["scale_x"][t_row] = scale
    t_view["scale_y"][t_row] = scale

    s_row = sprite_pool.dense_row_of(entity_index)
    s_view = sprite_pool.active_view()
    s_view["texture_id"][s_row] = texture_id
    s_view["tint_r"][s_row] = tint[0]
    s_view["tint_g"][s_row] = tint[1]
    s_view["tint_b"][s_row] = tint[2]
    s_view["tint_a"][s_row] = tint[3]
    s_view["layer_z"][s_row] = layer_z


def _emit_slider_path_markers(world: World, x: float, y: float, end_x: float, end_y: float, ttl_seconds: float) -> None:
    """Semeia `PATH_MARKER_COUNT` entradas na pool `fx` ao longo da reta
    `(x,y)->(end_x,end_y)`, com `ttl_seconds` (= tempo-ate-o-hit +
    duracao do arraste, calculado no momento do SPAWN) decaindo em tempo
    REAL (`FxTtlSystem` -- presentation-only, nunca sincronizado a
    audio-clock, mesmo tradeoff ja aceito pelas particulas de acerto): o
    rastro do slider pode, apos um engasgo de frame, sobreviver alguns
    ms a mais/menos que a bola em si -- cosmetico, nunca afeta
    pontuacao."""
    fx_pool = world.get_pool("fx")
    for i in range(PATH_MARKER_COUNT):
        fraction = i / max(PATH_MARKER_COUNT - 1, 1)
        packed = world.create_entity("fx")
        index = unpack_index(packed)
        row = fx_pool.dense_row_of(index)
        view = fx_pool.active_view()
        view["kind"][row] = SHAPE_CIRCLE
        view["position_x"][row] = x + fraction * (end_x - x)
        view["position_y"][row] = y + fraction * (end_y - y)
        view["width"][row] = PATH_MARKER_SIZE
        view["height"][row] = PATH_MARKER_SIZE
        view["tint_r"][row] = PATH_MARKER_TINT[0]
        view["tint_g"][row] = PATH_MARKER_TINT[1]
        view["tint_b"][row] = PATH_MARKER_TINT[2]
        view["tint_a"][row] = PATH_MARKER_TINT[3]
        view["ttl_seconds"][row] = ttl_seconds


def _make_on_judgment(particle_storage: ParticleStorage, screen_shake: ScreenShake):
    """Callback passado a `OsuJudgmentSystem` (ROADMAP M15): mesma juice
    de `games/rhythm_game/composition.py._make_on_judgment`, mas
    recebendo `(x, y)` REAIS do hit-object julgado -- nao um indice de
    lane com tabela de lookup (mais simples que o modo lane aqui: a
    posicao ja e dado nativo do proprio objeto)."""
    position_x = np.zeros(HIT_PARTICLE_COUNT_PER_BURST, dtype=np.float32)
    position_y = np.zeros(HIT_PARTICLE_COUNT_PER_BURST, dtype=np.float32)
    velocity_x = np.zeros(HIT_PARTICLE_COUNT_PER_BURST, dtype=np.float32)
    velocity_y = np.zeros(HIT_PARTICLE_COUNT_PER_BURST, dtype=np.float32)
    ttl_seconds = np.full(HIT_PARTICLE_COUNT_PER_BURST, HIT_PARTICLE_TTL_SECONDS, dtype=np.float32)
    size = np.full(HIT_PARTICLE_COUNT_PER_BURST, HIT_PARTICLE_SIZE, dtype=np.float32)
    tint_rgba = np.zeros((HIT_PARTICLE_COUNT_PER_BURST, 4), dtype=np.uint8)
    rng = np.random.default_rng()  # juice de apresentacao -- nao precisa de determinismo

    def on_judgment(judgment: Judgment, layer: int, x: float, y: float) -> None:
        if judgment == Judgment.MISS:
            new_total = min(screen_shake.current_magnitude() + MISS_SHAKE_INTENSITY, MISS_SHAKE_CAP)
            screen_shake.trigger(new_total, MISS_SHAKE_DURATION_SECONDS)
            return

        angles = rng.uniform(0.0, 2.0 * np.pi, size=HIT_PARTICLE_COUNT_PER_BURST)
        speeds = rng.uniform(HIT_PARTICLE_SPEED_RANGE[0], HIT_PARTICLE_SPEED_RANGE[1], size=HIT_PARTICLE_COUNT_PER_BURST)
        position_x[:] = x
        position_y[:] = y
        velocity_x[:] = np.cos(angles) * speeds
        velocity_y[:] = np.sin(angles) * speeds
        tint_rgba[:, :] = LAYER_PARTICLE_TINTS.get(layer, LAYER_PARTICLE_TINTS[0])
        particle_storage.emit_burst(position_x, position_y, velocity_x, velocity_y, ttl_seconds, size, tint_rgba)

    return on_judgment


def start_osu_song(
    game_loop: GameLoop,
    config: EngineConfig,
    song: SongEntry,
    difficulty: dict,
    on_return_to_menu: Callable[[], None],
) -> None:
    """Monta um `World` NOVO (mesmo idioma de `_start_song` do modo
    lane) pra `song`/`difficulty`, registra por cima as pools/arquetipos/
    sistemas do modo Osu! (ROADMAP M15), carrega o beatmap/audio da
    musica escolhida, e substitui o `World`/pilha de cenas do
    `game_loop` ja existente."""
    world = CompositionRoot(config).build_world()

    world.create_pool(OSU_NOTE_STATE_POOL_NAME, OSU_NOTE_STATE_DTYPE, dense_capacity=config.entity_capacity)
    ArchetypeLoader(OSU_ARCHETYPES_DIR).load_and_register_all(world)
    world.register_archetype("fx", ("fx",))

    scheduled_hits = OsuBeatmapLoader(
        threat_type_name_to_id={OSU_CIRCLE_TYPE_NAME: int(OsuObjectKind.CIRCLE), OSU_SLIDER_TYPE_NAME: int(OsuObjectKind.SLIDER)},
        slider_threat_type_id=int(OsuObjectKind.SLIDER),
    ).load(song.beatmap_path)
    spawn_hits, hit_times = split_spawn_and_hit_schedules(scheduled_hits, difficulty["approach_seconds"])

    audio_clock = game_loop.audio_engine.get_clock()
    audio_clock.calibrate_latency(difficulty["output_latency_seconds"])

    particle_storage = ParticleStorage(capacity=HIT_PARTICLE_CAPACITY)
    screen_shake = ScreenShake()

    spawner = OsuSpawnerSystem(
        audio_clock=audio_clock,
        scheduled_hits=spawn_hits,
        hit_archetype_name=OSU_ARCHETYPE_NAME,
        osu_note_state_pool_name=OSU_NOTE_STATE_POOL_NAME,
        on_hit_object_spawned=_make_on_hit_object_spawned(difficulty["approach_scale_max"], difficulty["approach_seconds"]),
        hit_times=hit_times,
    )
    presentation = OsuPresentationSystem(
        audio_clock=audio_clock,
        note_state_pool_name=OSU_NOTE_STATE_POOL_NAME,
        transform_pool_name="transform",
        approach_seconds=difficulty["approach_seconds"],
        ring_start_scale=difficulty["approach_scale_max"],
    )
    judgment = OsuJudgmentSystem(
        audio_clock=audio_clock,
        input_provider=game_loop.input_provider,
        note_state_pool_name=OSU_NOTE_STATE_POOL_NAME,
        entity_capacity=config.entity_capacity,
        hit_radius_px=difficulty["hit_radius_px"],
        slider_follow_radius_px=difficulty["slider_follow_radius_px"],
        perfect_window_seconds=difficulty["perfect_window_seconds"],
        good_window_seconds=difficulty["good_window_seconds"],
        miss_window_seconds=difficulty["miss_window_seconds"],
        slider_perfect_fraction=difficulty["slider_perfect_fraction"],
        slider_good_fraction=difficulty["slider_good_fraction"],
        points_by_judgment=(difficulty["points_perfect"], difficulty["points_good"], difficulty["points_miss"]),
        audio_engine=game_loop.audio_engine,
        sfx_ids_by_judgment=SFX_IDS_BY_JUDGMENT,
        on_judgment=_make_on_judgment(particle_storage, screen_shake),
    )

    world.register_system(spawner)
    world.register_system(presentation)
    world.register_system(judgment)
    world.register_system(FxTtlSystem())
    world.register_system(ParticleUpdateSystem(particle_storage))
    world.register_system(ScreenShakeUpdateSystem(screen_shake, game_loop.renderer))
    world.register_system(QuitOnActionSystem(game_loop.input_provider, on_quit_action=on_return_to_menu))

    gameplay_scene = GameplayScene()
    pause_scene = PauseScene(
        input_provider=game_loop.input_provider,
        game_loop=game_loop,
        audio_engine=game_loop.audio_engine,
        track_id=song.track_id,
        gameplay_scene=gameplay_scene,
        viewport_size=(config.window_width, config.window_height),
    )
    world.register_system(PauseOnActionSystem(game_loop.input_provider, game_loop, pause_scene))

    game_loop.audio_engine.load_track(song.track_id, str(song.audio_path))
    game_loop.audio_engine.play_track(song.track_id)

    game_loop.replace_world(world)
    game_loop.reset_scenes(gameplay_scene)

    game_loop.set_on_draw_ui(
        build_hud_callback(
            judgment_system=judgment,
            spawner_system=spawner,
            note_state_pool=world.get_pool(OSU_NOTE_STATE_POOL_NAME),
            viewport_size=(config.window_width, config.window_height),
            particle_storage=particle_storage,
        )
    )
