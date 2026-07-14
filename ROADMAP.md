# OuroborosEngine — Roadmap pós-BulletHell

O port completo do BulletHell (16 bosses, 10 armas, 8 habilidades, 4 modos,
59 cenários de smoke headless — ver `BulletHell/bullethell/MIGRATION.md`)
foi o primeiro produto real rodando sobre a engine e funcionou como teste
de carga da arquitetura. **O núcleo ECS aguentou tudo sem uma única
mudança**: sparse-set + SoA, `PackedEntityId`, destruição diferida e
`World.step` provaram o desenho. O que faltou está inteiramente na camada
de **apresentação** (Pilar 2) e em ergonomia do núcleo. Este roadmap
ordena esse trabalho pelo que desbloqueia primeiro.

Regras que valem para TODOS os marcos (Constituição):
- `ouroboros.core`/produtos nunca importam pygame — toda feature nova
  entra por `ouroboros.interfaces` (ABC) + `ouroboros.adapters`
  (implementação), verificada pelo import-linter.
- Zero-GC no gameplay: qualquer API chamável de `ISystem.update()` opera
  sobre arrays/primitivos pré-alocados.
- Dados estáticos em `data/*.json` com ids `zlib.crc32`.

---

## M1 — Apresentação 2.0: formas, alpha e camada de efeitos  `[desbloqueia: telegraphs, holofote, lasers dignos]`

O `PygameRenderer` atual desenha só retângulos opacos. Evidências do port:
balas são quadrados; o laser é um retângulo esticado sem fase de telegraph
visual; o **holofote da Soberba é invisível** (o jogador não vê onde deve
ficar — defeito de jogabilidade real); o mutador FANTASMA precisou pintar
balas de preto porque `tint_a` é ignorado.

1. **Formas por `texture_id`**: enquanto não há texturas, o adapter
   interpreta `texture_id` como forma primitiva registrada
   (`shape/rect`, `shape/circle`, `shape/ring`, `shape/beam_h`,
   `shape/beam_v` — ids crc32 em `data/shapes.json`). Balas viram
   círculos; vigas viram feixes.
2. **Alpha**: respeitar `tint_a` no `draw_batch` (surface `SRCALPHA`
   reutilizada por frame ou `pygame.gfxdraw`). O FANTASMA troca o hack
   do tint-preto por alpha de verdade; telegraphs ficam translúcidos.
3. **Pool genérica `fx` no core** (`FX_DTYPE`: kind, x, y, w, h, tint,
   ttl): systems escrevem efeitos como DADOS (anel de choque da Ira,
   coluna do holofote, flash de telegraph); o `GameLoop` repassa a view
   num único `draw_effects(...)` novo do `IRenderer`. Null backend:
   no-op. Zero-GC: pool pré-alocada, mesma disciplina das demais.

Critério de aceite: no BulletHell, holofote visível varrendo, laser com
telegraph translúcido → feixe aceso, balas redondas, FANTASMA via alpha.

## M2 — Texto e cenas  `[desbloqueia: menus, HUD numérico, conquistas]`

Sem texto não há menu de seleção, contador de ondas nem tela de
conquistas — o BulletHell hoje seleciona tudo por CLI e mostra HUD de
retângulos.

1. **`IRenderer.draw_text(x, y, text, size_id, color, anchor)`**: texto é
   apresentação — permitido alocar no adapter (cache de superfícies por
   string; fontes pré-carregadas por `size_id`). PROIBIDO chamar de
   dentro de `ISystem.update()`: quem usa é a camada de cenas.
2. **SceneStack no bootstrap**: `GameLoop` ganha uma pilha de cenas
   (`MenuScene` desenha com renderer direto; `GameplayScene` embrulha o
   `World.step` atual). Transições substituem o loop fixo
   input→step→render sem tocar no core.
3. **HUD híbrido**: barras continuam data-driven (pool `hud`); números e
   rótulos entram pela cena por cima.

