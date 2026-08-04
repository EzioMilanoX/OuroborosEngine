# OuroborosEngine

Engine hibrida, orientada a dados (data-oriented) e Zero-GC no gameplay,
escrita em Python, servindo de base para dois produtos distintos:

- **Roguelite** — geracao procedural pesada (dungeons via seed/RNG estrito,
  `ModifierStack` que altera atributos via algebra vetorial).
- **Jogo Musical** — pipeline offline de IA (`librosa`) que extrai BPM/onsets
  de um audio e gera um `beatmap.json` estatico, consumido em runtime por um
  `RhythmSpawnerSystem` sincronizado a um `IAudioClock` (nunca a delta-time).

## A Constituicao da Engine

1. **Zero-GC no gameplay**: memoria pre-alocada via NumPy (Structure of
   Arrays); nenhuma instanciacao dinamica de objetos Python durante
   `World.step()`.
2. **Separacao Logic vs Presentation**: `ouroboros.core`/`roguelite`/`rhythm`
   nunca importam `pygame`/`godot` diretamente — apenas `ouroboros.interfaces`
   (ABCs). Backends concretos vivem isolados em `ouroboros.adapters` (ver
   `tooling/import_linter_contracts.ini`, executado em CI/pre-commit).
3. **Data-Driven**: dificuldades, armas, arquetipos, beatmaps e bindings de
   input vem de `data/*.json`, nunca hardcoded em codigo Python.

## Pilares

| Pilar | Pacote | Status |
|---|---|---|
| 1 — Nucleo ECS Zero-GC | `ouroboros.core` | assinaturas completas |
| 2 — Camada de Abstracao | `ouroboros.interfaces` | assinaturas completas |
| 3 — Roguelite (Procedural) | `ouroboros.roguelite` | em desenvolvimento |
| 4 — Pipeline de IA (Jogo Musical) | `ouroboros.rhythm` | em desenvolvimento |
| 5 — Testes Headless | `tests/` | em desenvolvimento |

## Status

Esqueleto inicial: apenas assinaturas de classes/metodos com docstrings
explicando responsabilidade e invariantes — nenhum corpo de metodo
implementado ainda.

## Licenca

Licenciado sob a [Mozilla Public License 2.0](LICENSE) (MPL-2.0). Copyleft
por arquivo: qualquer arquivo desta engine que voce modificar e distribuir
deve continuar sob MPL-2.0, mas jogos construidos sobre a engine (em
arquivos proprios, importando `ouroboros`) podem ser fechados/comerciais
livremente.
