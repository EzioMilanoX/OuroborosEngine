# OuroborosEngine — Roadmap

O port completo do BulletHell (16 bosses, 10 armas, 8 habilidades, 4 modos,
hoje já com 20+ bosses via o arco "Decálogo" — projeto irmão em
`../BulletHell`, não versionado neste repositório) foi o primeiro produto real
rodando sobre a engine e funcionou como teste de carga da arquitetura. **O
núcleo ECS aguentou tudo sem uma única mudança**: sparse-set + SoA,
`PackedEntityId`, destruição diferida e `World.step` provaram o desenho.

Regras que valem para TODOS os marcos (Constituição):
- `ouroboros.core`/produtos nunca importam pygame — toda feature nova
  entra por `ouroboros.interfaces` (ABC) + `ouroboros.adapters`
  (implementação), verificada pelo import-linter.
- Zero-GC no gameplay: qualquer API chamável de `ISystem.update()` opera
  sobre arrays/primitivos pré-alocados.
- Dados estáticos em `data/*.json` com ids `zlib.crc32`.

---

## Fase 1 — pós-BulletHell (M1–M6): concluída

Fechou a lacuna que sobrou inteiramente na camada de **apresentação** (Pilar 2)
e na ergonomia do núcleo, e depois retomou os pilares 3/4 como produtos
jogáveis de verdade:

- **M1** — formas por `texture_id` (`shape/rect`, `shape/circle`, `shape/ring`,
  `shape/beam_h/v`), alpha real (`tint_a`), pool `fx` genérica + `draw_effects`.
- **M2** — `IRenderer.draw_text`, `SceneStack` (`IScene`/`GameplayScene`) no
  `GameLoop`, HUD híbrido.
- **M3** — manifesto de texturas (`load_texture`), `ParticleStorage` +
  `draw_particles` (blend aditivo), screen shake como estado de cena.
- **M4** — `IAudioEngine.load_sound`/bancos de áudio data-driven
  (`audio_bank_loader`), `pause_track`/`resume_track`.
- **M5** — `ComponentPool.attach(clear=True)`, `MemoryManager.pack_current`/
  `World.pack_current`, fixture oficial de smoke headless
  (`bind_quit_after`, Pilar 5), contratos import-linter atualizados a cada
  módulo novo, `World.systems`.
- **M6** — vertical slices jogáveis: **Jogo Musical** (4 lanes, alinhado com o
  projeto irmão "Hertz & Beats", pausa real) e **Roguelite** (movimento,
  perseguição, arma inicial, dano por colisão, câmera seguindo o jogador,
  morte/vitória).

Todos os 6 marcos foram implementados, testados (301 testes, `lint-imports`
verde) e pushados — ver histórico de commits pra detalhes de cada um.

---

## Fase 2 — consolidação, infraestrutura e profundidade (M7–M11)

Auditoria do estado real do código (5 agentes de exploração, um por
produto/camada) mostrou que a Fase 1 deixou capacidade construída-mas-nunca-
usada (`UniformGrid`, `DungeonStreamingSystem`, um placeholder de backend
Godot vazio), zero CI, um README desatualizado, e um produto irmão
(BulletHell) preso a um wheel da engine anterior a toda a Fase 1. Esta fase
ataca essa dívida antes de aprofundar os dois produtos que moram neste repo.

Cada marco segue o mesmo ciclo já usado em M1–M6: pesquisa → design → crítica
→ implementação → testes → `lint-imports` → smoke → reportar.

### M7 — Infraestrutura de verificação `[rápido, desbloqueia confiança]`

1. `.github/workflows/ci.yml`: roda `pytest tests/ -q` +
   `lint-imports --config tooling/import_linter_contracts.ini` em push/PR
   pra `main`.
2. Reescrever `README.md` pra refletir o estado real (Fase 1 completa, 3
   produtos jogáveis, BulletHell como repo irmão) e corrigir a alegação falsa
   de que o import-linter já roda em CI.

### M8 — Release do engine + adoção no BulletHell (cross-repo) `[maior escopo, dois repos]`

**M8a** (neste repo, concluído): bump de versão (`0.2.0`), build de um wheel
novo, e `IRenderer.set_fullscreen(enabled: bool)` — gap real da engine,
achado pelo próprio BulletHell (mais uma correção real encontrada no
processo: `pyproject.toml` combinava `license` SPDX com um classifier
antigo, o que quebraria qualquer `pip install` fresco, incluindo o CI do M7).

**M8b** (repo `BulletHell`, concluído): `wheels/ENGINE_COMMIT.txt` apontado pro
release `0.2.1`; `spawn_particles`/`ParticleSystem` (uma entidade ECS por
partícula) viraram uma fila de pedidos de burst (`particle_request`, mesmo
idioma de `clock.shake`/`clock.sfx`) drenada numa `ParticleStorage`
compartilhada — hash determinístico de ângulo/velocidade preservado
bit-a-bit (verificado); `_apply_shake` passou a usar
`ScreenShake.trigger()`/`current_magnitude()` pro decaimento/teto aditivo
(26/s, 18.0), mas o offset dx/dy em si continua vindo da mesma fórmula de
hash de `run_t` de sempre — **não** do retorno de `ScreenShake.update()`
(achado da crítica: `update()` decai *antes* de calcular a magnitude, ordem
oposta à leitura-antes-de-decair que o BulletHell já fazia); os 7
`register_tone` inline viraram um banco `bullethell/data/sfx.json` via
`load_audio_bank`; `set_fullscreen` ligado num 3º toggle em SISTEMA (achado
e corrigido de quebra: o toggle antigo tinha um bug real que faria um save
sem a chave nova começar default-LIGADO). Motivou 2 adições pequenas na
engine (`ScreenShake.current_magnitude()`, `ParticleStorage.ttl0_seconds`
— release `0.2.1`). Verificado: 6/6 smoke scripts (222 checks) + 174 testes
pytest do BulletHell, mais checagens funcionais diretas.

