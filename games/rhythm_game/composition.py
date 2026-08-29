"""Composicao do Jogo Musical: MenuScene (selecao musica/dificuldade) + montagem de uma partida por cima do CompositionRoot generico."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence, Tuple

import numpy as np

from ouroboros.bootstrap.audio_bank_loader import AudioBankDefinitionError, load_audio_bank
from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene
from ouroboros.core.memory.handles import PackedEntityId, unpack_index
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader
from ouroboros.rhythm.loaders.rhythm_difficulty_loader import RhythmDifficultyLoader
from ouroboros.rhythm.loaders.song_catalog_loader import SongCatalogLoader, SongEntry
from ouroboros.rhythm.runtime.approach_schedule import split_spawn_and_hit_schedules
from ouroboros.rhythm.runtime.beatmap_loader import BeatmapLoader
from ouroboros.rhythm.runtime.judgment_system import JudgmentSystem
from ouroboros.rhythm.runtime.note_scroll_system import NoteScrollSystem
from ouroboros.rhythm.runtime.rhythm_spawner_system import RhythmSpawnerSystem
from ouroboros.rhythm.runtime.schemas import NOTE_STATE_DTYPE

from games.rhythm_game.hud import build_hud_callback
from games.rhythm_game.menu_scene import MenuRow, MenuScene
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
RHYTHM_DIFFICULTIES_DIR = _REPO_ROOT / "data" / "difficulties" / "rhythm"
SONGS_DIR = _REPO_ROOT / "data" / "songs"

RHYTHM_JUDGMENT_AUDIO_PATH = _REPO_ROOT / "data" / "audio" / "rhythm_judgment.json"
SFX_IDS_BY_JUDGMENT = ("judgment_perfect", "judgment_good", "judgment_miss")

# Subpasta dedicada (nao `data/archetypes/` direto): `ArchetypeLoader.load_and_register_all`
# escaneia o diretorio inteiro nao-recursivamente, e `data/archetypes/*.json` no nivel raiz e
# tambem escaneado por completo pelos testes do Pilar 3 (Roguelite) contra um `world` generico
# que nao tem as pools `lane`/`threat_type`/`note_state` -- colocar o arquetipo deste jogo aqui
# evita esse conflito sem acoplar nada entre os dois produtos.
RHYTHM_ARCHETYPES_DIR = _REPO_ROOT / "data" / "archetypes" / "rhythm"


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


def _start_song(
    game_loop: GameLoop,
    config: EngineConfig,
    song: SongEntry,
    difficulty: dict,
    on_return_to_menu: Callable[[], None],
) -> None:
    """Monta um `World` NOVO (Pilar 1, via `CompositionRoot.build_world()` --
    nao reconstroi renderer/input/audio, que sobrevivem a troca de musica)
    pra `song`/`difficulty`, registra por cima as pools/arquetipo/sistemas
    especificos deste jogo (Pilar 4 + HUD), carrega o beatmap/audio da
    musica escolhida, e substitui o `World`/pilha de cenas do `game_loop`
    ja existente (ROADMAP M11.1 -- chamado a partir de `MenuScene.
    confirm_selection()`, nunca constroi seu proprio `GameLoop`).

    `on_return_to_menu`: registrado em `QuitOnActionSystem` -- 'quit'
    durante esta partida NAO encerra o processo (so o `MenuScene` faz
    isso), volta pro menu.
    """
    world = CompositionRoot(config).build_world()

    world.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]), dense_capacity=config.entity_capacity)
    world.create_pool(
        THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]), dense_capacity=config.entity_capacity
    )
    world.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE, dense_capacity=config.entity_capacity)

    # Carrega data/archetypes/rhythm/rhythm_note.json de verdade (nao um tuple hardcoded em
    # Python) -- so funciona porque as 3 pools especificas acima ja existem neste ponto;
    # ArchetypeLoader valida isso ANTES de registrar qualquer coisa.
    ArchetypeLoader(RHYTHM_ARCHETYPES_DIR).load_and_register_all(world)

    lane_x_positions = _lane_x_positions(config.window_width)
    judgment_line_y = float(config.window_height - 100)

    scheduled_threats = BeatmapLoader({BEATMAP_THREAT_TYPE_NAME: 0}).load(song.beatmap_path)
    spawn_threats, hit_times = split_spawn_and_hit_schedules(scheduled_threats, difficulty["approach_seconds"])

    audio_clock = game_loop.audio_engine.get_clock()
    audio_clock.calibrate_latency(difficulty["output_latency_seconds"])

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
    world.register_system(QuitOnActionSystem(game_loop.input_provider, on_quit_action=on_return_to_menu))

    # `gameplay_scene` e construida UMA VEZ aqui e reusada tanto pela PauseScene
    # (que precisa redesenhar o ultimo frame congelado por baixo do overlay de
    # pausa) quanto por `reset_scenes` abaixo -- NUNCA `game_loop.current_scene`
    # (que neste momento e o MenuScene/GameplayScene da musica ANTERIOR, nao a
    # cena desta partida).
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
            note_state_pool=world.get_pool(NOTE_STATE_POOL_NAME),
            viewport_size=(config.window_width, config.window_height),
            judgment_line_y=judgment_line_y,
            lane_x_positions=lane_x_positions,
        )
    )


def _build_menu_scene(game_loop: GameLoop, config: EngineConfig, rows: Sequence[MenuRow]) -> MenuScene:
    """Constroi um `MenuScene` novo sobre o mesmo catalogo `rows` -- chamado
    tanto na montagem inicial (`build_menu_game`) quanto ao voltar pro
    menu a partir de uma partida (`_make_on_return_to_menu`)."""

    def on_confirm(song: SongEntry, difficulty_id: str) -> None:
        difficulty = RhythmDifficultyLoader(RHYTHM_DIFFICULTIES_DIR).load(difficulty_id)
        _start_song(
            game_loop, config, song, difficulty,
            on_return_to_menu=_make_on_return_to_menu(game_loop, config, rows, song.track_id),
        )

    return MenuScene(
        input_provider=game_loop.input_provider,
        game_loop=game_loop,
        rows=rows,
        on_confirm=on_confirm,
        viewport_size=(config.window_width, config.window_height),
    )


def _make_on_return_to_menu(
    game_loop: GameLoop, config: EngineConfig, rows: Sequence[MenuRow], active_track_id: str
) -> Callable[[], None]:
    """`on_quit_action` de `QuitOnActionSystem` durante uma partida: para a
    musica em andamento, limpa o HUD/camera-shake residual da partida
    abandonada, e substitui a pilha de cenas por um `MenuScene` NOVO
    (nao o mesmo objeto -- `reset_scenes` exige uma cena, e este menu
    pode ter side-effects de cursor de uma sessao anterior que nao
    devem sobreviver a uma nova visita)."""

    def on_return_to_menu() -> None:
        game_loop.audio_engine.stop_track(active_track_id)
        game_loop.renderer.set_camera_offset(0.0, 0.0)
        game_loop.set_on_draw_ui(None)
        game_loop.reset_scenes(_build_menu_scene(game_loop, config, rows))

    return on_return_to_menu


def build_menu_game(config: EngineConfig) -> GameLoop:
    """
    Monta o `GameLoop` do Jogo Musical no estado de MENU (ROADMAP M11.1):
    `CompositionRoot(config).build()` da um `World` placeholder generico +
    os backends reais (construidos UMA VEZ, sobrevivem a qualquer musica
    escolhida depois via `replace_world`); carrega o banco de SFX de
    julgamento e o catalogo de musicas/dificuldades reais UMA VEZ aqui
    (recursos de vida-de-processo, ao contrario de `ParticleStorage`/
    `ScreenShake`, que sao por-partida); e substitui a pilha de cenas por
    um `MenuScene` ANTES do primeiro frame, entao a `GameplayScene` base
    (sobre o `World` placeholder vazio) nunca chega a rodar `world.step()`
    nem uma vez.
    """
    game_loop = CompositionRoot(config).build()

    # Carrega o banco de SFX e valida os ids ANTES de expor o menu -- um id
    # incompativel deve falhar aqui, na composicao, nunca dentro do loop de
    # gameplay quando JudgmentSystem tentar tocar um som inexistente (ver
    # docstring de load_audio_bank).
    loaded_sfx_ids = load_audio_bank(game_loop.audio_engine, str(RHYTHM_JUDGMENT_AUDIO_PATH))
    missing_sfx_ids = [sfx_id for sfx_id in SFX_IDS_BY_JUDGMENT if sfx_id not in loaded_sfx_ids]
    if missing_sfx_ids:
        raise AudioBankDefinitionError(
            f"SFX_IDS_BY_JUDGMENT referencia id(s) ausentes em {RHYTHM_JUDGMENT_AUDIO_PATH}: {missing_sfx_ids}"
        )

    songs = SongCatalogLoader(SONGS_DIR, repo_root=_REPO_ROOT).load_all()
    difficulty_ids = RhythmDifficultyLoader(RHYTHM_DIFFICULTIES_DIR).list_available()
    rows: Tuple[MenuRow, ...] = tuple(
        (song, difficulty_id) for song in songs for difficulty_id in difficulty_ids
    )

    game_loop.reset_scenes(_build_menu_scene(game_loop, config, rows))
    return game_loop


def build_game(config: EngineConfig) -> GameLoop:
    """Atalho de conveniencia: monta o menu (`build_menu_game`) e inicia
    direto a linha 0 do catalogo (primeira musica x primeira dificuldade),
    sem simular nenhuma tecla -- mesmo caminho de codigo que
    `MenuScene.confirm_selection()` usa, so acionado programaticamente
    (mesmo espirito do atalho `--play` do BulletHell, ver ROADMAP M8c).
    Usado por testes/ferramentas que precisam de uma partida pronta pra
    jogar sem dirigir a navegacao do menu.
    """
    game_loop = build_menu_game(config)
    menu_scene = game_loop.current_scene
    assert isinstance(menu_scene, MenuScene)
    menu_scene.confirm_selection()
    return game_loop
