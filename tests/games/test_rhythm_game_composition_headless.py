"""
Testa `games.rhythm_game.composition.build_game` de ponta a ponta com o
`CompositionRoot` real (backends Pygame reais, sob
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy ja forcados em tests/conftest.py) --
confirma que o vertical slice builda corretamente e roda alguns frames
reais sem crashar, mesmo padrao de
tests/integration/test_composition_root_headless.py.
"""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop

from ouroboros.bootstrap.audio_bank_loader import AudioBankDefinitionError
from ouroboros.bootstrap.scene import GameplayScene

from games.rhythm_game import composition
from games.rhythm_game.composition import (
    LANE_POOL_NAME,
    MISS_SHAKE_INTENSITY,
    NOTE_STATE_POOL_NAME,
    THREAT_TYPE_POOL_NAME,
    build_game,
    build_menu_game,
)
from games.rhythm_game.menu_scene import MenuScene
from games.rhythm_game.pause_scene import PauseScene

_JUDGMENT_LINE_Y = 500.0  # config.json: window_height=600 -> judgment_line_y = 600 - 100 (ver composition.py)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "rhythm_game" / "config.json"


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig.from_json(str(_CONFIG_PATH))


@pytest.fixture
def game_loop(config: EngineConfig) -> GameLoop:
    loop = build_game(config)
    yield loop
    loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def test_build_game_loads_the_judgment_sfx_bank(game_loop: GameLoop):
    """Confirma, via a composicao real (nao um teste isolado do loader), que os 3 ids de
    SFX de julgamento foram de fato registrados no audio engine real."""
    sounds = game_loop.audio_engine._sounds
    for sfx_id in composition.SFX_IDS_BY_JUDGMENT:
        assert sfx_id in sounds


def test_build_menu_game_raises_early_when_the_note_texture_is_missing_from_the_manifest(
    config: EngineConfig, monkeypatch
):
    """Mesmo criterio do teste de SFX abaixo: um manifesto de texturas sem a
    entrada obrigatoria deve falhar na COMPOSICAO, nunca dentro do loop de
    gameplay quando uma nota tentar desenhar um texture_id nunca carregado."""
    monkeypatch.setattr(composition, "NOTE_TEXTURE_NAME", "nonexistent_texture_name")

    try:
        with pytest.raises(ValueError):
            build_menu_game(config)
    finally:
        pygame.display.quit()
        if pygame.mixer.get_init():
            pygame.mixer.quit()


def test_missed_notes_trigger_real_screen_shake_via_the_running_game(game_loop: GameLoop, bind_quit_after):
    """Prova de ponta a ponta (nao so o teste sintetico de _make_on_judgment):
    sem nenhuma tecla pressionada, a primeira nota real acaba auto-errando
    (JudgmentSystem._auto_miss_expired) e isso deve disparar screen shake de
    verdade no ScreenShakeUpdateSystem registrado por _start_song.

    Espiona ScreenShake.trigger() em vez de checar current_magnitude() APOS
    o run() inteiro: a duracao do shake (MISS_SHAKE_DURATION_SECONDS) e curta
    o bastante pra ja ter decaido de volta a 0.0 antes do teste conseguir
    checar, dependendo de QUANDO dentro da janela de frames o auto-erro
    acontece -- checar a CHAMADA em si, nao o estado residual, e robusto a
    isso."""
    screen_shake = next(
        s._screen_shake for s in game_loop.world.systems if type(s).__name__ == "ScreenShakeUpdateSystem"
    )
    trigger_calls = []
    original_trigger = screen_shake.trigger

    def spy_trigger(intensity: float, duration_seconds: float) -> None:
        trigger_calls.append((intensity, duration_seconds))
        original_trigger(intensity, duration_seconds)

    screen_shake.trigger = spy_trigger

    bind_quit_after(game_loop.input_provider, quit_after=140)  # ~2.3s a 60fps -- alem de approach+miss window

    game_loop.run()

    assert len(trigger_calls) > 0
    assert trigger_calls[0][0] == pytest.approx(MISS_SHAKE_INTENSITY)


