# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le data/difficulties/rhythm/*.json e expoe parametros de dificuldade do Jogo Musical como dados puros."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple


class RhythmDifficultyDefinitionError(Exception):
    """Levantado quando um arquivo de dificuldade do Jogo Musical nao existe ou esta
    estruturalmente malformado.
    """


class RhythmDifficultyLoader:
    """Le `data/difficulties/rhythm/*.json` e expoe os parametros de dificuldade
    do Jogo Musical como dados puros, nunca como constantes hardcoded em Python.

    Subpasta dedicada (nao `data/difficulties/` direto): o Roguelite tem seu
    proprio `normal.json` no mesmo diretorio pai, distinguido hoje so por
    nome de arquivo -- uma varredura de diretorio (`list_available`) que
    escaneasse `data/difficulties/` inteiro pegaria os dois catalogos
    misturados. Mesma logica de `RHYTHM_ARCHETYPES_DIR` (Roguelite).

    Roda fora do loop de gameplay (menu/selecao de dificuldade).
    """

    def __init__(self, difficulties_directory: Path) -> None:
        """Aponta para o diretorio contendo os arquivos `*.json` de dificuldade do Jogo Musical."""
        self._difficulties_directory = Path(difficulties_directory)

    def load(self, difficulty_id: str) -> Dict[str, object]:
        """Le e valida `<difficulty_id>.json`, retorna seus parametros como dict.

        Levanta `RhythmDifficultyDefinitionError` se o arquivo nao existir ou
        estiver malformado.
        """
        path = self._difficulties_directory / f"{difficulty_id}.json"
        if not path.is_file():
            raise RhythmDifficultyDefinitionError(
                f"arquivo de dificuldade '{difficulty_id}' nao encontrado em {path}"
            )
        with path.open("r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise RhythmDifficultyDefinitionError(f"JSON invalido em {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RhythmDifficultyDefinitionError(
                f"arquivo de dificuldade '{difficulty_id}' deve conter um objeto JSON no nivel raiz"
            )
        return data

    def list_available(self) -> Tuple[str, ...]:
        """Retorna os ids de todas as dificuldades disponiveis, descobertos
        por varredura de arquivos (nunca uma lista hardcoded).
        """
        return tuple(sorted(path.stem for path in self._difficulties_directory.glob("*.json")))
