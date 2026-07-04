"""
Modulo NEUTRO -- a UNICA definicao compartilhada entre o escritor offline
e o leitor runtime de beatmap.json.

CRITICO: este modulo NUNCA importa librosa, nunca importa nada de
ouroboros.rhythm.offline.* e nunca importa pygame/godot. Isso e o que
garante que `ouroboros.rhythm.runtime.beatmap_loader` possa ser
importado no processo de jogo shippado SEM arrastar transitivamente a
dependencia pesada de librosa (e numba/scipy/soundfile) que o pipeline
offline usa. Tanto `ouroboros.rhythm.offline.beatmap_schema` quanto
`ouroboros.rhythm.runtime.beatmap_loader` importam
`BEATMAP_SCHEMA_VERSION` e os nomes de campo EXCLUSIVAMENTE deste
modulo -- nunca um do outro.
"""
from __future__ import annotations

from typing import Tuple

BEATMAP_SCHEMA_VERSION: int = 1
"""Versao do formato de `beatmap.json`. Incrementada a cada mudanca
incompativel de schema; `BeatmapLoader` (runtime) DEVE RECUSAR carregar
uma versao desconhecida em vez de tentar interpretar campos ausentes/
renomeados como se fossem a versao atual.
"""

REQUIRED_ROOT_FIELDS: Tuple[str, ...] = ("version", "track_id", "bpm", "threats")
"""Campos obrigatorios do documento raiz de `beatmap.json`."""

REQUIRED_THREAT_FIELDS: Tuple[str, ...] = ("timestamp_seconds", "threat_type", "lane", "strength")
"""Campos obrigatorios de cada entrada da lista `threats` do documento."""