def test_build_game_raises_early_when_sfx_id_is_missing_from_the_bank(config: EngineConfig, monkeypatch):
    """Um id incompativel entre `SFX_IDS_BY_JUDGMENT` e o banco carregado deve falhar
    na COMPOSICAO (AudioBankDefinitionError), nunca dentro do loop de gameplay."""
    monkeypatch.setattr(composition, "SFX_IDS_BY_JUDGMENT", ("judgment_perfect", "nonexistent_sfx_id", "judgment_miss"))

    try:
        with pytest.raises(AudioBankDefinitionError):
            build_game(config)
    finally:
        # build_game ja inicializou pygame (renderer+audio) antes de falhar --
        # limpa manualmente, ja que nao ha GameLoop pra chamar renderer.shutdown().
        pygame.display.quit()
        if pygame.mixer.get_init():
            pygame.mixer.quit()


def test_build_game_registers_product_specific_pools_and_archetype(game_loop: GameLoop):
    world = game_loop.world
    assert world.has_pool(LANE_POOL_NAME)
    assert world.has_pool(THREAT_TYPE_POOL_NAME)
    assert world.has_pool(NOTE_STATE_POOL_NAME)
    assert world.has_archetype("rhythm_note")


def test_music_is_loaded_and_playing(game_loop: GameLoop):
    clock = game_loop.audio_engine.get_clock()
    assert clock.is_playing()


def test_game_runs_several_real_frames_without_crashing(game_loop: GameLoop, bind_quit_after):
    """Roda o GameLoop de verdade (nao chamadas isoladas de update()) por um numero fixo
    de frames -- `bind_quit_after` monkeypatcha o input_provider real pra terminar de
    forma deterministica, sem isso `run()` bloquearia esperando fechamento de janela."""
    poll_count = bind_quit_after(game_loop.input_provider, quit_after=5)

    game_loop.run()

    assert poll_count["n"] == 5


def test_notes_eventually_spawn_as_real_time_advances(game_loop: GameLoop, bind_quit_after):
    """Depois de ~1s de frames reais rodando (o driver de audio dummy do SDL avanca
    `pygame.mixer.music.get_pos()` com o tempo real de parede, confirmado empiricamente),
    pelo menos uma nota do beatmap real gerado (primeiro evento em ~0.49s) deve ter sido
    instanciada -- prova que o pipeline completo (clock real -> RhythmSpawnerSystem ->
    create_entity) funciona de ponta a ponta, nao so em isolamento com NullAudioClock."""
    bind_quit_after(game_loop.input_provider, quit_after=60)  # ~1s a 60fps

    game_loop.run()

    note_state_pool = game_loop.world.get_pool(NOTE_STATE_POOL_NAME)
    assert note_state_pool.count > 0


def test_spawned_notes_have_real_lead_time_above_the_judgment_line(game_loop: GameLoop, bind_quit_after):
    """Regressao: `RhythmSpawnerSystem` deve nascer a nota com antecedencia real
    (via `approach_seconds`/`hit_times`, ver `approach_schedule.split_spawn_and_hit_schedules`)
    -- nao no proprio instante do acerto. Sem essa separacao, a nota nasceria
    praticamente EM CIMA da linha de julgamento (`position_y` proximo de
    `_JUDGMENT_LINE_Y`), sem nenhum tempo de reacao/scroll visivel."""
    bind_quit_after(game_loop.input_provider, quit_after=5)

    game_loop.run()

    note_state_pool = game_loop.world.get_pool(NOTE_STATE_POOL_NAME)
    assert note_state_pool.count > 0

    transform_pool = game_loop.world.get_pool("transform")
    entity_index = note_state_pool.active_entity_indices()[0]
    position_y = float(transform_pool.active_view()["position_y"][transform_pool.dense_row_of(entity_index)])

    assert position_y < _JUDGMENT_LINE_Y - 50.0, (
        "nota deveria estar visivelmente ACIMA da linha de julgamento logo apos nascer "
        "(antecedencia real via approach_seconds), nao em cima dela"
    )


