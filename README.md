# OuroborosEngine

Engine hibrida, orientada a dados (data-oriented) e Zero-GC no gameplay,
escrita em Python. Nasceu como base para dois produtos —Roguelite e Jogo
Musical— teve seu nucleo ECS provado por um terceiro, o port do BulletHell
(projeto irmao em `../BulletHell`, nao versionado neste repositorio), e desde
entao ganhou mais tres vertical slices (Platformer, Turn-based Tactics, Card
Game) provando capacidades genericas novas — colisao contra tiles,
grid/pathfinding/turno, e um modelo de dados sem ECS.

- **Roguelite** (`games/roguelite/`) — geracao procedural de masmorra
  (`DungeonGenerator`/`StrictRandom`, seed determinístico), inimigos que
  perseguem o jogador, arma inicial com cooldown, dano por colisao,
  camera seguindo o jogador. Rodar com `python -m games.roguelite.main`.
- **Jogo Musical** (`games/rhythm_game/`) — pipeline offline de IA (`librosa`)
  que extrai BPM/onsets de um audio e gera um `beatmap.json` estatico
  (inclusive multi-camada via Perfis de Extracao, tag `"layer"`), consumido
  em runtime por um `RhythmSpawnerSystem` sincronizado a um `IAudioClock`
  (nunca a delta-time); menu real de selecao de musica/dificuldade
  (`MenuScene`, catalogo com 2 musicas), 4 lanes, julgamento de notas com
  SFX + particula no acerto + screen shake no erro, textura real de nota,
  pausa real. Rodar com `python -m games.rhythm_game.main`.
- **Platformer** (`games/platformer/`) — nivel ASCII hardcoded, colisao real
  contra tiles (`Grid2D`/`TileCollisionSystem`, resolucao por eixo) +
  gravidade opt-in (`GravitySystem`), corrida e pulo (so no chao). Rodar
  com `python -m games.platformer.main`.
- **Turn-based Tactics** (`games/tactics/`) — batalha em grade
  (`ouroboros.tactics`: `BattlefieldGrid`, A*/alcancaveis/linha de visao,
  `TurnQueue` por iniciativa), 2 unidades por time, mover/atacar/IA
  trivial. Rodar com `python -m games.tactics.main`.
- **Card Game** (`games/card_game/`) — baralho hardcoded (`ouroboros.cardgame`:
  `CardLoader`/`Zone`/vocabulario de efeitos, sem ECS), turno
  compra→principal→combate→fim, jogador vs. oponente estatico. Rodar com
  `python -m games.card_game.main`.

## A Constituicao da Engine

1. **Zero-GC no gameplay**: memoria pre-alocada via NumPy (Structure of
   Arrays); nenhuma instanciacao dinamica de objetos Python durante
   `World.step()`.
2. **Separacao Logic vs Presentation**: `ouroboros.core`/`roguelite`/`rhythm`
   nunca importam um backend concreto (`pygame`) diretamente — apenas
   `ouroboros.interfaces` (ABCs). Backends concretos vivem isolados em
   `ouroboros.adapters` (ver `tooling/import_linter_contracts.ini`,
   verificado no CI a cada push/PR — `.github/workflows/ci.yml`).
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
| 6 — Platformer (colisao de tiles) | `ouroboros.core.grid2d` + `games.platformer` | vertical slice jogavel |
| 7 — Turn-based Tactics (grid/pathfinding/turno) | `ouroboros.tactics` + `games.tactics` | vertical slice jogavel |
| 8 — Card Game (cartas/zonas/efeitos, sem ECS) | `ouroboros.cardgame` + `games.card_game` | vertical slice jogavel |

## Status

A Fase 1 do roadmap (M1-M6) esta concluida: apresentacao 2.0 (formas/alpha/
fx), texto e `SceneStack`, texturas e particulas, audio data-driven,
ergonomia do nucleo, e os dois vertical slices acima. A Fase 2 (M7-M11)
tambem esta concluida: CI real + este README (M7); release da engine + adocao
completa no BulletHell -- SceneStack, particulas, screen shake, audio banks,
fullscreen (M8, cross-repo); `UniformGrid`/`DungeonStreamingSystem` postos
pra funcionar de verdade + limpeza do placeholder vazio de um backend Godot
(M9); Roguelite ganhou profundidade real -- tipos de sala data-driven
(`data/room_types.json`), uma segunda arma exercitando modificadores
(`submachine_gun.json`), `spawn_rate_multiplier` de verdade influenciando a
contagem de inimigos por sala (M10); Jogo Musical ganhou um `MenuScene` real
de selecao de musica/dificuldade, uma segunda musica gerada pelo pipeline de
IA (`--profile hybrid`, com diversidade real de `"layer"`), e adotou
particulas/screen shake/textura real no feedback de acerto (M11). A Fase 3
(M12-M14) tambem esta concluida: colisao real contra tiles + gravidade
opt-in provadas por um Platformer (M12); grid/pathfinding/turno + promocao
do `ModifierStack` pro nucleo, provados por um Turn-based Tactics (M13);
cartas/zonas/efeitos reusando o `ModifierStack` ja promovido, sem ECS,
provados por um Card Game (M14). Nenhum item planejado restante -- detalhes
completos em `ROADMAP.md`.

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
