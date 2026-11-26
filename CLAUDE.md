# CLAUDE.md — OuroborosEngine

Guia para o Claude Code neste projeto. Idioma: PT-BR (docstrings e comentários sem acento,
como o resto do código; docs `.md` com acento).

## O que é
Engine ECS compartilhada, orientada a dados (SoA em NumPy) e **Zero-GC no gameplay**. Jogos
irmãos em `../` a consomem: BulletHell, Penumbra, ImpureBloodline, Hertz & Beats, Karmabound,
Ryoiki, TerrorPS1, Biogenia. Visão geral em [README.md](README.md); marcos e decisões em
[ROADMAP.md](ROADMAP.md); o que mudou para quem usa em [CHANGELOG.md](CHANGELOG.md).

## Rodar / verificar
```bash
pip install -e ".[dev]"            # [gl] para o 3D (moderngl)
pytest                             # ~2 min; testes de GL pulam sem OpenGL
ruff check .                       # regras fixadas em [tool.ruff] (E4/E7/E9/F)
lint-imports --config tooling/import_linter_contracts.ini
powershell -File tools/testar_jogos.ps1   # todos os jogos; antes de commitar mudança de comportamento
```
`lint-imports` não vem instalado nesta máquina: `pip install --target <pasta temporária>
import-linter` e rode com `PYTHONPATH` apontando para ela (sem mexer no Python global).

## Constituição (não quebrar)
1. `ouroboros.core`/`interfaces`/produtos nunca importam pygame nem moderngl — só
   `adapters` e o `composition_root`. Módulo novo em `bootstrap` entra na lista do contrato 2.
2. Zero-GC no que roda por quadro: buffers pré-alocados, resultado em objeto reaproveitável.
   Os testes de colisão e de replay conferem com `gc.callbacks` que o caminho quente não
   dispara o coletor — faça o mesmo para API nova de quadro.
3. Dados em `data/*.json`, ids por `zlib.crc32`.
4. API nova em interface: método **não abstrato** com default (no-op/`None`/
   `NotImplementedError`), para nenhum backend existente quebrar.

## Mapa rápido
- `core/` — World, pools, sistemas 2D, `grid2d`, **`colisao3d/`** (primitivas, `Relevo`,
  `MundoColisao3D` com grade em x/z e movimento que desliza), **`projecao`** (`Projecao` de
  cima/3/4/isométrica, `FilaProfundidade`) e **`ascii`** (`TelaAscii`, `SpriteAscii`,
  `FiltroAscii`).
- `interfaces/` — ABCs (renderer 2D, `renderer3d`, input, áudio), backends nulos e
  **`malhas3d`** (construtores de malha para `IRenderer3D.criar_malha`).
- `adapters/` — pygame (com `ascii_pygame`: glifos em cache e o filtro ASCII) e `gl_backend`
  (ModernGL, OpenGL 3.3).
- `bootstrap/` — composição, game loop, cenas, save atômico, **`replay`**.
- `games/` — vertical slices, a vitrine de estilos (o 3D de CPU em `tres_d.py` ainda tem
  os construtores antigos) e o `ascii_knight` (demo de projeções e do modo ASCII).

## Convenções da API 3D
y para cima; triângulos soltos (sem índice), virados para fora (anti-horário visto de fora).
Nomes em português no 3D (`criar_malha`, `mover_capsula`), como o `renderer3d`; o resto da
engine é em inglês. O `terreno` e o `Relevo` dividem a célula pela mesma diagonal — não mude
uma sem a outra.

## Versão e release
`pyproject.toml` e `ouroboros/__init__.py` em **0.5.0**. Não suba a versão por conta própria:
o que entrar sem release vai em "Ainda sem versão" no CHANGELOG. O BulletHell usa um wheel
versionado em `BulletHell/wheels/` (CI sem o repo irmão): mudança que ele usa exige rebuild do
wheel (`BulletHell/tools/build_engine_wheel.ps1`) depois do commit da engine.

## Regras de trabalho
- Mudança de comportamento compartilhado começa aqui, não no jogo; depois `testar_jogos.ps1`.
- Só commitar/push quando o Enzo pedir.
