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

## Fase 2 — consolidação, infraestrutura e profundidade (M7–M11): concluída

Auditoria do estado real do código (5 agentes de exploração, um por
produto/camada) mostrou que a Fase 1 deixou capacidade construída-mas-nunca-
usada (`UniformGrid`, `DungeonStreamingSystem`, um placeholder de backend
Godot vazio), zero CI, um README desatualizado, e um produto irmão
(BulletHell) preso a um wheel da engine anterior a toda a Fase 1. Esta fase
atacou essa dívida antes de aprofundar os dois produtos que moram neste repo.

Cada marco seguiu o mesmo ciclo já usado em M1–M6: pesquisa → design → crítica
→ implementação → testes → `lint-imports` → smoke → reportar. Todos os 5
marcos (M7–M11) foram implementados, testados (373 testes, `lint-imports`
verde) e pushados — ver histórico de commits e as seções abaixo pra detalhes
de cada um.

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

### M9 — Consumir primitivos construídos e nunca usados `[dívida técnica]` — concluído

1. **`UniformGrid` real**: `CompositionRoot.build()` ganhou um parâmetro
   opcional `spatial_grid` (repassado pro `CollisionSystem` que já constrói —
   `None` preserva o comportamento força-bruta de sempre pros outros
   produtos). Roguelite gera a masmorra ANTES de chamar
   `CompositionRoot.build()` (achado da crítica: `DungeonGenerator`/
   `StrictRandom` não têm nenhuma dependência de `World`, então isso é
   seguro), monta uma grade dimensionada pelos limites REAIS dos tiles
   (salas + corredores — achado da crítica: usar só o retângulo de cada
   sala deixaria corredores, que podem se estender bem além dele, fora dos
   limites) e passa pra `.build(spatial_grid=...)`.
2. **`DungeonStreamingSystem` real**: ganhou `on_room_activated`/
   `on_room_deactivated` opcionais, chamados logo após `create_entity`/antes
   de `destroy_entity`, recebendo a linha de `DungeonLayout.rooms` e o
   `PackedEntityId` — a peça que faltava pra escrever os campos iniciais de
   cada entidade materializada (mesmo gap do `ArchetypeLoader` ignorar
   `initial_values`, já documentado no M6). Roguelite trocou os sprites
   estáticos do M6 por streaming de verdade. Achado real da crítica:
   `ROOM_DTYPE.center_x/center_y` são gerados em unidades de TILE, mas o
   sistema compara direto contra a posição (em pixels) da âncora — sem
   converter, a distância ficaria errada por um fator de `TILE_PIXELS`;
   corrigido escalando uma cópia de `layout.rooms` só pra esse uso.
3. **`godot_backend`**: removido o placeholder vazio e as entradas
   correspondentes no import-linter (contratos 1 e 2 — `forbidden_modules`
   só lista `pygame` agora).

Verificado: suite completa (319 testes) + `lint-imports` (3 kept, 0 broken) +
verificação manual do jogo real (salas ativando/desativando conforme o
jogador se move, colisão continuando a funcionar via a grade nova).

### M10 — Roguelite: profundidade real — concluído

1. **Tabela JSON de tipos de sala** (`data/room_types.json`, novo
   `RoomTypeLoader`): variedade visual real por `room_type` (campo que já
   existia em `ROOM_DTYPE` desde a geração original da masmorra, mas nunca
   tinha sido lido por ninguém — confirmado pela seed fixa do jogo: gera
   `[0, 2, 0, 1, 1, 3]`, as 4 variações realmente aparecem numa run). Achado
   real da crítica: nada garantia que a tabela JSON tivesse entradas
   suficientes pro intervalo `[0, 4)` que o gerador produz — corrigido com
   uma constante `ROOM_TYPE_COUNT` (nova, em `dungeon_generator.py`, usada
   tanto na geração quanto na validação do loader) e uma checagem de limites
   explícita em `_make_on_room_activated`, pra nunca deixar um `IndexError`
   de numpy escapar de dentro do callback de ativação de sala.