@pytest.fixture
def menu_game_loop(config: EngineConfig) -> GameLoop:
    """Ao contrario da fixture `game_loop` (que ja usa o atalho `build_game`
    -- pula a navegacao, comeca com uma musica tocando), esta comeca de
    fato no MenuScene, pra testar a navegacao/confirmacao/retorno reais."""
    loop = build_menu_game(config)
    yield loop
    loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def _rig_action_toggle_on_frame(game_loop: GameLoop, action_name: str, toggle_on_frame_indices):
    """Generalizacao de `_rig_pause_toggle_on_frame`: `is_action_pressed(action_name)`
    retorna True exatamente nos indices de frame (0-based) listados, preservando
    o comportamento real (sempre False) pras demais acoes."""
    frame_count = {"n": 0}
    original_poll = game_loop.input_provider.poll
    original_is_action_pressed = game_loop.input_provider.is_action_pressed

    def counting_poll() -> None:
        original_poll()
        frame_count["n"] += 1

    def fake_is_action_pressed(name: str) -> bool:
        if name == action_name:
            return frame_count["n"] in toggle_on_frame_indices
        return original_is_action_pressed(name)

    game_loop.input_provider.poll = counting_poll
    game_loop.input_provider.is_action_pressed = fake_is_action_pressed
    return frame_count


def test_build_menu_game_starts_on_the_menu_scene(menu_game_loop: GameLoop):
    assert isinstance(menu_game_loop.current_scene, MenuScene)


def test_build_menu_game_lists_both_real_songs(menu_game_loop: GameLoop):
    """ROADMAP M11.2: o catalogo real ja tem 2 musicas (demo_track/second_track) --
    com 1 unica dificuldade real hoje, isso e o produto cartesiano inteiro."""
    menu_scene = menu_game_loop.current_scene
    assert isinstance(menu_scene, MenuScene)
    assert len(menu_scene._rows) == 2
    track_ids = {song.track_id for song, _difficulty_id in menu_scene._rows}
    assert track_ids == {"demo_track", "second_track"}


def test_confirming_the_menu_starts_the_selected_song_and_plays_music(menu_game_loop: GameLoop):
    frame_count = _rig_action_toggle_on_frame(menu_game_loop, "confirm", toggle_on_frame_indices={1})
    menu_game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 2

    menu_game_loop.run()

    assert isinstance(menu_game_loop.current_scene, GameplayScene)
    assert menu_game_loop.audio_engine.get_clock().is_playing()
    assert menu_game_loop.world.get_pool(NOTE_STATE_POOL_NAME) is not None


def test_pressing_quit_at_the_menu_stops_the_game_loop(menu_game_loop: GameLoop):
    frame_count = _rig_action_toggle_on_frame(menu_game_loop, "quit", toggle_on_frame_indices={1})
    # sentinela: se QuitOnActionSystem nao parar o loop, este teste travaria
    # rodando pra sempre -- wants_quit so vira True bem mais tarde, entao um
    # game_loop.stop() efetivo e a UNICA forma de run() retornar a tempo.
    menu_game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 100_000

    menu_game_loop.run()

    assert frame_count["n"] < 100_000


