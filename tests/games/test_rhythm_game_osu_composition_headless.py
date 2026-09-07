# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testa o modo Osu! do Jogo Musical (ROADMAP M15) de ponta a ponta com o
`CompositionRoot` real (backends Pygame reais, sob
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy ja forcados em tests/conftest.py) --
confirma que o vertical slice builda corretamente e roda muitos frames
reais sem crashar (o teste mais importante aqui: a mascara de
`NULL_PACKED_HANDLE` de `OsuPresentationSystem` sob o pipeline COMPLETO,
nao so em isolamento), mesmo padrao de
tests/games/test_rhythm_game_composition_headless.py.
"""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene

from games.rhythm_game.composition import build_menu_game
from games.rhythm_game.menu_scene import MenuScene
from games.rhythm_game.osu.composition import OSU_NOTE_STATE_POOL_NAME

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "rhythm_game" / "config.json"


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig.from_json(str(_CONFIG_PATH))


@pytest.fixture
def osu_game_loop(config: EngineConfig) -> GameLoop:
    """Builda o menu real e confirma a entrada `demo_track_osu` (a unica
    de modo `"osu"` no catalogo hoje) -- mesmo atalho de `build_game`
    (`games/rhythm_game/composition.py`), so escolhendo a linha certa em
    vez da linha 0."""
    loop = build_menu_game(config)
    menu_scene = loop.current_scene
    assert isinstance(menu_scene, MenuScene)
    osu_row_index = next(
        index for index, (song, _difficulty_id) in enumerate(menu_scene._rows) if song.mode == "osu"
    )
    menu_scene._cursor = osu_row_index
    menu_scene.confirm_selection()

    yield loop
    loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def _find_system(game_loop: GameLoop, class_name: str):
    return next(s for s in game_loop.world.systems if type(s).__name__ == class_name)


def test_confirming_the_osu_row_starts_gameplay_and_registers_osu_pools(osu_game_loop: GameLoop):
    assert isinstance(osu_game_loop.current_scene, GameplayScene)
    assert osu_game_loop.world.has_pool(OSU_NOTE_STATE_POOL_NAME)
    assert osu_game_loop.world.has_archetype("osu_note")
    assert osu_game_loop.world.has_archetype("osu_visual_marker")
    assert osu_game_loop.audio_engine.get_clock().is_playing()


def test_osu_judgment_and_spawner_systems_are_registered(osu_game_loop: GameLoop):
    assert _find_system(osu_game_loop, "OsuSpawnerSystem") is not None
    assert _find_system(osu_game_loop, "OsuPresentationSystem") is not None
    assert _find_system(osu_game_loop, "OsuJudgmentSystem") is not None


def test_hit_objects_eventually_spawn_as_real_time_advances(osu_game_loop: GameLoop, bind_quit_after):
    """Mesmo criterio de test_notes_eventually_spawn_as_real_time_advances
    (modo lane): depois de ~1s de frames reais, pelo menos um hit-object
    real (primeiro evento do beatmap gerado, em ~0.49s) deve ter sido
    instanciado."""
    bind_quit_after(osu_game_loop.input_provider, quit_after=60)

    osu_game_loop.run()

    note_state_pool = osu_game_loop.world.get_pool(OSU_NOTE_STATE_POOL_NAME)
    assert note_state_pool.count > 0


def test_a_never_clicked_circle_eventually_auto_misses(osu_game_loop: GameLoop, bind_quit_after):
    """Sem nenhum clique simulado, o primeiro hit-object real deve
    auto-errar (`OsuJudgmentSystem._auto_miss_never_clicked`) dentro de
    ~2s de frames reais -- prova de ponta a ponta de que o pipeline
    completo (clock real -> OsuSpawnerSystem -> OsuJudgmentSystem ->
    destroy_entity) julga corretamente sem depender so de testes
    isolados com NullAudioClock."""
    bind_quit_after(osu_game_loop.input_provider, quit_after=120)  # ~2s a 60fps

    osu_game_loop.run()

    judgment = _find_system(osu_game_loop, "OsuJudgmentSystem")
    assert judgment.judged_count > 0
    assert judgment.score == 0  # so houve auto-erro ate aqui -- nenhum acerto


def test_a_full_playthrough_runs_many_real_frames_without_crashing(osu_game_loop: GameLoop, bind_quit_after):
    """O teste mais importante deste arquivo: roda ~4s de frames reais
    (varios ciclos completos de spawn/aproximacao/auto-erro/destruicao,
    incluindo CIRCLEs e SLIDERs intercalados) sem crashar -- exercita a
    mascara de `NULL_PACKED_HANDLE` de `OsuPresentationSystem` sob o
    pipeline vetorizado COMPLETO (nao so em isolamento com poucas linhas
    construidas a mao), a mesma classe de bug que a critica de M15 achou
    como quase-certa de estourar no primeiro frame com qualquer CIRCLE em
    campo."""
    bind_quit_after(osu_game_loop.input_provider, quit_after=240)  # ~4s a 60fps

    osu_game_loop.run()  # nao deve levantar IndexError nem nenhuma outra excecao

    judgment = _find_system(osu_game_loop, "OsuJudgmentSystem")
    assert judgment.judged_count > 0


def test_pressing_quit_returns_to_the_menu_scene(osu_game_loop: GameLoop, bind_quit_after):
    """'quit' durante uma partida Osu! volta pro menu (mesmo criterio de
    lane-mode, ver test_pressing_quit_during_a_song_returns_to_the_menu_scene_instead_of_quitting)."""
    frame_count = {"n": 0}
    original_poll = osu_game_loop.input_provider.poll
    original_is_action_pressed = osu_game_loop.input_provider.is_action_pressed

    def counting_poll() -> None:
        original_poll()
        frame_count["n"] += 1

    def fake_is_action_pressed(action_name: str) -> bool:
        if action_name == "quit":
            return frame_count["n"] == 1
        return original_is_action_pressed(action_name)

    osu_game_loop.input_provider.poll = counting_poll
    osu_game_loop.input_provider.is_action_pressed = fake_is_action_pressed
    osu_game_loop.input_provider.wants_quit = lambda: frame_count["n"] >= 2

    osu_game_loop.run()

    assert isinstance(osu_game_loop.current_scene, MenuScene)
