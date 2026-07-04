"""Le data/difficulties/*.json e expoe parametros de dificuldade como dados puros."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple


class DifficultyDefinitionError(Exception):
    """Levantado quando um arquivo de dificuldade nao existe ou esta
    estruturalmente malformado.
    """


class DifficultyLoader:
    """Le `data/difficulties/*.json` e expoe os parametros de dificuldade
    como dados puros, nunca como constantes hardcoded em Python.

    Roda fora do loop de gameplay (selecao de dificuldade em menu/config).
    """

    def __init__(self, difficulties_directory: Path) -> None:
        """Aponta para o diretorio contendo os arquivos `*.json` de dificuldade."""
        self._difficulties_directory = Path(difficulties_directory)

    def load(self, difficulty_id: str) -> Dict[str, object]:
        """Le e valida `<difficulty_id>.json`, retorna seus parametros como dict.

        Levanta `DifficultyDefinitionError` se o arquivo nao existir ou
        estiver malformado.
        """
        path = self._difficulties_directory / f"{difficulty_id}.json"
        if not path.is_file():
            raise DifficultyDefinitionError(
                f"arquivo de dificuldade '{difficulty_id}' nao encontrado em {path}"
            )
        with path.open("r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise DifficultyDefinitionError(f"JSON invalido em {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise DifficultyDefinitionError(
                f"arquivo de dificuldade '{difficulty_id}' deve conter um objeto JSON no nivel raiz"
            )
        return data

    def list_available(self) -> Tuple[str, ...]:
        """Retorna os ids de todas as dificuldades disponiveis, descobertos
        por varredura de arquivos (nunca uma lista hardcoded).
        """
        return tuple(sorted(path.stem for path in self._difficulties_directory.glob("*.json")))
