"""HUD minimo: score/combo/precisao + linha de julgamento + particulas de acerto + tela de fim de musica."""
from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

import numpy as np

from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.core.particle_storage import ParticleStorage
from ouroboros.interfaces.renderer import IRenderer
from ouroboros.rhythm.runtime.judgment_system import JudgmentSystem
from ouroboros.rhythm.runtime.rhythm_spawner_system import RhythmSpawnerSystem

_WHITE = (255, 255, 255, 255)
_GOLD = (255, 220, 120, 255)
_LILAC = (200, 200, 255, 255)
_LINE_COLOR = (255, 255, 255, 160)


def build_hud_callback(
    judgment_system: JudgmentSystem,
    spawner_system: RhythmSpawnerSystem,
    note_state_pool: ComponentPool,
    viewport_size: Tuple[int, int],
    judgment_line_y: float,
    lane_x_positions: Sequence[float],
    particle_storage: Optional[ParticleStorage] = None,
) -> Callable[[IRenderer], None]:
    """
    Constroi o callback passado a `GameLoop.set_on_draw_ui`. Fecha sobre
    referencias vivas (`judgment_system`, `spawner_system`,
    `note_state_pool`) -- por isso so pode ser construido DEPOIS que
    esses objetos existem, ou seja, depois que o script de composicao
    ja registrou seus proprios sistemas em cima do `GameLoop` retornado
    por `CompositionRoot.build()`.

    `particle_storage` (opcional, default `None` -- omitir preserva 100%
    o comportamento antigo, mesmo idioma do resto da composicao): se
    fornecido, desenha as particulas vivas (ROADMAP M11.3) ANTES do
    texto do HUD, pra elas nunca cobrirem score/combo/precisao.
    `set_on_draw_ui` e o UNICO slot de callback global do `GameLoop`
    (ver docstring) -- por isso o desenho de particulas entra AQUI, nao
    num segundo callback.
    """
    width, height = viewport_size
    line_left = min(lane_x_positions) - 40.0
    line_right = max(lane_x_positions) + 40.0

    def draw_ui(renderer: IRenderer) -> None:
        if particle_storage is not None and particle_storage.count > 0:
            view = particle_storage.active_view()
            positions_xy = np.stack([view["position_x"], view["position_y"]], axis=1)
            tint_rgba = np.stack([view["tint_r"], view["tint_g"], view["tint_b"], view["tint_a"]], axis=1)
            renderer.draw_particles(positions_xy, view["size"], tint_rgba, particle_storage.count)

        renderer.draw_text(10, 10, f"Score: {judgment_system.score}", 24, _WHITE)
        renderer.draw_text(10, 40, f"Combo: {judgment_system.combo}  (max {judgment_system.max_combo})", 18, _GOLD)
        renderer.draw_text(10, 64, f"Precisao: {judgment_system.accuracy * 100.0:.1f}%", 18, _LILAC)

        renderer.draw_ui_rect(line_left, judgment_line_y - 3.0, line_right - line_left, 6.0, _LINE_COLOR)

        if spawner_system.is_finished and note_state_pool.count == 0:
            renderer.draw_text(
                width / 2.0,
                height / 2.0,
                f"Fim de musica! Score final: {judgment_system.score}  (max combo {judgment_system.max_combo})",
                28,
                _WHITE,
                anchor="center",
            )
            renderer.draw_text(width / 2.0, height / 2.0 + 32.0, "ESC para voltar ao menu", 16, _LILAC, anchor="center")

    return draw_ui
