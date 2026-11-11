# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Vitrine de estilos (ROADMAP fase 8): cada estilo gera todos os quadros no tamanho da tela,
os estilos saem diferentes entre si, e a composicao monta e desenha de verdade (pygame
real sob o driver dummy de tests/conftest.py).
"""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig

from games.vitrine_estilos import arte
from games.vitrine_estilos.composition import build_game

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "vitrine_estilos" / "config.json"


@pytest.fixture(scope="module")
def quadros():
    pygame.init()
    pygame.display.set_mode((1, 1))
    return {e: arte.gerar(e) for e in arte.ESTILOS}


def test_cada_estilo_gera_todos_os_quadros_no_tamanho_da_tela(quadros):
    for estilo, qs in quadros.items():
        assert len(qs) == arte.QUADROS, estilo
        assert all(q.get_size() == (arte.LARGURA, arte.ALTURA) for q in qs), estilo


def test_os_estilos_sao_diferentes_entre_si(quadros):
    medias = {e: pygame.transform.average_color(qs[0])[:3] for e, qs in quadros.items()}
    assert len(set(medias.values())) == len(arte.ESTILOS)
    assert medias["sumie"][0] > 180  # o papel claro
    assert medias["neon"][0] < 60  # o escuro do neon


def test_pixel_art_sai_em_blocos_nitidos(quadros):
    q = quadros["pixel"][0]
    for x in range(0, 60, 6):  # dentro de um bloco de 6x6 a cor nao muda
        assert q.get_at((x, 30)) == q.get_at((x + 5, 30))


def test_o_golpe_tem_antecipacao_corte_pausa_e_volta():
    assert arte.pose_t(0.3)["corte"] is None  # respirando em guarda
    assert arte.pose_t(0.65)["ang_espada"] < arte.GUARDA  # antecipacao: a espada recua para cima
    assert arte.pose_t(0.75)["corte"] is not None  # o corte
    assert arte.pose_t(0.83)["ang_espada"] == arte.FIM  # segura o golpe
    volta = arte.pose_t(0.999)["ang_espada"]
    assert abs(volta - arte.pose_t(0.0)["ang_espada"]) < 0.05  # o laco fecha sem salto


def test_o_cache_em_disco_so_repinta_quando_a_arte_muda(tmp_path, monkeypatch):
    from games.vitrine_estilos import composition

    class R:
        def load_texture(self, *a):
            pass

    chamadas = []
    original = arte.gerar
    monkeypatch.setattr(arte, "gerar", lambda e: chamadas.append(e) or original(e))
    composition.preparar_texturas(R(), tmp_path, ("pixel",))
    composition.preparar_texturas(R(), tmp_path, ("pixel",))
    assert chamadas == ["pixel"]  # a segunda vez so carrega
    (tmp_path / "versao_pixel.txt").write_text("outra", encoding="utf-8")
    composition.preparar_texturas(R(), tmp_path, ("pixel",))
    assert chamadas == ["pixel", "pixel"]


def test_a_vitrine_monta_troca_de_estilo_e_desenha(tmp_path):
    loop = build_game(EngineConfig.from_json(str(_CONFIG_PATH)), pasta=tmp_path)
    cena = loop.current_scene
    loop.tick_once(1 / 60)
    assert len(list(tmp_path.glob("*.png"))) == arte.QUADROS * len(arte.ESTILOS)
    assert cena.foco is None  # comeca na grade
    cena.foco = 2
    loop.tick_once(1 / 60)
    tela = pygame.display.get_surface()
    assert pygame.transform.average_color(tela)[0] > 180  # o papel do sumi-e na tela toda
    loop.renderer.shutdown()


def test_low_poly_e_3d_de_verdade_e_a_camera_passeia(quadros):
    from games.vitrine_estilos.tres_d import cena_lowpoly
    assert len(cena_lowpoly(0)) > 300  # malhas de triangulos
    a, b = quadros["lowpoly"][0], quadros["lowpoly"][3]
    assert pygame.image.tobytes(a, "RGB") != pygame.image.tobytes(b, "RGB")  # o angulo mudou


def test_malhas_fechadas_viram_para_fora():
    import numpy as np

    from games.vitrine_estilos import tres_d
    malhas = [(tres_d.bloco((0, 0, 0), 1.0, 1.0, 0.6, 1.0, (1, 1, 1)), (0, 0.5, 0)),
              (tres_d.icosaedro((0, 0, 0), 1, (1, 1, 1), sub=1), (0, 0, 0))]
    for tris, centro in malhas:
        for tri in tris:  # a normal de cada face aponta para longe do centro
            a, b, c = (np.array(p) for p in tri[:3])
            assert np.cross(b - a, c - a) @ ((a + b + c) / 3 - centro) > 0


def test_z_buffer_o_mais_perto_ganha_em_qualquer_ordem():
    import numpy as np

    from games.vitrine_estilos.tres_d import rasterizar
    xs, ys = np.array([[0.0, 9.0, 0.0]]), np.array([[0.0, 0.0, 9.0]])
    perto, longe = np.full((1, 3, 3), (255.0, 0, 0)), np.full((1, 3, 3), (0, 255.0, 0))
    fundo = np.zeros((10, 10, 3))
    for ordem in ((perto, longe), (longe, perto)):
        zs = [np.array([[1.0, 1, 1]]) if c is perto else np.array([[5.0, 5, 5]]) for c in ordem]
        img, _ = rasterizar(np.vstack([xs, xs]), np.vstack([ys, ys]), np.vstack(zs), np.vstack(ordem), fundo)
        assert np.allclose(img[2, 2], (255, 0, 0))


def test_terror_e_escuro_em_pixels_grandes_e_a_lanterna_varre(quadros):
    qs = quadros["terror"]
    assert pygame.transform.average_color(qs[0])[0] < 45  # quase tudo no escuro
    q = qs[12]
    for x in range(0, 90, 3):  # 320x180 ampliado 3x sem suavizar
        assert q.get_at((x, 270)) == q.get_at((x + 2, 271))
    assert pygame.image.tobytes(qs[12], "RGB") != pygame.image.tobytes(qs[36], "RGB")
