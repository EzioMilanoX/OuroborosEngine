# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
As duas coisas que todo produto reescreve, e erra igual.

`ResourceRoot` e `SaveFile` nao tem nada de engine no sentido de ECS -- nao
tocam `World`, nao rodam por frame. Estao aqui porque sao as duas peripecias
que TODO produto encontra e resolve do mesmo jeito:

* caminhos relativos deixam de funcionar no dia em que o produto vira um
  `.exe`, porque o diretorio atual passa a ser onde a pessoa clicou;
* um arquivo de save mal escrito derruba o jogo na abertura seguinte, e
  descobrir isso e mais caro que perder o save.

Os dois so falham em maquina de outra pessoa -- disco cheio, pasta
somente-leitura, desligamento no meio da escrita, bundle descompactado num
temporario. Por isso os testes forjam essas situacoes em vez de esperar.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from ouroboros.bootstrap.resources import ResourceRoot, frozen_root, is_frozen
from ouroboros.bootstrap.save_file import SaveFile, default_save_path


class TestResourceRootNeverTrustsTheCurrentDirectory:
    def test_resolve_caminho_relativo_contra_a_raiz_declarada(self, tmp_path, monkeypatch):
        """O defeito inteiro numa linha: `open("data/x.json")` procura no
        diretorio atual, e o diretorio atual nao e problema de quem joga."""
        resources = ResourceRoot(tmp_path)
        monkeypatch.chdir(tmp_path.parent)
        assert resources.resolve("data/x.json") == str(tmp_path / "data" / "x.json")

    def test_caminho_absoluto_passa_intacto(self, tmp_path):
        """Quem apontou para fora do bundle sabia o que estava fazendo -- uma
        dificuldade de teste, por exemplo."""
        resources = ResourceRoot(tmp_path)
        outside = Path(tmp_path).parent / "outro" / "x.json"
        assert resources.resolve(outside) == str(outside)

    def test_juntar_partes_da_um_caminho_absoluto(self, tmp_path):
        resources = ResourceRoot(tmp_path)
        assert resources("data", "levels") == tmp_path / "data" / "levels"

    def test_num_bundle_onefile_a_raiz_e_MEIPASS(self, tmp_path, monkeypatch):
        """PyInstaller onefile descompacta num temporario e aponta `_MEIPASS`
        para ele. A raiz de desenvolvimento nem existe nessa maquina."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        resources = ResourceRoot(tmp_path / "repo")
        assert resources.root == tmp_path / "bundle"
        assert is_frozen()

    def test_num_bundle_onedir_a_raiz_e_a_pasta_do_executavel(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "jogo" / "j.exe"))
        resources = ResourceRoot(tmp_path / "repo")
        assert resources.root == tmp_path / "jogo"

    def test_fora_de_um_bundle_nao_ha_raiz_congelada(self):
        assert frozen_root() is None
        assert not is_frozen()

    def test_a_raiz_e_consultada_a_cada_chamada(self, tmp_path, monkeypatch):
        """Guardar a raiz no construtor funcionaria em producao e mentiria em
        teste -- e e em teste que alguem simula estar congelado."""
        resources = ResourceRoot(tmp_path / "repo")
        assert resources.root == tmp_path / "repo"
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        assert resources.root == tmp_path / "bundle"


class TestReadingNeverRaises:
    def test_arquivo_ausente_vira_vazio(self, tmp_path):
        assert SaveFile(tmp_path / "nao_existe.json").read() == {}

    def test_json_corrompido_vira_vazio(self, tmp_path):
        """O caso real: desligamento no meio de uma escrita NAO atomica de
        alguma versao anterior. O jogo tem de abrir do zero, nao travar."""
        path = tmp_path / "save.json"
        path.write_text("{ isto nao e json", encoding="utf-8")
        assert SaveFile(path).read() == {}

    def test_raiz_que_nao_e_objeto_vira_vazio(self, tmp_path):
        """`[]` ou `"oi"` nao sao um save meio valido. Aceitar so adiaria o
        erro para o primeiro campo lido, e ai longe daqui."""
        for content in ("[]", '"oi"', "42", "null"):
            path = tmp_path / "save.json"
            path.write_text(content, encoding="utf-8")
            assert SaveFile(path).read() == {}, content

    def test_uma_pasta_no_lugar_do_arquivo_vira_vazio(self, tmp_path):
        directory = tmp_path / "save.json"
        directory.mkdir()
        assert SaveFile(directory).read() == {}


class TestWritingIsAtomic:
    def test_ida_e_volta(self, tmp_path):
        save = SaveFile(tmp_path / "save.json")
        assert save.write({"fases": [True, False], "volume": 0.7})
        assert save.read() == {"fases": [True, False], "volume": 0.7}

    def test_cria_a_pasta_se_precisar(self, tmp_path):
        save = SaveFile(tmp_path / "fundo" / "do" / "poco" / "save.json")
        assert save.write({"a": 1})
        assert save.read() == {"a": 1}

    def test_nao_sobra_temporario(self, tmp_path):
        """O `.tmp` e um detalhe de implementacao; deixa-lo para tras poria um
        arquivo estranho na pasta de quem joga."""
        save = SaveFile(tmp_path / "save.json")
        save.write({"a": 1})
        assert not list(tmp_path.glob("*.tmp"))

    def test_uma_escrita_que_falha_deixa_a_anterior_INTACTA(self, tmp_path, monkeypatch):
        """A razao de a escrita ser atomica. Meio arquivo e pior que nenhum,
        porque parece valido ate nao ser."""
        save = SaveFile(tmp_path / "save.json")
        save.write({"fases": 10})

        def explode(*args, **kwargs):
            raise OSError("disco cheio")

        monkeypatch.setattr(os, "replace", explode)
        assert save.write({"fases": 20}) is False
        assert save.read() == {"fases": 10}, "o save anterior foi perdido"
        assert not list(tmp_path.glob("*.tmp"))

    def test_payload_nao_serializavel_nao_derruba_o_jogo(self, tmp_path):
        """Erro de programacao -- e descobri-lo derrubando o jogo de quem esta
        jogando e a pior hora possivel."""
        save = SaveFile(tmp_path / "save.json")
        assert save.write({"x": object()}) is False
        assert save.read() == {}


class TestWhereTheSaveLives:
    def test_no_windows_vai_para_APPDATA(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        assert default_save_path("MeuJogo") == tmp_path / "MeuJogo" / "save.json"

    def test_sem_APPDATA_segue_o_XDG(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert default_save_path("MeuJogo", "p.json") == tmp_path / "MeuJogo" / "p.json"

    def test_nunca_ao_lado_do_codigo(self, monkeypatch, tmp_path):
        """Um repositorio e clonavel e somente-leitura em muitas maquinas, e
        um save dentro dele apareceria no `git status` a cada partida."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        destino = default_save_path("MeuJogo")
        raiz = Path(__file__).resolve().parents[2]
        assert raiz not in destino.parents
