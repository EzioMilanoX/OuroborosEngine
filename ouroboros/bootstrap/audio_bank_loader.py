# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le um banco de SFX data-driven (JSON) e registra cada entrada num IAudioEngine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, FrozenSet

from ouroboros.interfaces.audio_engine import IAudioEngine

_VALID_TYPES = frozenset({"tone", "file"})
_VALID_TONE_KINDS = frozenset({"square", "noise", "sweep", "zap"})


class AudioBankDefinitionError(Exception):
    """Levantado quando um banco de SFX (JSON) esta estruturalmente
    malformado ou referencia um `type`/`kind` desconhecido."""


def load_audio_bank(audio_engine: IAudioEngine, bank_path: str) -> FrozenSet[str]:
    """Le o banco de SFX `bank_path` (dict JSON `nome -> definicao`) e
    registra cada entrada em `audio_engine`, fora do loop de gameplay
    (chamado pelo script de composicao de um produto, nunca de dentro
    de `ISystem.update()`).

    Cada definicao e `{"type": "tone", "kind": ..., "freq": ..., "duration": ...}`
    (som sintetizado via `IAudioEngine.register_tone`, sem asset nenhum) ou
    `{"type": "file", "path": ...}` (amostra pre-carregada via
    `IAudioEngine.load_sound`).

    Valida TODAS as entradas ANTES de registrar qualquer uma (mesmo
    idioma de `ArchetypeLoader.load_and_register_all`): um `type`
    desconhecido, um `kind` de tom desconhecido (sem essa checagem,
    `PygameAudioEngine.register_tone` cai silenciosamente para
    "square" em qualquer `kind` nao reconhecido -- um typo no JSON
    produziria o som errado em vez de falhar) ou um campo obrigatorio
    ausente levanta `AudioBankDefinitionError` antes de qualquer
    chamada a `audio_engine`, para nunca deixa-lo em estado
    parcialmente registrado.

    Retorna o `frozenset` dos nomes efetivamente registrados, para o
    chamador validar que os ids que pretende usar (ex.:
    `sfx_ids_by_judgment` de `JudgmentSystem`) de fato existem no
    banco -- uma falha por id incompativel deve aparecer aqui, na
    composicao, nunca dentro do loop de gameplay.
    """
    with open(bank_path, "r", encoding="utf-8") as handle:
        try:
            raw: Dict[str, Any] = json.load(handle)
        except json.JSONDecodeError as exc:
            raise AudioBankDefinitionError(f"JSON invalido em {bank_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise AudioBankDefinitionError(f"banco de SFX {bank_path} malformado -- esperado um objeto JSON")

    parsed: Dict[str, Dict[str, Any]] = {}
    for sound_id, definition in raw.items():
        if not isinstance(definition, dict) or "type" not in definition:
            raise AudioBankDefinitionError(
                f"entrada '{sound_id}' em {bank_path} malformada -- campo obrigatorio 'type' ausente"
            )

        sound_type = definition["type"]
        if sound_type not in _VALID_TYPES:
            raise AudioBankDefinitionError(
                f"entrada '{sound_id}' em {bank_path} tem type desconhecido '{sound_type}' "
                f"(validos: {sorted(_VALID_TYPES)})"
            )

        if sound_type == "tone":
            kind = definition.get("kind", "square")
            if kind not in _VALID_TONE_KINDS:
                raise AudioBankDefinitionError(
                    f"entrada '{sound_id}' em {bank_path} tem kind de tom desconhecido '{kind}' "
                    f"(validos: {sorted(_VALID_TONE_KINDS)})"
                )
            if "freq" not in definition or "duration" not in definition:
                raise AudioBankDefinitionError(
                    f"entrada '{sound_id}' em {bank_path} (type=tone) precisa de 'freq'/'duration'"
                )
        else:  # sound_type == "file"
            if "path" not in definition:
                raise AudioBankDefinitionError(
                    f"entrada '{sound_id}' em {bank_path} (type=file) precisa de 'path'"
                )

        parsed[sound_id] = definition

    # Somente apos validar TODAS as entradas e que o audio_engine e efetivamente mutado.
    for sound_id, definition in parsed.items():
        if definition["type"] == "tone":
            audio_engine.register_tone(
                sound_id,
                kind=definition.get("kind", "square"),
                freq=float(definition["freq"]),
                duration=float(definition["duration"]),
            )
        else:
            audio_engine.load_sound(sound_id, definition["path"])

    return frozenset(parsed.keys())