def test_pressing_quit_during_a_song_returns_to_the_menu_scene_instead_of_quitting(menu_game_loop: GameLoop):
    """ROADMAP M11.1: 'quit' durante uma partida volta pro menu (nao encerra
    o processo) -- so 'quit' NO MENU encerra de verdade (teste anterior)."""
    confirm_frames = _rig_action_toggle_on_frame(menu_game_loop, "confirm", toggle_on_frame_indices={1})
    menu_game_loop.input_provider.wants_quit = lambda: confirm_frames["n"] >= 2
    menu_game_loop.run()
    assert isinstance(menu_game_loop.current_scene, GameplayScene)
    clock = menu_game_loop.audio_engine.get_clock()
    assert clock.is_playing()

    quit_frames = _rig_action_toggle_on_frame(menu_game_loop, "quit", toggle_on_frame_indices={2})
    menu_game_loop.input_provider.wants_quit = lambda: quit_frames["n"] >= 3
    menu_game_loop.run()

    assert isinstance(menu_game_loop.current_scene, MenuScene)
    assert clock.is_playing() is False  # a musica abandonada foi parada (stop_track)
    assert menu_game_loop._on_draw_ui is None  # HUD da partida abandonada nao deve sobreviver ao retorno


def _rig_pause_toggle_on_frame(game_loop: GameLoop, toggle_on_frame_indices):
    """Instrumenta `game_loop.input_provider` com um contador de polls e faz
    `is_action_pressed("pause")` retornar True exatamente nos indices de frame (0-based)
    listados em `toggle_on_frame_indices` -- outras acoes continuam com o comportamento
    real (sempre False, ja que nada simula tecla nenhuma sob o driver dummy)."""
    frame_count = {"n": 0}
    original_poll = game_loop.input_provider.poll
    original_is_action_pressed = game_loop.input_provider.is_action_pressed

    def counting_poll() -> None:
        original_poll()
        frame_count["n"] += 1

    def fake_is_action_pressed(action_name: str) -> bool:
        if action_name == "pause":
            return frame_count["n"] in toggle_on_frame_indices
        return original_is_action_pressed(action_name)

    game_loop.input_provider.poll = counting_poll
    game_loop.input_provider.is_action_pressed = fake_is_action_pressed
    return frame_count


def test_pressing_pause_pushes_pause_scene_and_freezes_the_world(game_loop: GameLoop):
    frame_count = _rig_pause_toggle_on_frame(game_loop, toggle_on_frame_indices={2})
    game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 3

    game_loop.run()

    assert isinstance(game_loop.current_scene, PauseScene)


def test_world_and_audio_clock_stay_frozen_while_paused(game_loop: GameLoop):
    frame_count = _rig_pause_toggle_on_frame(game_loop, toggle_on_frame_indices={2})
    game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 3
    game_loop.run()
    assert isinstance(game_loop.current_scene, PauseScene)

    note_count_at_pause = game_loop.world.get_pool(NOTE_STATE_POOL_NAME).count
    clock = game_loop.audio_engine.get_clock()
    frozen_at = clock.now_seconds()
    assert clock.is_playing() is False

    # roda mais alguns frames "pausado" -- nada deve mudar, mesmo com tempo real passando
    game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 8
    game_loop.run()

    assert game_loop.world.get_pool(NOTE_STATE_POOL_NAME).count == note_count_at_pause
    assert clock.now_seconds() == frozen_at


def test_pressing_pause_again_pops_back_to_gameplay_and_resumes_audio(game_loop: GameLoop):
    """Nota: a prova de que o audio realmente CONGELA (nao avanca contra o tempo real de
    parede) e continua do valor certo ao retomar (nao reseta) ja e feita de forma direta e
    determinística em `tests/interfaces/test_pygame_backend_headless.py`
    (`test_pygame_audio_clock_freezes_now_seconds_while_paused`/`..._resumes_from_the_frozen_value...`)
    -- aqui so confirmamos que o ciclo completo de push/pop via input de verdade funciona."""
    frame_count = _rig_pause_toggle_on_frame(game_loop, toggle_on_frame_indices={2, 6})
    game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 7

    game_loop.run()

    assert isinstance(game_loop.current_scene, GameplayScene)
    clock = game_loop.audio_engine.get_clock()
    assert clock.is_playing() is True
