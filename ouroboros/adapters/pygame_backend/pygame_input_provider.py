# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao concreta de IInputProvider sobre pygame.event/pygame.key."""
from __future__ import annotations

import json
import re

import pygame

from ouroboros.interfaces.input_provider import IInputProvider

_MOUSE_BUTTON_INDEX = {"MOUSE_LEFT": 0, "MOUSE_MIDDLE": 1, "MOUSE_RIGHT": 2}

_PAD_BUTTON_INDEX = {
    "A": 0, "B": 1, "X": 2, "Y": 3,
    "LB": 4, "RB": 5, "BACK": 6, "START": 7,
}
"""Numeracao de fato de todo controle que se apresenta como XInput -- o padrao
de Xbox, que DualShock e os genericos seguem quando o SDL os mapeia."""

_PAD_AXIS_DIRECTION = {
    "LEFT": (0, -1.0), "RIGHT": (0, 1.0),
    "UP": (1, -1.0), "DOWN": (1, 1.0),
}
"""Direcao -> (eixo, sinal). O analogico esquerdo e o direcional entram pelo
MESMO codigo: para o jogo sao a mesma intencao, e obrigar quem joga a saber
qual dos dois a interface escuta seria uma pergunta sem resposta boa."""

_PAD_CODE = re.compile(r"^PAD(\d*)_(.+)$")

_AXIS_ENGAGE = 0.55
_AXIS_RELEASE = 0.30
"""Duas soleiras, e nao uma.

Um analogico em repouso nao para em zero: fica tremendo perto dele. Com uma
soleira so, um polegar parado na fronteira manda dezenas de bordas por
segundo -- um personagem vibra no lugar, um cursor de menu atravessa a lista
sozinho. Com histerese a direcao so ENGATA em 0.55 e so SOLTA abaixo de 0.30,
e o tremor inteiro acontece dentro do vao."""


