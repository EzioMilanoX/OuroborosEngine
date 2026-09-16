# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Controle nos bindings, e o que isso corrige.

Ate aqui `PygameInputProvider` resolvia `KEY_*` e `MOUSE_*` e mais nada, e o
unico uso que a engine fazia de joystick era `set_rumble`. Um produto que
quisesse controle tinha de escrever o proprio adapter -- e ai um produto
importa pygame, que e exatamente o que o contrato 1 do import-linter existe
pra impedir. A lacuna da engine virava violacao da constituicao no produto.

Nao ha joystick nesta maquina nem no CI, e mesmo que houvesse ninguem
apertaria um botao no meio de um `pytest`. Entao o que entra aqui e a parte
que de fato pode estar errada -- **resolucao de codigo**, **o ou de varias
fontes** e a **histerese** do analogico -- com controles de mentira no lugar
do hardware. Deixar o pygame decidir testaria o pygame, e nao isto.
"""
import json

import pygame
import pytest

from ouroboros.adapters.pygame_backend.pygame_input_provider import (
    PygameInputProvider, _AXIS_ENGAGE, _AXIS_RELEASE)
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.null.null_input_provider import NullInputProvider


class _FakePad:
    """Um controle cujos botoes, eixos e chapeu o teste escreve a mao."""

    def __init__(self, hats: int = 1) -> None:
        self.buttons = {}
        self.axes = {}
        self.hat = (0, 0)
        self._hats = hats

    def get_button(self, index): return bool(self.buttons.get(index))
    def get_axis(self, index): return float(self.axes.get(index, 0.0))
    def get_numhats(self): return self._hats
    def get_hat(self, index): return self.hat


@pytest.fixture
def provider(tmp_path):
    """`poll` bombeia a fila de eventos, que exige video inicializado --
    `conftest.py` ja forca `SDL_VIDEODRIVER=dummy`, entao nao ha janela."""
    pygame.init()
    pygame.display.set_mode((64, 64))

    def _build(bindings, pads=()):
        path = tmp_path / "bindings.json"
        path.write_text(json.dumps(bindings), encoding="utf-8")
        provider = PygameInputProvider()
        provider.load_bindings(str(path))
        provider._pads = list(pads)
        provider._pad_count = len(pads)
        # Congela a sondagem: sem isto, `_resolve_pads` trocaria os controles
        # de mentira pelos de verdade (nenhum) no primeiro `poll`.
        provider._resolve_pads = lambda: provider._pads
        return provider
    return _build


class TestCodesResolve:
    def test_botoes_e_direcoes_viram_indices(self):
        assert PygameInputProvider._resolve_binding("PAD_A") == ("pad_button", 0, 0)
        assert PygameInputProvider._resolve_binding("PAD_START") == ("pad_button", 0, 7)
        assert PygameInputProvider._resolve_binding("PAD_LEFT") == ("pad_axis", 0, 0, -1.0)

    def test_o_digito_escolhe_o_controle(self):
        """E assim que um jogo de sofa da um controle a cada jogador. O digito
        e 1-based porque quem escreve o arquivo pensa em jogador 1 e 2."""
        assert PygameInputProvider._resolve_binding("PAD_A")[1] == 0
        assert PygameInputProvider._resolve_binding("PAD2_A")[1] == 1
        assert PygameInputProvider._resolve_binding("PAD4_DOWN")[1] == 3

    def test_um_codigo_inventado_levanta_na_carga(self):
        """Falhar ALTO, na abertura. Um `PAD_LT` aceito em silencio viraria
        uma acao que simplesmente nunca chega, e quem joga conclui que o
        controle esta quebrado."""
        with pytest.raises(ValueError):
            PygameInputProvider._resolve_binding("PAD_LT")


class TestSeveralSourcesForOneAction:
    def test_uma_lista_vale_como_ou(self, provider):
        """O arranjo normal. Sem isto, escolher o controle custaria o teclado,
        e num jogo local a dois os dois convivem na mesma partida."""
        pad = _FakePad()
        input_provider = provider({"jump": ["KEY_SPACE", "PAD_A"]}, pads=[pad])
        input_provider.poll()
        assert not input_provider.is_action_held("jump")

        pad.buttons[0] = True
        input_provider.poll()
        assert input_provider.is_action_held("jump")

    def test_um_codigo_sozinho_continua_valendo(self, provider):
        """Todo arquivo de bindings que ja existe usa uma string. Aceitar so
        lista quebraria os cinco produtos da engine de uma vez."""
        input_provider = provider({"jump": "PAD_A"}, pads=[_FakePad()])
        input_provider._pads[0].buttons[0] = True
        input_provider.poll()
        assert input_provider.is_action_held("jump")

    def test_cada_controle_dirige_o_seu_jogador(self, provider):
        pads = [_FakePad(), _FakePad()]
        input_provider = provider(
            {"jump": "PAD_A", "p2_jump": "PAD2_A"}, pads=pads)

        pads[0].buttons[0] = True
        input_provider.poll()
        assert input_provider.is_action_held("jump")
        assert not input_provider.is_action_held("p2_jump")

        pads[0].buttons[0] = False
        pads[1].buttons[0] = True
        input_provider.poll()
        assert input_provider.is_action_held("p2_jump")
        assert not input_provider.is_action_held("jump")

    def test_controle_ausente_nao_levanta(self, provider):
        """Mesmo criterio de `set_rumble`: hardware que nao esta la nunca e o
        motivo de o jogo fechar. Vale para o controle que nunca existiu e
        para o que foi arrancado no meio da partida."""
        pad = _FakePad()
        input_provider = provider({"jump": "PAD2_A"}, pads=[pad])
        input_provider.poll()
        assert not input_provider.is_action_held("jump")

        input_provider._pads = []
        input_provider.poll()
        assert not input_provider.is_action_held("jump")


class TestEdgesAndHysteresis:
    def test_segurar_o_botao_produz_uma_borda_so(self, provider):
        """Menus inteiros andam por `is_action_pressed`. Sem a borda ser uma
        so, descer um item viraria descer a lista."""
        pad = _FakePad()
        input_provider = provider({"down": "PAD_A"}, pads=[pad])
        pad.buttons[0] = True

        input_provider.poll()
        assert input_provider.is_action_pressed("down")
        input_provider.poll()
        assert not input_provider.is_action_pressed("down")
        assert input_provider.is_action_held("down")

        pad.buttons[0] = False
        input_provider.poll()
        assert input_provider.is_action_released("down")

    def test_o_analogico_engata_e_solta_em_soleiras_diferentes(self, provider):
        pad = _FakePad(hats=0)
        input_provider = provider({"right": "PAD_RIGHT"}, pads=[pad])

        pad.axes[0] = 0.40
        input_provider.poll()
        assert not input_provider.is_action_held("right"), "0.40 nao engata"

        pad.axes[0] = 0.70
        input_provider.poll()
        assert input_provider.is_action_held("right")

        pad.axes[0] = 0.40
        input_provider.poll()
        assert input_provider.is_action_held("right"), "engatado, 0.40 segura"

        pad.axes[0] = 0.20
        input_provider.poll()
        assert not input_provider.is_action_held("right")

    def test_um_polegar_parado_na_fronteira_nao_manda_bordas(self, provider):
        """O motivo de a histerese existir. Com uma soleira so, o tremor de um
        analogico em repouso atravessa um menu sozinho."""
        pad = _FakePad(hats=0)
        input_provider = provider({"down": "PAD_DOWN"}, pads=[pad])
        bordas = 0
        for i in range(40):
            pad.axes[1] = 0.42 + (0.04 if i % 2 else -0.04)
            input_provider.poll()
            if input_provider.is_action_pressed("down"):
                bordas += 1
        assert bordas == 0

    def test_as_duas_soleiras_nao_se_cruzam(self):
        assert _AXIS_RELEASE < _AXIS_ENGAGE, "sem vao nao ha histerese"

    def test_a_histerese_e_por_EIXO_e_nao_por_acao(self, provider):
        """Duas acoes no mesmo eixo, e uma tecla segurando uma delas: se o
        engate fosse guardado por acao, a tecla mudaria a soleira do
        analogico da outra."""
        pad = _FakePad(hats=0)
        input_provider = provider(
            {"a": "PAD_RIGHT", "b": "PAD_RIGHT"}, pads=[pad])
        pad.axes[0] = 0.70
        input_provider.poll()
        pad.axes[0] = 0.40
        input_provider.poll()
        assert input_provider.is_action_held("a")
        assert input_provider.is_action_held("b")


class TestTheDpadAndTheStickAreTheSameIntent:
    def test_o_direcional_manda_quando_esta_em_uso(self, provider):
        """Ele e digital: um 1.0 exato nunca pode perder para o tremor do
        analogico parado ao lado."""
        pad = _FakePad()
        input_provider = provider({"right": "PAD_RIGHT"}, pads=[pad])
        pad.axes[0] = 0.0
        pad.hat = (1, 0)
        input_provider.poll()
        assert input_provider.is_action_held("right")

    def test_cima_no_chapeu_e_cima_na_tela(self, provider):
        """O chapeu reporta CIMA como +1 e o analogico como -1. Com o sinal
        trocado, um menu anda ao contrario -- e nada no codigo diria qual dos
        dois esta errado."""
        pad = _FakePad()
        input_provider = provider({"up": "PAD_UP", "down": "PAD_DOWN"}, pads=[pad])
        pad.hat = (0, 1)
        input_provider.poll()
        assert input_provider.is_action_held("up")
        assert not input_provider.is_action_held("down")


class TestCountingPads:
    def test_o_contrato_responde_zero_por_default(self):
        """Backends sem controle continuam validos -- e um produto que
        perguntasse e recebesse erro teria de saber qual backend esta rodando,
        que e justamente o que a interface existe pra esconder."""
        assert not getattr(IInputProvider.connected_pads, "__isabstractmethod__", False)
        assert NullInputProvider().connected_pads() == 0

    def test_o_backend_conta_os_que_estao_la(self, provider):
        input_provider = provider({"jump": "PAD_A"}, pads=[_FakePad(), _FakePad()])
        assert input_provider.connected_pads() == 2
