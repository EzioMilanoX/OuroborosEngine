"""Le data/archetypes/*.json e registra cada arquetipo no World."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

from ouroboros.core.world import World


class ArchetypeDefinitionError(Exception):
    """Levantado quando um JSON de arquetipo referencia um nome de pool
    inexistente no `World`, ou esta estruturalmente malformado.
    """


class ArchetypeLoader:
    """Le `data/archetypes/*.json` e registra cada arquetipo no `World`.

    Cada JSON descreve um arquetipo como uma lista nomeada de pools de
    componente (ex.: `["transform", "velocity", "hitbox"]`); este
    loader nunca hardcoda a composicao de um arquetipo em Python. Roda
    inteiramente fora do loop de gameplay, durante a inicializacao do
    `World`.
    """

    def __init__(self, archetypes_directory: Path) -> None:
        """Aponta para o diretorio contendo os arquivos `*.json` de arquetipo."""
        self._archetypes_directory = Path(archetypes_directory)

    def load_and_register_all(self, world: World) -> Dict[str, Tuple[str, ...]]:
        """Le todos os `*.json` do diretorio, valida que cada nome de
        pool referenciado ja existe em `world` (via `World.get_pool`/
        `has_pool`) ANTES de registrar qualquer coisa, chama
        `world.register_archetype(name, pool_names)` para cada um, e
        retorna um dict `archetype_name -> pool_names`.

        Levanta `ArchetypeDefinitionError` se algum JSON referenciar um
        nome de pool inexistente -- a validacao cruzada acontece antes de
        registrar QUALQUER arquetipo, para nunca deixar o `World` em
        estado parcialmente registrado.
        """
        parsed: Dict[str, Tuple[str, ...]] = {}

        for path in sorted(self._archetypes_directory.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError as exc:
                    raise ArchetypeDefinitionError(f"JSON invalido em {path}: {exc}") from exc

            if not isinstance(data, dict) or "id" not in data or "pools" not in data:
                raise ArchetypeDefinitionError(
                    f"arquivo de arquetipo {path} malformado -- campos obrigatorios 'id'/'pools' ausentes"
                )

            name = str(data["id"])
            pool_names = tuple(str(pool_name) for pool_name in data["pools"])

            if name in parsed:
                raise ArchetypeDefinitionError(f"arquetipo duplicado '{name}' encontrado em {path}")

            for pool_name in pool_names:
                if not world.has_pool(pool_name):
                    raise ArchetypeDefinitionError(
                        f"arquetipo '{name}' (arquivo {path}) referencia pool inexistente '{pool_name}'"
                    )

            parsed[name] = pool_names

        # Somente apos validar TODOS os arquivos (nenhum pool inexistente
        # referenciado por nenhum deles) e que o World e efetivamente mutado.
        for name, pool_names in parsed.items():
            world.register_archetype(name, pool_names)

        return parsed
