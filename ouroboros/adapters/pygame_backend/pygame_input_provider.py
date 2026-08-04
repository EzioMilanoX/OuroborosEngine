# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao concreta de IInputProvider sobre pygame.event/pygame.key."""
from __future__ import annotations

import json

import pygame

from ouroboros.interfaces.input_provider import IInputProvider

_MOUSE_BUTTON_INDEX = {"MOUSE_LEFT": 0, "MOUSE_MIDDLE": 1, "MOUSE_RIGHT": 2}


class PygameInputProvider(IInputProvider):
    """
    Implementacao de `IInputProvider` sobre `pygame.event.get()` e
    `pygame.key.get_pressed()`/`pygame.mouse.get_pressed()`.

    Bindings (`data/input_bindings/*.json`) mapeiam nome de acao para um
    codigo textual: `"KEY_<nome>"` (resolvido via
    `pygame.key.key_code`, ex.: `"KEY_A"` -> tecla A, `"KEY_SPACE"` ->
    barra de espaco) ou `"MOUSE_LEFT"`/`"MOUSE_MIDDLE"`/`"MOUSE_RIGHT"`.
    """

    def __init__(self) -> None:
        self._bindings = {}
        self._current_held = {}
        self._previous_held = {}
        self._axes = {}
        self._wants_quit = False
        self._joystick = None
        self._joystick_probed = False

    def load_bindings(self, bindings_path: str) -> None:
        with open(bindings_path, "r", encoding="utf-8") as f:
            raw_bindings = json.load(f)
        self._bindings = {action: self._resolve_binding(code) for action, code in raw_bindings.items()}

    @staticmethod
    def _resolve_binding(code_name: str):
        if code_name in _MOUSE_BUTTON_INDEX:
            return ("mouse", _MOUSE_BUTTON_INDEX[code_name])
        if code_name.startswith("KEY_"):
            key_name = code_name[len("KEY_"):].lower()
            return ("key", pygame.key.key_code(key_name))
        raise ValueError(f"binding de input nao reconhecido: {code_name!r}")

    def poll(self) -> None:
        self._previous_held = dict(self._current_held)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._wants_quit = True

        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        current = {}
        for action_name, (kind, code) in self._bindings.items():
            if kind == "key":
                current[action_name] = bool(keys[code])
            else:
                current[action_name] = code < len(mouse_buttons) and bool(mouse_buttons[code])
        self._current_held = current

    def is_action_pressed(self, action_name: str) -> bool:
        return self._current_held.get(action_name, False) and not self._previous_held.get(action_name, False)

    def is_action_held(self, action_name: str) -> bool:
        return self._current_held.get(action_name, False)

    def is_action_released(self, action_name: str) -> bool:
        return self._previous_held.get(action_name, False) and not self._current_held.get(action_name, False)

    def get_axis(self, axis_name: str) -> float:
        return self._axes.get(axis_name, 0.0)

    def wants_quit(self) -> bool:
        return self._wants_quit

    def _resolve_joystick(self):
        """Resolve (e cacheia) o primeiro joystick/controle conectado sob
        demanda -- NUNCA no construtor, para nao pagar o custo de sondar
        hardware em jogos que nunca chamam `set_rumble`. `None` se nao
        houver controle ou o subsistema nao inicializar (teclado/mouse
        continuam funcionando normalmente)."""
        if self._joystick_probed:
            return self._joystick
        self._joystick_probed = True
        try:
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                self._joystick = pygame.joystick.Joystick(0)
                self._joystick.init()
        except pygame.error:
            self._joystick = None
        return self._joystick

    def set_rumble(self, low_freq: float, high_freq: float, duration_sec: float) -> None:
        """Aciona os dois motores de vibracao do primeiro controle
        conectado (`Joystick.rumble`, pygame-ce); no-op silencioso sem
        controle, sem suporte a force feedback do driver/SO, ou em
        qualquer outro erro de hardware -- vibracao e feedback cosmetico,
        nunca pode derrubar o loop de jogo."""
        joystick = self._resolve_joystick()
        if joystick is None:
            return
        try:
            joystick.rumble(
                max(0.0, min(1.0, low_freq)),
                max(0.0, min(1.0, high_freq)),
                int(max(0.0, duration_sec) * 1000.0),
            )
        except pygame.error:
            pass