class PygameInputProvider(IInputProvider):
    """
    Implementacao de `IInputProvider` sobre `pygame.event.get()` e
    `pygame.key.get_pressed()`/`pygame.mouse.get_pressed()`.

    Bindings (`data/input_bindings/*.json`) mapeiam nome de acao para um
    codigo textual, ou para uma LISTA deles:

    - `"KEY_<nome>"`, resolvido via `pygame.key.key_code` (ex.: `"KEY_A"`,
      `"KEY_SPACE"`);
    - `"MOUSE_LEFT"`/`"MOUSE_MIDDLE"`/`"MOUSE_RIGHT"`;
    - `"PAD_A"`, `"PAD_LB"`, `"PAD_START"`... para botao de controle, e
      `"PAD_LEFT"`/`"PAD_RIGHT"`/`"PAD_UP"`/`"PAD_DOWN"` para o analogico
      esquerdo ou o direcional. Um digito depois de `PAD` escolhe QUAL
      controle: `"PAD_A"` e o primeiro, `"PAD2_A"` o segundo, e assim por
      diante -- e assim que um jogo de sofa da um controle a cada jogador.

    Uma lista vale como **ou**: `["KEY_SPACE", "PAD_A"]` responde aos dois, e
    e o arranjo normal. Sem isso, escolher o controle custaria o teclado, e
    num jogo local a dois os dois arranjos convivem na mesma partida.

    Um controle ausente nunca levanta -- mesmo criterio de `set_rumble`. Um
    controle arrancado no meio de uma partida nao pode ser o motivo de o jogo
    fechar.
    """

    def __init__(self) -> None:
        self._bindings = {}
        self._current_held = {}
        self._previous_held = {}
        self._axes = {}
        self._wants_quit = False
        self._joystick = None
        self._joystick_probed = False
        self._pads = []
        self._pad_count = -1
        # Estado de engate por eixo -- e o que torna a histerese possivel.
        self._axis_engaged = {}
        self._cursor_x = 0.0
        self._cursor_y = 0.0

    def load_bindings(self, bindings_path: str) -> None:
        with open(bindings_path, "r", encoding="utf-8") as f:
            raw_bindings = json.load(f)
        self._bindings = {
            action: tuple(self._resolve_binding(code)
                          for code in (codes if isinstance(codes, list) else [codes]))
            for action, codes in raw_bindings.items()
        }

    @staticmethod
    def _resolve_binding(code_name: str):
        if code_name in _MOUSE_BUTTON_INDEX:
            return ("mouse", _MOUSE_BUTTON_INDEX[code_name])
        if code_name.startswith("KEY_"):
            key_name = code_name[len("KEY_"):].lower()
            return ("key", pygame.key.key_code(key_name))
        pad = _PAD_CODE.match(code_name)
        if pad is not None:
            # "PAD_A" e o primeiro controle, "PAD2_A" o segundo: o digito e
            # 1-based porque quem escreve o arquivo pensa em jogador 1 e 2.
            index = int(pad.group(1)) - 1 if pad.group(1) else 0
            name = pad.group(2)
            if name in _PAD_BUTTON_INDEX:
                return ("pad_button", index, _PAD_BUTTON_INDEX[name])
            if name in _PAD_AXIS_DIRECTION:
                axis, sign = _PAD_AXIS_DIRECTION[name]
                return ("pad_axis", index, axis, sign)
        raise ValueError(f"binding de input nao reconhecido: {code_name!r}")

    def poll(self) -> None:
        self._previous_held = dict(self._current_held)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._wants_quit = True

        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        pads = self._resolve_pads()
        current = {}
        for action_name, sources in self._bindings.items():
            held = False
            for source in sources:
                # Curto-circuito NAO serve aqui: `_pad_axis_held` guarda o
                # estado de engate de cada eixo, e pular a leitura deixaria
                # esse estado congelado no ultimo frame em que ele foi lido.
                if self._source_held(source, keys, mouse_buttons, pads):
                    held = True
            current[action_name] = held
        self._current_held = current

        self._cursor_x, self._cursor_y = (float(v) for v in pygame.mouse.get_pos())

    def is_action_pressed(self, action_name: str) -> bool:
        return self._current_held.get(action_name, False) and not self._previous_held.get(action_name, False)

    def is_action_held(self, action_name: str) -> bool:
        return self._current_held.get(action_name, False)

    def is_action_released(self, action_name: str) -> bool:
        return self._previous_held.get(action_name, False) and not self._current_held.get(action_name, False)

    def get_axis(self, axis_name: str) -> float:
        return self._axes.get(axis_name, 0.0)

    def get_cursor_position(self):
        return (self._cursor_x, self._cursor_y)

    def wants_quit(self) -> bool:
        return self._wants_quit

    def _source_held(self, source, keys, mouse_buttons, pads) -> bool:
        kind = source[0]
        if kind == "key":
            return bool(keys[source[1]])
        if kind == "mouse":
            return source[1] < len(mouse_buttons) and bool(mouse_buttons[source[1]])
        index = source[1]
        if index >= len(pads):
            # Controle desligado (ou nunca ligado): a acao simplesmente nao
            # vem dele. Nunca levanta -- mesmo criterio de `set_rumble`.
            self._axis_engaged.pop(source, None)
            return False
        if kind == "pad_button":
            try:
                return bool(pads[index].get_button(source[2]))
            except Exception:
                return False
        return self._pad_axis_held(source, pads[index])

    def _pad_axis_held(self, source, pad) -> bool:
        """Uma direcao do analogico esquerdo OU do direcional, com histerese.

        O direcional manda quando esta sendo usado: ele e digital, entao um
        1.0 exato nunca pode perder para o tremor do analogico parado ao lado.
        """
        _, _, axis, sign = source
        value = 0.0
        try:
            if pad.get_numhats() > 0:
                hat_x, hat_y = pad.get_hat(0)
                # O chapeu reporta CIMA como +1 e o analogico como -1. Sem
                # esta inversao um menu andaria ao contrario no direcional.
                value = float(hat_x) if axis == 0 else -float(hat_y)
        except Exception:
            value = 0.0
        if not value:
            try:
                value = float(pad.get_axis(axis))
            except Exception:
                return False

        engaged = self._axis_engaged.get(source, False)
        threshold = _AXIS_RELEASE if engaged else _AXIS_ENGAGE
        engaged = value * sign >= threshold
        self._axis_engaged[source] = engaged
        return engaged

    def _resolve_pads(self):
        """Reabre a lista quando o numero de controles muda.

        `get_count()` e barato e reflete o que o `pygame.event.get()` do
        proprio `poll` ja bombeou, entao ligar um controle com o jogo aberto
        funciona sem nenhum evento proprio."""
        try:
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            count = pygame.joystick.get_count()
        except Exception:
            return self._pads
        if count == self._pad_count:
            return self._pads
        self._pad_count = count
        pads = []
        for index in range(count):
            try:
                pad = pygame.joystick.Joystick(index)
                pad.init()
                pads.append(pad)
            except Exception:
                pass
        self._pads = pads
        return pads

    def connected_pads(self) -> int:
        return len(self._resolve_pads())

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
