# OuroborosEngine

Engine hibrida, orientada a dados (data-oriented) e Zero-GC no gameplay,
escrita em Python. Nasceu como base para dois produtos —Roguelite e Jogo
Musical— e teve seu nucleo ECS provado por um terceiro, o port do BulletHell
(projeto irmao em `../BulletHell`, nao versionado neste repositorio).

- **Roguelite** (`games/roguelite/`) — geracao procedural de masmorra
  (`DungeonGenerator`/`StrictRandom`, seed determinístico), inimigos que
  perseguem o jogador, arma inicial com cooldown, dano por colisao,
  camera seguindo o jogador. Rodar com `python -m games.roguelite.main`.
- **Jogo Musical** (`games/rhythm_game/`) — pipeline offline de IA (`librosa`)
  que extrai BPM/onsets de um audio e gera um `beatmap.json` estatico,
  consumido em runtime por um `RhythmSpawnerSystem` sincronizado a um
  `IAudioClock` (nunca a delta-time); 4 lanes, julgamento de notas com SFX,
  pausa real. Rodar com `python -m games.rhythm_game.main`.

## A Constituicao da Engine

1. **Zero-GC no gameplay**: memoria pre-alocada via NumPy (Structure of
   Arrays); nenhuma instanciacao dinamica de objetos Python durante
   `World.step()`.
2. **Separacao Logic vs Presentation**: `ouroboros.core`/`roguelite`/`rhythm`
   nunca importam `pygame`/`godot` diretamente — apenas `ouroboros.interfaces`
   (ABCs). Backends concretos vivem isolados em `ouroboros.adapters` (ver
   `tooling/import_linter_contracts.ini`, verificado no CI a cada push/PR —
   `.github/workflows/ci.yml`).
3. **Data-Driven**: dificuldades, armas, arquetipos, beatmaps e bindings de
   input vem de `data/*.json`, nunca hardcoded em codigo Python.

## Pilares

| Pilar | Pacote | Status |
|---|---|---|
| 1 — Nucleo ECS Zero-GC | `ouroboros.core` | implementado |
| 2 — Camada de Abstracao (renderer/input/audio, SceneStack, texturas, particulas, screen shake) | `ouroboros.interfaces` + `ouroboros.adapters.pygame_backend` | implementado |
| 3 — Roguelite (Procedural) | `ouroboros.roguelite` + `games.roguelite` | vertical slice jogavel |
| 4 — Pipeline de IA (Jogo Musical) | `ouroboros.rhythm` + `games.rhythm_game` | vertical slice jogavel |
| 5 — Testes Headless | `tests/` | suite completa, roda em CI |

## Status

O roadmap pos-BulletHell (Fase 1, M1-M6) esta concluido: apresentacao 2.0
(formas/alpha/fx), texto e `SceneStack`, texturas e particulas, audio
data-driven, ergonomia do nucleo, e os dois vertical slices acima. Detalhes
e a Fase 2 (infraestrutura, adocao no BulletHell, aprofundamento dos
produtos) estao em `ROADMAP.md`.

## Rodando localmente

```
pip install -e ".[dev]"
pytest tests/ -q
lint-imports --config tooling/import_linter_contracts.ini
```

## Licenca

Licenciado sob a [Mozilla Public License 2.0](LICENSE) (MPL-2.0). Copyleft
por arquivo: qualquer arquivo desta engine que voce modificar e distribuir
deve continuar sob MPL-2.0, mas jogos construidos sobre a engine (em
arquivos proprios, importando `ouroboros`) podem ser fechados/comerciais
livremente.