Critério de aceite: BulletHell com menu de seleção
(modo/boss/arma/skill/mutadores) navegável por teclado e HUD com números
de HP/vidas/onda — CLI vira atalho, não único caminho.

## M3 — Texturas e partículas  `[desbloqueia: identidade visual, juice]`

1. **Manifesto de assets** `data/textures.json` (`name` → arquivo);
   adapter carrega no `initialize` e resolve `texture_id` crc32 → surface
   (fallback: forma do M1). `EngineConfig` ganha `assets_path`.
2. **`ParticleStorage` no core** (SoA: x, y, vx, vy, ttl, size, tint) com
   kernel de update vetorizado + emissão em lote (`emit_burst`), e blend
   aditivo no adapter. O BulletHell tem os pontos de emissão prontos
   (hits, explosões de mina, morte de boss, graze).
3. **Screen shake/hitstop** como estado da cena (apresentação), não do
   core.

Critério de aceite: sprites para player/boss/balas, partículas em
hit/explosão, 60 FPS mantidos com 5000 balas + 1200 partículas.

## M4 — Áudio  `[desbloqueia: SFX do jogo e o pilar musical]`

1. **`IAudioEngine.play(bank_id)`** com banco pré-carregado de
   `data/audio.json` (crc32) e canal de música com loop — chamável de
   sistemas via fila de eventos de áudio (pool pré-alocada, mesma
   disciplina do `fx`).
2. Integrar com o `IAudioClock` existente — o RhythmSpawner (Pilar 4)
   passa a ter um caso de uso completo: padrões de bala sincronizados a
   beatmap dentro do BulletHell (crossover natural dos dois produtos).

## M5 — Ergonomia do núcleo (aprendizados do port)

Pequenos, mas cada um custou um bug ou boilerplate real:

1. **`ComponentPool.attach(index, clear=True)`**: linha densa reciclada
   contém lixo do swap-remove — o port teve um bug real por campo não
   escrito (`fragment`). Um zero-fill opcional na attach elimina a classe
   inteira de erro (custo O(itemsize), opt-in para spawns raros).
2. **`MemoryManager.pack_current(index)`**: obter o `PackedEntityId`
   atual de um índice vivo. Hoje cada pool de projétil do jogo carrega
   uma coluna `self` só para poder se destruir — com essa API a coluna
   some de ~8 dtypes.
3. **Harness de smoke headless genérico** em `tests/`: o padrão
   null-backends + driver programático + métricas (59 cenários no
   BulletHell) pegou toda regressão do port em segundos. Extrair o
   esqueleto para a engine como fixture oficial do Pilar 5.
4. **Contratos import-linter** para os novos módulos (fx, scenes, assets,
   audio) antes de escrever código — manter a Regra 2 verificável.

## M6 — Produtos (retomada dos pilares 3 e 4)

Com M1–M4 prontos, os produtos originais destravam com o vocabulário já
provado pelo BulletHell:
- **Roguelite**: dungeon streaming + `ModifierStack` sobre o mesmo modelo
  de pools/arquétipos; inimigos reutilizam o padrão minion/emitter.
- **Jogo Musical**: `RhythmSpawnerSystem` emitindo padrões (o formato
  `patterns.json` do BulletHell é reutilizável) sincronizados ao
  `IAudioClock`, nunca a delta-time.

---

## Ordem e dependências

```
M1 (formas/alpha/fx) ──► M2 (texto/cenas) ──► M3 (texturas/partículas)
        │                                            │
        └────────────► M4 (áudio) ◄─────────────────┘
M5 (ergonomia) — paralelo a qualquer um
M6 (produtos)  — após M1–M4
```

M1 e M5.1/M5.2 são os de maior retorno imediato: destravam defeitos
visíveis de jogabilidade no BulletHell (holofote invisível, telegraphs)
e eliminam a classe de bug mais traiçoeira encontrada no port.
