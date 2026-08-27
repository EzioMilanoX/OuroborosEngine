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

from games.rhythm_game import composition
from games.rhythm_game.composition import (
    LANE_POOL_NAME,
    NOTE_STATE_POOL_NAME,
    THREAT_TYPE_POOL_NAME,
    build_game,
)

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
