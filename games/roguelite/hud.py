"""HUD minimo: camera segue o jogador + HP/inimigos restantes."""
from __future__ import annotations

from typing import Callable, Tuple

from ouroboros.core.world import World
from ouroboros.interfaces.renderer import IRenderer
from ouroboros.roguelite.systems.damage_system import DamageOnCollisionSystem

_WHITE = (255, 255, 255, 255)
_RED = (255, 90, 90, 255)


def build_hud_callback(
    world: World,
    health_pool_name: str,
    player_entity_index: int,
    damage_system: DamageOnCollisionSystem,
    viewport_size: Tuple[int, int],
) -> Callable[[IRenderer], None]:
    """
    Constroi o callback passado a `GameLoop.set_on_draw_ui`. Fecha
    sobre `world`/`damage_system` (ja existentes no momento da
    composicao). ANTES de desenhar qualquer texto, faz a CAMERA seguir
    o jogador -- reaproveita o hook `set_on_draw_ui` ja existente (que
    ja recebe `renderer` todo frame, mesmo mecanismo do HUD do Jogo
    Musical) em vez de qualquer codigo novo de engine: sem isso, o
    jogador sairia da tela pra sempre assim que deixasse a sala inicial
    (a masmorra e maior que uma tela).
    """
    transform_pool = world.get_pool("transform")
    health_pool = world.get_pool(health_pool_name)
    viewport_width, viewport_height = viewport_size
    half_width, half_height = viewport_width / 2.0, viewport_height / 2.0

    def draw_ui(renderer: IRenderer) -> None:
        if transform_pool.is_attached(player_entity_index):
            row = transform_pool.dense_row_of(player_entity_index)
            view = transform_pool.active_view()
            player_x = float(view["position_x"][row])
            player_y = float(view["position_y"][row])
            renderer.set_camera_offset(half_width - player_x, half_height - player_y)

        if health_pool.is_attached(player_entity_index):
            hp_row = health_pool.dense_row_of(player_entity_index)
            hp_view = health_pool.active_view()
            current_hp = float(hp_view["current_hp"][hp_row])
            max_hp = float(hp_view["max_hp"][hp_row])
        else:
            current_hp, max_hp = 0.0, 0.0

        renderer.draw_text(10, 10, f"HP: {current_hp:.0f} / {max_hp:.0f}", 22, _RED)
        renderer.draw_text(10, 38, f"Inimigos restantes: {damage_system.enemies_remaining}", 18, _WHITE)

    return draw_ui
