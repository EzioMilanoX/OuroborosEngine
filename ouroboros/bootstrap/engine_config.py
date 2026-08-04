# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""EngineConfig: configuracao imutavel de composicao, carregada de fontes externas (JSON/CLI)."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    """
    Configuracao de composicao do motor, lida de fora do codigo (ex.:
    arquivo JSON de configuracao ou argumentos de linha de comando)
    antes de `CompositionRoot` construir o `World` e os backends.
    Instanciada uma unica vez, fora do loop de gameplay.
    """

    window_width: int
    window_height: int
    window_title: str
    entity_capacity: int
    difficulty_path: str
    input_bindings_path: str

    @staticmethod
    def from_json(config_path: str) -> "EngineConfig":
        """Carrega e valida uma `EngineConfig` a partir de um arquivo JSON."""
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return EngineConfig(
            window_width=raw["window_width"],
            window_height=raw["window_height"],
            window_title=raw["window_title"],
            entity_capacity=raw["entity_capacity"],
            difficulty_path=raw["difficulty_path"],
            input_bindings_path=raw["input_bindings_path"],
        )
