# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cena unica de batalha tatica (ROADMAP M13): turno por unidade, jogador via input direto, IA trivial pro time inimigo."""
from __future__ import annotations

from typing import Optional, Tuple

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer
from ouroboros.tactics.combat.schemas import Team
from ouroboros.tactics.grid.battlefield_grid import BattlefieldGrid
from ouroboros.tactics.grid.pathfinding import find_path, has_line_of_sight, reachable_cells
from ouroboros.tactics.turn_queue import TurnQueue

UNIT_POOL_NAME = "tactics_unit"
CELL_SIZE = 48.0

_ADJACENT_OFFSETS: Tuple[Tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
_BUDGET_TOLERANCE = 1e-6

_TEXT_WHITE = (255, 255, 255, 255)
_TEXT_GOLD = (255, 220, 120, 255)


def rebuild_occupancy_from_pool(world: World, grid: BattlefieldGrid) -> None:
    """Regathera o roster VIVO atual da pool `tactics_unit` e reconstroi a
    ocupacao da grade do zero (ver docstring de
    `BattlefieldGrid.rebuild_occupancy`). Deve ser chamado DEPOIS de
    `world.flush()` sempre que uma unidade morrer -- `world.destroy_entity`
    e DIFERIDO (so realmente desanexa as pools no proximo `flush()`, ver
    `ouroboros/core/world.py`), e esta cena NUNCA chama `world.step()`
    (turn-based, orientado a evento -- nao ha nada pra simular por
    frame), entao nada mais drena a fila de destruicao por ela. Sem o
    `flush()` explicito antes desta chamada, a unidade morta ainda
    apareceria como ocupante da sua ultima celula pra sempre."""
    unit_pool = world.get_pool(UNIT_POOL_NAME)
    entity_indices = unit_pool.active_entity_indices()
    view = unit_pool.active_view()
    grid.rebuild_occupancy(entity_indices, view["grid_x"][: unit_pool.count], view["grid_y"][: unit_pool.count])


class TacticsBattleScene(IScene):
    """
    Cena UNICA cobrindo a batalha inteira, com fase interna implicita (de
    quem e o `TurnQueue.current_entity_index` agora) -- mesmo idioma de
    `WizardScene`/`MenuScene`: le input diretamente em `update()`, nunca
    depende de nenhum `ISystem` (nenhum roda, ja que `world.step()` nunca e
    chamado aqui -- ver `rebuild_occupancy_from_pool`). Guarda uma
    `GameplayScene` pra delegar `render()` a ela (desenha o lote
    `transform`+`sprite` -- unidades e terreno), mesmo idioma de
    `PauseScene`.

    Turno do jogador: mover (uma celula por pressao de seta, validada
    contra `reachable_cells` recalculada a cada passo a partir da posicao
    ATUAL com o orcamento RESTANTE -- respeita terreno `DIFFICULT`, nao um
    contador ingenuo de "N passos") + atacar (uma vez, encerra o turno) OU
    encerrar o turno explicitamente sem atacar. Turno do inimigo (IA
    trivial, resolvido de uma vez so, sem animacao passo-a-passo): anda em
    direcao a unidade inimiga mais proxima (mira uma celula ADJACENTE a
    ela via `find_path` -- a propria celula dela esta ocupada e
    corretamente inalcancavel, ver docstring de `find_path`), ataca se
    ficar adjacente.
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        game_loop: GameLoop,
        grid: BattlefieldGrid,
        modifier_stack: ModifierStack,
        turn_queue: TurnQueue,
        viewport_size: Tuple[int, int],
    ) -> None:
        self._input_provider = input_provider
        self._game_loop = game_loop
        self._grid = grid
        self._modifier_stack = modifier_stack
        self._turn_queue = turn_queue
        self._viewport_width, self._viewport_height = viewport_size
        self._gameplay_scene = GameplayScene()
        self._remaining_move_budget = 0.0
        self._game_over_message: Optional[str] = None

    def on_enter(self, world: World, renderer: IRenderer) -> None:
        del renderer
        active_entity_index = self._turn_queue.current_entity_index
        if active_entity_index is not None:
            self._begin_turn_for_active_unit(world, active_entity_index)

    def update(self, world: World, delta_time: float) -> None:
        del delta_time
        if self._input_provider.is_action_pressed("quit"):
            self._game_loop.stop()
            return
        if self._game_over_message is not None:
            return

        active_entity_index = self._turn_queue.current_entity_index
        if active_entity_index is None:
            return  # defensivo -- _check_win_lose ja deveria ter disparado antes disso

        unit_pool = world.get_pool(UNIT_POOL_NAME)
        active_row = unit_pool.dense_row_of(active_entity_index)
        active_team = int(unit_pool.active_view()["team"][active_row])

        if active_team == Team.ENEMY:
            self._run_enemy_turn(world, active_entity_index)
        else:
            self._run_player_input(world, active_entity_index)

    def render(self, world: World, renderer: IRenderer) -> None:
        self._gameplay_scene.render(world, renderer)

        unit_pool = world.get_pool(UNIT_POOL_NAME)
        transform_pool = world.get_pool("transform")
        unit_view = unit_pool.active_view()
        entity_indices = unit_pool.active_entity_indices()
        transform_view = transform_pool.active_view()
        for row in range(unit_pool.count):
            entity_index = int(entity_indices[row])
            t_row = transform_pool.dense_row_of(entity_index)
            px = float(transform_view["position_x"][t_row])
            py = float(transform_view["position_y"][t_row])
            hp_text = f"{int(unit_view['current_hp'][row])}/{int(unit_view['max_hp'][row])}"
            renderer.draw_text(px, py - CELL_SIZE / 2.0 - 4.0, hp_text, 12, _TEXT_WHITE, anchor="center")

        if self._game_over_message is not None:
            renderer.draw_text(
                self._viewport_width / 2.0, self._viewport_height / 2.0,
                self._game_over_message, 32, _TEXT_GOLD, anchor="center",
            )
            renderer.draw_text(
                self._viewport_width / 2.0, self._viewport_height / 2.0 + 36.0,
                "ESC para sair", 16, _TEXT_WHITE, anchor="center",
            )
            return

        active_entity_index = self._turn_queue.current_entity_index
        if active_entity_index is not None:
            row = unit_pool.dense_row_of(active_entity_index)
            team_label = "Jogador" if int(unit_view["team"][row]) == Team.PLAYER else "Inimigo"
            renderer.draw_text(10, 10, f"Turno: {team_label} (unidade #{active_entity_index})", 18, _TEXT_WHITE)
            renderer.draw_text(10, 32, f"Movimento restante: {self._remaining_move_budget:.1f}", 14, _TEXT_WHITE)

    # ------------------------------------------------------------ jogador

    def _run_player_input(self, world: World, unit_entity_index: int) -> None:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        row = unit_pool.dense_row_of(unit_entity_index)
        view = unit_pool.active_view()
        x, y = int(view["grid_x"][row]), int(view["grid_y"][row])

        for action_name, offset in (
            ("move_right", (1, 0)), ("move_left", (-1, 0)),
            ("move_down", (0, 1)), ("move_up", (0, -1)),
        ):
            if self._input_provider.is_action_pressed(action_name):
                self._try_move(world, unit_entity_index, x, y, offset[0], offset[1])
                return

        if self._input_provider.is_action_pressed("attack"):
            if self._try_attack(world, unit_entity_index):
                self._advance_turn(world)
            return

        if self._input_provider.is_action_pressed("end_turn"):
            self._advance_turn(world)

    def _try_move(self, world: World, unit_entity_index: int, x: int, y: int, dx: int, dy: int) -> None:
        target = (x + dx, y + dy)
        if not self._grid.in_bounds(*target):
            return
        reachable = reachable_cells(self._grid, (x, y), self._remaining_move_budget, ignoring_entity_index=unit_entity_index)
        if target not in reachable:
            return  # bloqueado, ocupado, ou alem do orcamento restante

        cost = reachable[target]
        self._remaining_move_budget = max(0.0, self._remaining_move_budget - cost)
        self._move_unit_to(world, unit_entity_index, target[0], target[1])

    def _move_unit_to(self, world: World, unit_entity_index: int, grid_x: int, grid_y: int) -> None:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        row = unit_pool.dense_row_of(unit_entity_index)
        view = unit_pool.active_view()
        view["grid_x"][row] = grid_x
        view["grid_y"][row] = grid_y

        transform_pool = world.get_pool("transform")
        t_row = transform_pool.dense_row_of(unit_entity_index)
        t_view = transform_pool.active_view()
        t_view["position_x"][t_row] = (grid_x + 0.5) * CELL_SIZE
        t_view["position_y"][t_row] = (grid_y + 0.5) * CELL_SIZE

        rebuild_occupancy_from_pool(world, self._grid)

    # ------------------------------------------------------------ combate (compartilhado jogador/IA)

    def _find_adjacent_enemy(self, world: World, unit_entity_index: int) -> Optional[int]:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        row = unit_pool.dense_row_of(unit_entity_index)
        view = unit_pool.active_view()
        x, y = int(view["grid_x"][row]), int(view["grid_y"][row])
        my_team = int(view["team"][row])

        for dx, dy in _ADJACENT_OFFSETS:
            nx, ny = x + dx, y + dy
            if not self._grid.in_bounds(nx, ny):
                continue
            occupant = self._grid.occupant_at(nx, ny)
            if occupant == -1:
                continue
            occupant_row = unit_pool.dense_row_of(occupant)
            if int(view["team"][occupant_row]) == my_team:
                continue
            if not has_line_of_sight(self._grid, (x, y), (nx, ny)):
                continue
            return occupant
        return None

    def _try_attack(self, world: World, attacker_entity_index: int) -> bool:
        defender_entity_index = self._find_adjacent_enemy(world, attacker_entity_index)
        if defender_entity_index is None:
            return False
        self._resolve_attack(world, attacker_entity_index, defender_entity_index)
        return True

    def _resolve_attack(self, world: World, attacker_entity_index: int, defender_entity_index: int) -> None:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        attacker_row = unit_pool.dense_row_of(attacker_entity_index)
        defender_row = unit_pool.dense_row_of(defender_entity_index)
        view = unit_pool.active_view()

        attack_index = int(view["attack_attribute_index"][attacker_row])
        defense_index = int(view["defense_attribute_index"][defender_row])
        attack_value = float(self._modifier_stack.attributes[attack_index]["final_value"])
        defense_value = float(self._modifier_stack.attributes[defense_index]["final_value"])
        damage = max(1.0, attack_value - defense_value)

        remaining_hp = float(view["current_hp"][defender_row]) - damage
        view["current_hp"][defender_row] = max(0.0, remaining_hp)

        if remaining_hp <= 0.0:
            self._kill_unit(world, defender_entity_index)

    def _kill_unit(self, world: World, entity_index: int) -> None:
        packed = world.pack_current(entity_index)
        world.destroy_entity(packed)
        world.flush()  # CRITICO -- ver docstring de rebuild_occupancy_from_pool
        self._turn_queue.remove(entity_index)
        rebuild_occupancy_from_pool(world, self._grid)
        self._check_win_lose(world)

    def _check_win_lose(self, world: World) -> None:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        view = unit_pool.active_view()
        teams_alive = {int(team) for team in view["team"][: unit_pool.count]}
        if int(Team.PLAYER) not in teams_alive:
            self._game_over_message = "VOCE PERDEU"
        elif int(Team.ENEMY) not in teams_alive:
            self._game_over_message = "VOCE VENCEU"

    # ------------------------------------------------------------ turno

    def _advance_turn(self, world: World) -> None:
        next_entity_index = self._turn_queue.advance_to_next()
        if next_entity_index is not None:
            self._begin_turn_for_active_unit(world, next_entity_index)

    def _begin_turn_for_active_unit(self, world: World, entity_index: int) -> None:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        row = unit_pool.dense_row_of(entity_index)
        move_range_index = int(unit_pool.active_view()["move_range_attribute_index"][row])
        self._remaining_move_budget = float(self._modifier_stack.attributes[move_range_index]["final_value"])

    # ------------------------------------------------------------ IA (time inimigo)

    def _find_nearest_enemy_of(self, world: World, unit_entity_index: int) -> Optional[int]:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        row = unit_pool.dense_row_of(unit_entity_index)
        view = unit_pool.active_view()
        my_team = int(view["team"][row])
        x, y = int(view["grid_x"][row]), int(view["grid_y"][row])

        best_entity_index: Optional[int] = None
        best_distance: Optional[int] = None
        for other_index in unit_pool.active_entity_indices():
            other_index = int(other_index)
            if other_index == unit_entity_index:
                continue
            other_row = unit_pool.dense_row_of(other_index)
            if int(view["team"][other_row]) == my_team:
                continue
            ox, oy = int(view["grid_x"][other_row]), int(view["grid_y"][other_row])
            distance = abs(ox - x) + abs(oy - y)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_entity_index = other_index
        return best_entity_index

    def _run_enemy_turn(self, world: World, unit_entity_index: int) -> None:
        unit_pool = world.get_pool(UNIT_POOL_NAME)
        row = unit_pool.dense_row_of(unit_entity_index)
        view = unit_pool.active_view()
        x, y = int(view["grid_x"][row]), int(view["grid_y"][row])
        move_range_index = int(view["move_range_attribute_index"][row])
        move_budget = float(self._modifier_stack.attributes[move_range_index]["final_value"])

        target_entity_index = self._find_nearest_enemy_of(world, unit_entity_index)
        if target_entity_index is not None:
            target_row = unit_pool.dense_row_of(target_entity_index)
            target_x = int(view["grid_x"][target_row])
            target_y = int(view["grid_y"][target_row])

            best_path = None
            for dx, dy in _ADJACENT_OFFSETS:
                candidate_goal = (target_x + dx, target_y + dy)
                if not self._grid.in_bounds(*candidate_goal):
                    continue
                path = find_path(self._grid, (x, y), candidate_goal, ignoring_entity_index=unit_entity_index)
                if path is not None and (best_path is None or len(path) < len(best_path)):
                    best_path = path

            if best_path is not None:
                self._walk_path_within_budget(world, unit_entity_index, best_path, move_budget)

        self._try_attack(world, unit_entity_index)  # resultado ignorado -- ataca ou nao, o turno acaba de qualquer jeito
        self._advance_turn(world)

    def _walk_path_within_budget(
        self, world: World, unit_entity_index: int, path, move_budget: float
    ) -> None:
        """Anda ao longo de `path` (que inclui a posicao ATUAL em `path[0]`)
        ate o orcamento acabar -- resolve o movimento inteiro da IA de uma
        vez so (sem animacao passo-a-passo, decisao de escopo do v1)."""
        spent = 0.0
        final_x, final_y = path[0]
        for next_x, next_y in path[1:]:
            step_cost = self._grid.move_cost_at(next_x, next_y)
            if spent + step_cost > move_budget + _BUDGET_TOLERANCE:
                break
            spent += step_cost
            final_x, final_y = next_x, next_y

        if (final_x, final_y) != path[0]:
            self._move_unit_to(world, unit_entity_index, final_x, final_y)