**M8c** (repo `BulletHell`, concluído): trocado o menu hand-rolled (`GameApp`/
`scenes.py`, ~1200 linhas, seu próprio loop principal com 15 estados via
if/elif) pela `SceneStack` de verdade. Motivou 3 adições na engine
(`GameLoop.replace_world`/`reset_scenes`/`tick_once` — release `0.2.2`):
nenhum produto existente precisava de "sem `World` até terminar um menu,
reconstruir `World` a cada partida" (Jogo Musical/Roguelite constroem um
`World` só, pra vida inteira do processo). `GameApp` virou objeto de
SESSÃO (não mais dono do loop); 8 `IScene`s novas substituem o dispatch de
15 estados (`WizardScene` cobre os 7 passos do assistente como uma única
cena com passo interno, não 7 cenas). Dois bugs reais achados e corrigidos
durante a implementação: "SAIR" ficaria mudo (dependia de `self._running`/
`GameApp.run()`, ambos removidos — corrigido chamando `game_loop.stop()`
direto) e "voltar ao menu" via `pop_scene()` exporia a `GameplayScene`
genérica da engine (base não-removível da pilha) rodando por baixo sem
menu/HUD — corrigido usando o novo `reset_scenes()` para essas transições
de "modo" inteiro, não `pop_scene()`. Verificado: 6/6 smoke scripts (242
checks, 3 deles ajustados pra construir o `GameLoop` que passaram a
precisar) + 174 testes pytest + o entry point real (`main_ecs.py`, com e
sem `--play`) rodando de ponta a ponta.

Fora de escopo do M8b/M8c: texturas reais no BulletHell (falta arte, não só
código) e reorganizar o roster de bosses do Decálogo pros modos normais.

### M9 — Consumir primitivos construídos e nunca usados `[dívida técnica]`

1. **`UniformGrid` real**: Roguelite passa a construir sua `CollisionSystem`
   com uma grade dimensionada pelos limites da masmorra, em vez de
   `spatial_grid=None`.
2. **`DungeonStreamingSystem` real**: estender o sistema (pillar-level, em
   `ouroboros/roguelite/systems/dungeon_streaming_system.py`) com um hook
   tipo `on_room_activated(room, packed_entity_ids)` — a peça que faltava
   pra escrever os campos iniciais de cada entidade materializada (mesmo gap
   que `ArchetypeLoader` ignorar `initial_values` já documentado no M6) — e
   trocar os sprites estáticos do M6 por streaming de verdade.
3. **`godot_backend`**: remover o placeholder vazio e as entradas
   correspondentes no import-linter — boilerplate morto sem plano concreto de
   um segundo backend.

### M10 — Roguelite: profundidade real `[depende do M9.2 pra renderização de salas]`

1. Tabela JSON de tipos de sala consumida na renderização — variedade visual
   real por `room_type` (campo que já existe em `ROOM_DTYPE` desde a geração
   original da masmorra, mas nunca foi lido por ninguém).
2. Uma segunda arma real com `"modifiers"` não-vazio — primeiro exercício de
   verdade do caminho já pronto em `WeaponLoader.materialize`.
3. Consumir `spawn_rate_multiplier` de `DifficultyLoader` na hora de decidir
   quantos inimigos spawnar por sala.

Fora de escopo (deferido): sistema de loot/pickups e, com ele,
`RandomStreamPurpose.LOOT_TABLE`/`loot_rarity_bias` — fica pra quando loot for
um marco próprio.

### M11 — Jogo Musical: profundidade real

1. `MenuScene` de seleção de música/dificuldade via `SceneStack`.
2. Um segundo beatmap real e válido (consertar `example_track.beatmap.json`
   pro schema v1 + áudio de verdade, ou gerar um novo via o pipeline de
   extração por IA).
3. Adotar M3 no feedback de acerto: textura real em vez de `SHAPE_CIRCLE`,
   partícula na batida acertada, screen shake no miss.
4. Fazer a tag `"layer"` (perfil `hybrid`) influenciar algo visível (cor/
   textura distinta por camada, ou SFX distinto).

## Ordem e dependências

```
M7 (CI+README, rápido)
  │
M8a/M8b/M8c (release da engine + adoção completa no BulletHell -- concluído)
  │
M9 (UniformGrid + DungeonStreamingSystem real + limpeza do godot_backend)
  │
  ├──► M10 (Roguelite: salas/arma/dificuldade)
  └──► M11 (Jogo Musical: menu/beatmap/juice) -- pode rodar em paralelo ao M10
```

M7 primeiro por ser rápido. M8 em seguida por ser o item de maior
alavancagem (nada da Fase 1 chega no BulletHell sem ele) mas também o de
maior escopo/risco (dois repositórios) — os 3 sub-marcos (release, trocas
cirúrgicas, SceneStack) todos concluídos. M9 antes de M10 porque a
renderização de salas do M10.1 depende de onde o streaming real (M9.2)
deixar o código. M11 não depende de nada além do que já existe hoje.

## Fora de escopo desta fase inteira

- Sistema de loot/progressão entre andares.
- Texturas/sprites reais no BulletHell.
- Reorganizar o roster de bosses do Decálogo do BulletHell pros modos normais.
- Um segundo backend de renderização de verdade — o item do M9 é só limpeza
  do placeholder vazio, não um novo backend.
