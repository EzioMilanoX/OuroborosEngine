"""Composicao do Jogo Musical: registra pools/arquetipo/sistemas especificos por cima do CompositionRoot generico."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import numpy as np

from ouroboros.bootstrap.audio_bank_loader import AudioBankDefinitionError, load_audio_bank
from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.memory.handles import PackedEntityId, unpack_index
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader
from ouroboros.rhythm.runtime.approach_schedule import split_spawn_and_hit_schedules
from ouroboros.rhythm.runtime.beatmap_loader import BeatmapLoader
from ouroboros.rhythm.runtime.judgment_system import JudgmentSystem
from ouroboros.rhythm.runtime.note_scroll_system import NoteScrollSystem
from ouroboros.rhythm.runtime.rhythm_spawner_system import RhythmSpawnerSystem
from ouroboros.rhythm.runtime.schemas import NOTE_STATE_DTYPE

from games.rhythm_game.hud import build_hud_callback
from games.rhythm_game.pause_scene import PauseScene
from games.rhythm_game.systems.pause_on_action_system import PauseOnActionSystem
from games.rhythm_game.systems.quit_on_action_system import QuitOnActionSystem

ARCHETYPE_NAME = "rhythm_note"
LANE_POOL_NAME = "lane"
THREAT_TYPE_POOL_NAME = "threat_type"
NOTE_STATE_POOL_NAME = "note_state"
LANE_ACTION_NAMES = ("lane_0", "lane_1", "lane_2", "lane_3")

# String gravada pelo CLI offline (hoje hardcoded em
# AudioAIProcessor._map_onsets_to_threats) -- NAO e o nome do arquetipo ECS
# (esse e ARCHETYPE_NAME acima), so uma tag inteira armazenada no beatmap,
# hoje nao usada por mais nada alem de ser mapeada para um int aqui.
BEATMAP_THREAT_TYPE_NAME = "rhythm_threat_basic"

LANE_TINTS = (
    (255, 90, 90, 255),
    (90, 255, 90, 255),
    (90, 160, 255, 255),
    (255, 220, 90, 255),
)
NOTE_SCALE = 2.5
NOTE_LAYER_Z = 10

_GAME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GAME_DIR.parent.parent
DIFFICULTY_PATH = _REPO_ROOT / "data" / "difficulties" / "rhythm_normal.json"
BEATMAP_PATH = _REPO_ROOT / "data" / "beatmaps" / "demo_track.beatmap.json"
TRACK_AUDIO_PATH = _GAME_DIR / "assets" / "audio" / "demo_track.wav"
TRACK_ID = "demo_track"

RHYTHM_JUDGMENT_AUDIO_PATH = _REPO_ROOT / "data" / "audio" / "rhythm_judgment.json"
SFX_IDS_BY_JUDGMENT = ("judgment_perfect", "judgment_good", "judgment_miss")

# Subpasta dedicada (nao `data/archetypes/` direto): `ArchetypeLoader.load_and_register_all`
# escaneia o diretorio inteiro nao-recursivamente, e `data/archetypes/*.json` no nivel raiz e
# tambem escaneado por completo pelos testes do Pilar 3 (Roguelite) contra um `world` generico
# que nao tem as pools `lane`/`threat_type`/`note_state` -- colocar o arquetipo deste jogo aqui
# evita esse conflito sem acoplar nada entre os dois produtos.
RHYTHM_ARCHETYPES_DIR = _REPO_ROOT / "data" / "archetypes" / "rhythm"


def _load_difficulty() -> dict:
    with open(DIFFICULTY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _lane_x_positions(window_width: int) -> Tuple[float, ...]:
    """4 posicoes X igualmente espacadas, centralizadas na largura da janela."""
    lane_count = len(LANE_ACTION_NAMES)
    spacing = 100.0
    center = window_width / 2.0
    first = center - spacing * (lane_count - 1) / 2.0
    return tuple(first + i * spacing for i in range(lane_count))


def _make_on_note_spawned():
    """Callback passado a `RhythmSpawnerSystem`: escreve a aparencia visual
    (texture_id/tint/scale/layer_z) de cada nota recem-criada. Sem isso a
    nota fica com `tint_a == 0` (zerado por padrao) e o renderer a ignora
    silenciosamente -- ver docstring de `RhythmSpawnerSystem.__init__`."""

    def on_note_spawned(
        world: World, packed_entity_id: PackedEntityId, lane: int, threat_type: int, layer: int
    ) -> None:
        del threat_type, layer
        index = unpack_index(packed_entity_id)
        sprite_pool = world.get_pool("sprite")
        transform_pool = world.get_pool("transform")
        sprite_row = sprite_pool.dense_row_of(index)
        transform_row = transform_pool.dense_row_of(index)

        tint = LANE_TINTS[lane % len(LANE_TINTS)]
        sprite_view = sprite_pool.active_view()
        sprite_view["texture_id"][sprite_row] = SHAPE_CIRCLE
        sprite_view["tint_r"][sprite_row] = tint[0]
        sprite_view["tint_g"][sprite_row] = tint[1]
        sprite_view["tint_b"][sprite_row] = tint[2]
        sprite_view["tint_a"][sprite_row] = tint[3]
        sprite_view["layer_z"][sprite_row] = NOTE_LAYER_Z

        transform_view = transform_pool.active_view()
        transform_view["scale_x"][transform_row] = NOTE_SCALE
        transform_view["scale_y"][transform_row] = NOTE_SCALE

    return on_note_spawned


def build_game(config: EngineConfig) -> GameLoop:
    """
    Monta o Jogo Musical completo: usa `CompositionRoot(config).build()`
    para o `World` generico (Pilar 1/2), registra por cima as pools/
    arquetipo/sistemas especificos deste jogo (Pilar 4 + HUD), carrega o
    beatmap e a musica, e retorna um `GameLoop` pronto para `.run()`.
    """
    game_loop = CompositionRoot(config).build()
    world = game_loop.world

    world.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]), dense_capacity=config.entity_capacity)
    world.create_pool(
        THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]), dense_capacity=config.entity_capacity
    )
    world.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE, dense_capacity=config.entity_capacity)

    # Carrega data/archetypes/rhythm/rhythm_note.json de verdade (nao um tuple hardcoded em
    # Python) -- so funciona porque as 3 pools especificas acima ja existem neste ponto;
    # ArchetypeLoader valida isso ANTES de registrar qualquer coisa.
    ArchetypeLoader(RHYTHM_ARCHETYPES_DIR).load_and_register_all(world)

    difficulty = _load_difficulty()
    lane_x_positions = _lane_x_positions(config.window_width)
    judgment_line_y = float(config.window_height - 100)

    scheduled_threats = BeatmapLoader({BEATMAP_THREAT_TYPE_NAME: 0}).load(BEATMAP_PATH)
    spawn_threats, hit_times = split_spawn_and_hit_schedules(scheduled_threats, difficulty["approach_seconds"])

    audio_clock = game_loop.audio_engine.get_clock()
    audio_clock.calibrate_latency(difficulty["output_latency_seconds"])

    # Carrega o banco de SFX e valida os ids ANTES de construir o JudgmentSystem --
    # um id incompativel deve falhar aqui, na composicao, nunca dentro do loop de
    # gameplay quando JudgmentSystem tentar tocar um som inexistente (ver docstring
    # de load_audio_bank).
    loaded_sfx_ids = load_audio_bank(game_loop.audio_engine, str(RHYTHM_JUDGMENT_AUDIO_PATH))
    missing_sfx_ids = [sfx_id for sfx_id in SFX_IDS_BY_JUDGMENT if sfx_id not in loaded_sfx_ids]
    if missing_sfx_ids:
        raise AudioBankDefinitionError(
            f"SFX_IDS_BY_JUDGMENT referencia id(s) ausentes em {RHYTHM_JUDGMENT_AUDIO_PATH}: {missing_sfx_ids}"
        )

    spawner = RhythmSpawnerSystem(
        audio_clock=audio_clock,
        scheduled_threats=spawn_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        on_note_spawned=_make_on_note_spawned(),
        hit_times=hit_times,
    )
    scroll = NoteScrollSystem(
        audio_clock=audio_clock,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        transform_pool_name="transform",
        lane_pool_name=LANE_POOL_NAME,
        lane_x_positions=lane_x_positions,
        judgment_line_y=judgment_line_y,
        scroll_speed_px_per_sec=difficulty["scroll_speed_px_per_sec"],
    )
    judgment = JudgmentSystem(
        audio_clock=audio_clock,
        input_provider=game_loop.input_provider,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        lane_pool_name=LANE_POOL_NAME,
        lane_action_names=LANE_ACTION_NAMES,
        entity_capacity=config.entity_capacity,
        perfect_window_seconds=difficulty["perfect_window_seconds"],
        good_window_seconds=difficulty["good_window_seconds"],
        miss_window_seconds=difficulty["miss_window_seconds"],
        points_by_judgment=(difficulty["points_perfect"], difficulty["points_good"], difficulty["points_miss"]),
        audio_engine=game_loop.audio_engine,
        sfx_ids_by_judgment=SFX_IDS_BY_JUDGMENT,
    )

    world.register_system(spawner)
    world.register_system(scroll)
    world.register_system(judgment)
    world.register_system(QuitOnActionSystem(game_loop.input_provider, game_loop))

    # A GameplayScene base ja foi auto-empilhada por GameLoop.__init__ (ROADMAP M2) --
    # a PauseScene reusa essa MESMA instancia pra redesenhar o ultimo frame congelado
    # por baixo do overlay de pausa, sem duplicar a logica de gather+draw.
    pause_scene = PauseScene(
        input_provider=game_loop.input_provider,
        game_loop=game_loop,
        audio_engine=game_loop.audio_engine,
        track_id=TRACK_ID,
        gameplay_scene=game_loop.current_scene,
        viewport_size=(config.window_width, config.window_height),
    )
    world.register_system(PauseOnActionSystem(game_loop.input_provider, game_loop, pause_scene))

    game_loop.audio_engine.load_track(TRACK_ID, str(TRACK_AUDIO_PATH))
    game_loop.audio_engine.play_track(TRACK_ID)

    game_loop.set_on_draw_ui(
        build_hud_callback(
            judgment_system=judgment,
            spawner_system=spawner,
            note_state_pool=world.get_pool(NOTE_STATE_POOL_NAME),
            viewport_size=(config.window_width, config.window_height),
            judgment_line_y=judgment_line_y,
            lane_x_positions=lane_x_positions,
        )
    )

    return game_loop