2. **`data/weapons/submachine_gun.json`** (segunda arma real, não equipada
   como inicial — falta UI de seleção): primeiro exercício de verdade do
   caminho `"modifiers"` não-vazio de `WeaponLoader.materialize` contra o
   catálogo real (os testes anteriores só cobriam esse caminho com um
   fixture em `tmp_path`). Novo teste de integração confere os valores
   finais calculados à mão: `damage = 6.0 + flat(-1.0) = 5.0`,
   `cooldown = (1/6) * percent_mult(0.85) ≈ 0.14167` — resolve o
   `weapon_def_id` por `stable_id_from_name` diretamente, não
   `next(iter(definitions))` (a crítica notou que esse idioma, usado nos
   testes mais antigos, depende da ordem alfabética de
   `sorted(glob("*.json"))` e ficaria frágil contra uma 3ª arma futura cujo
   nome ordene antes de "starter_pistol").
3. **`spawn_rate_multiplier` consumido** na hora de decidir quantos
   inimigos nascem por sala (antes, sempre exatamente 1, o multiplicador
   era lido de `DifficultyLoader` e nunca usado). `math.floor(x + 0.5)` em
   vez de `round()` — achado da crítica: o arredondamento bancário do
   Python (`round(2.5) == 2`, não 3) seria uma superfície não-monotônica
   pra quem tunar uma dificuldade nova; não muda nada hoje (`normal.json`
   tem `multiplier=1.0`, único arquivo de dificuldade existente). Sem teto
   explícito em `enemies_per_room`: `MemoryManager.create_entity` já
   levanta um `IndexError` claro se `entity_capacity` estourar, e nenhuma
   dificuldade real hoje se aproxima disso.

Verificado: suite completa (328 testes, incluindo um novo
`test_room_type_loader.py` e 3 testes novos de integração em
`test_roguelite_composition_headless.py`/`test_weapon_loader.py`) +
`lint-imports` (3 kept, 0 broken) + execução manual headless confirmando
inimigos-por-sala e tint por `room_type` batendo com o layout determinístico
esperado.

Fora de escopo (deferido): sistema de loot/pickups e, com ele,
`RandomStreamPurpose.LOOT_TABLE`/`loot_rarity_bias` — fica pra quando loot for
um marco próprio.

### M11 — Jogo Musical: profundidade real — concluído

1. **`MenuScene` real via `SceneStack`** (`games/rhythm_game/menu_scene.py`):
   lista o produto cartesiano `(música, dificuldade)` dos catálogos reais
   (`SongCatalogLoader`/`RhythmDifficultyLoader`, novos em
   `ouroboros/rhythm/loaders/`, mesmo desenho de
   `ouroboros/roguelite/loaders/`), navegável por `move_up`/`move_down`/
   `confirm` (3 bindings novos). Motivou uma extração pequena na engine
   (`CompositionRoot.build_world()`, Pilar 1 sem backends — `build()` só
   passou a chamá-lo): o Jogo Musical virou o segundo produto (depois do
   BulletHell, M8c) a precisar de "um `World` novo por partida" via
   `GameLoop.replace_world`. `QuitOnActionSystem` trocou `game_loop` por um
   callback `on_quit_action` — 'quit' durante uma partida agora volta pro
   menu (para a música, limpa HUD/câmera residual) em vez de encerrar o
   processo; só o `MenuScene` em si chama `game_loop.stop()`. `build_game()`
   virou um atalho de conveniência (mesmo espírito do `--play` do
   BulletHell): monta o menu e confirma a linha 0 direto, sem simular
   tecla — por isso a suite de testes inteira que já existia (só usava
   `build_game`) continuou passando sem nenhuma mudança. Achado real da
   crítica: `PauseScene` precisa da MESMA instância de `GameplayScene` que
   `reset_scenes` usa, nunca `game_loop.current_scene` (que na hora de
   montar uma partida é o `MenuScene` ou a cena da partida anterior).
