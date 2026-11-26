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
  (`MenuScene`, catalogo com 3 musicas), 4 lanes, julgamento de notas com
  SFX + particula no acerto + screen shake no erro, textura real de nota,
  pausa real. Ganhou tambem um **modo Osu!** (circulos/sliders em posicao
  arbitraria da tela, cursor+clique, gerados deterministicamente a partir
  dos onsets ja extraidos). Rodar com `python -m games.rhythm_game.main`.
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
- **Vitrine de estilos** (`games/vitrine_estilos/`) — a mesma cena (um espadachim sob a
  lua, ao lado de um torii, dando um corte) em ilustracao cel-shading, pixel art,
  tinta/sumi-e, flat com luz e low poly 3D, pintada ao abrir e mostrada com `draw_ui_image` (M18).
  Grade 3x2 para comparar; 1-5 abre um estilo, G volta, A/D troca. Rodar com
  `python -m games.vitrine_estilos.main`. Uma segunda cena (tecla C), **Biogenia**, mostra
  o fim do Cretaceo em corte lateral (o tiranossauro, o mamifero na toca, o ponto no ceu) em
  seis tons possiveis para o jogo: leve, silhueta, pixel art, naturalista, 2.5D e 3D com recortes
  (`games/vitrine_estilos/biogenia.py`; abrir direto com `... main biogenia`).
- **ASCII Knight** (`games/ascii_knight/`) — um cavaleiro em arte ASCII numa arena em visão 3/4,
  com pilares, árvores e inimigos ordenados pela fila de profundidade, sombra no chão e pulo.
  Setas/WASD andam, espaço ataca, J pula, F troca ASCII nativo / filtro ASCII / render normal,
  P troca a projeção (3/4, isométrica, de cima). Rodar com `python -m games.ascii_knight.main`.

## Projeções e modo ASCII

```python
from ouroboros.core.projecao import Projecao, FilaProfundidade, TRES_QUARTOS
from ouroboros.core.ascii import TelaAscii, SpriteAscii, AnimacaoAscii, FiltroAscii

proj = Projecao(TRES_QUARTOS, centro=(480, 320), tela=(960, 540), zoom=1.0)  # ou DE_CIMA, ISOMETRICA
sx, sy = proj.tela_de(x, y, z)        # mundo (chão x, y; altura z) -> pixel
x, y = proj.mundo_de(sx, sy)          # pixel -> ponto do chão (o cursor)
proj.tela_de_lote(xs, ys, zs, out_x, out_y)    # muitas entidades, sem alocar
sx, sy, rx, ry, forca = proj.sombra(x, y, z, raio)  # a elipse da sombra no chão

fila = FilaProfundidade(256)          # por quadro: limpar, adicionar, ordenar
fila.limpar()
fila.adicionar(ident, proj.profundidade(x, y), z, camada)
for ident in fila.ordenar(): ...      # de trás para a frente

tela = TelaAscii(120, 36)             # ASCII nativo
heroi = SpriteAscii("""
  ,~
 [o=]
 /|#|\\
""", cor_por_caractere={"#": (200, 50, 60)})
tela.limpar()
tela.sprite(heroi, col, linha, espelhado=olhando_esquerda)
renderer.draw_ascii(tela, 0, 0, tamanho=14)  # célula: renderer.ascii_cell_size(14)

renderer.set_ascii_filter(FiltroAscii(tamanho_fonte=12))  # qualquer jogo vira ASCII; None desliga
```

O filtro também liga pela configuração do jogo: `"ascii_filter": true` (ou um objeto com os
campos de `FiltroAscii`, ex.: `{"tamanho_fonte": 10, "area": [0, 0, 960, 500]}`) no JSON do
`EngineConfig`. Fica desligado por padrão e ainda não vale no backend `gl`.

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
| 9 — 3D (render GL, colisao, malhas) | `interfaces.renderer3d` + `adapters.gl_backend` + `core.colisao3d` + `interfaces.malhas3d` | usado por TerrorPS1 e Biogenia (render); colisao/malhas prontas, sem consumidor ainda |
| — Replay (entradas por quadro, arquivo, dessincronizacao) | `bootstrap.replay` | usado pelo BulletHell |

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
provados por um Card Game (M14). A Fase 4 (M15) tambem esta concluida: o
Jogo Musical ganhou um modo Osu! (circulos/sliders em posicao arbitraria,
julgamento por cursor+clique, capacidade nova de posicao de cursor no
Pilar 2, gerador deterministico de chart) integrado como um 3o modo
dentro do produto ja existente, sem tocar o modo lane original. Nenhum
item planejado restante -- detalhes completos em `ROADMAP.md`.

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