2. **Segunda música real** (`second_track`, `games/rhythm_game/tools/
   generate_second_track.py`): sintetiza um WAV com kick grave + um "blip"
   tonal agudo no contratempo e roda o CLI offline real com
   `--profile hybrid` — resultado real inspecionado: 120 ameaças, 58
   "kick" + 62 "vocal" (diversidade de camada de verdade, ao contrário de
   `demo_track`, extração legada com `layer=""` em toda nota). Serve tanto
   de segunda música jogável quanto de dado real pro item 4.
   `data/beatmaps/example_track.beatmap.json` (órfão, schema pré-v1
   quebrado, áudio referenciado que nunca existiu) removido — superado por
   `second_track`, não "consertado" (o ROADMAP oferecia as duas opções).
3. **M3 adotado no feedback de acerto** — primeira vez que ParticleStorage/
   ScreenShake/textura real são usados neste repo (nem o Roguelite tinha
   adotado): textura real de nota (`generate_note_texture.py` — disco
   branco com falloff de alpha, RGB quase-branco de propósito pro tint
   por-nota continuar exato via `BLEND_RGBA_MULT`) substitui `SHAPE_CIRCLE`;
   `ParticleStorage`/`ScreenShake` são construídos POR PARTIDA (congelam
   com o resto do `World` durante a pausa); motivou um `ScreenShakeUpdateSystem`
   novo na engine (mesmo idioma de `ParticleUpdateSystem`, que já existia).
   Achado real da crítica: `load_texture_manifest` não tinha guarda contra
   um `texture_id` colidir com o intervalo reservado às formas primitivas
   (`SHAPE_RECT`/`CIRCLE`/`RING`) — corrigido antes de qualquer produto ter
   carregado uma textura de verdade pela primeira vez.
4. **`"layer"` influencia algo visível**: `NOTE_STATE_DTYPE` ganhou o campo
   `layer` (copiado do agendamento no spawn); `JudgmentSystem` ganhou
   `on_judgment` (opcional), disparado com `(judgment, layer, lane_index)`.
   "vocal" desenha como `SHAPE_RING` em vez da textura real, e cada camada
   tem sua própria cor de partícula ao acertar — provado tanto por teste
   de unidade quanto contra o `second_track` real. Achado real da crítica:
   o callback original só carregava `judgment`, sem posição pra nascer o
   burst — corrigido acrescentando `lane_index` (sempre disponível em
   `_judge_presses`, nunca em `_auto_miss_expired`, que é só-Erro).

Verificado: suite completa (373 testes, incluindo `test_menu_scene.py`,
`test_rhythm_juice_wiring.py`, `test_song_catalog_loader.py`,
`test_rhythm_difficulty_loader.py` novos) + `lint-imports` (3 kept, 0
broken) + verificação manual headless de ponta a ponta (menu → escolher
`second_track` → notas com textura/forma corretas por camada → burst de
partícula/screen shake reais ao julgar → ESC volta pro menu → música
anterior parada).

## Ordem e dependências

```
M7 (CI+README, rápido)
  │
M8a/M8b/M8c (release da engine + adoção completa no BulletHell -- concluído)
  │
M9 (UniformGrid + DungeonStreamingSystem real + limpeza do godot_backend -- concluído)
  │
  ├──► M10 (Roguelite: salas/arma/dificuldade -- concluído)
  └──► M11 (Jogo Musical: menu/beatmap/juice -- concluído)
```

M7 primeiro por ser rápido. M8 em seguida por ser o item de maior
alavancagem (nada da Fase 1 chega no BulletHell sem ele) mas também o de
maior escopo/risco (dois repositórios) — os 3 sub-marcos (release, trocas
cirúrgicas, SceneStack) todos concluídos. M9 antes de M10 porque a
renderização de salas do M10.1 dependia de onde o streaming real (M9.2)
deixasse o código. M11 não dependia de nada além do que já existia —
último item da fase, agora também concluído.

## Fora de escopo desta fase inteira

- Sistema de loot/progressão entre andares.
- Texturas/sprites reais no BulletHell.
- Reorganizar o roster de bosses do Decálogo do BulletHell pros modos normais.
- Um segundo backend de renderização de verdade — o item do M9 é só limpeza
  do placeholder vazio, não um novo backend.
