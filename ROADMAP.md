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

---

## Fase 3 — preparar a engine para novos gêneros (M12–M14)

A engine hoje prova 3 gêneros (Roguelite, Jogo Musical, BulletHell-como-
shmup). Auditoria contra o código real (3 agentes de design, um por gênero)
confirmou que faltam capacidades genéricas de verdade pros próximos 3 gêneros
mais próximos: nenhuma colisão contra geometria estática (tiles), nenhum
pathfinding, nenhum scheduler de turno, nenhum sistema de save/load em lugar
nenhum do repo. Cada marco segue o mesmo ciclo de sempre (pesquisa → design →
crítica → implementação → testes → `lint-imports` → smoke → reportar) e ganha
um jogo de demonstração mínimo pra provar o primitivo contra um produto real
— mesmo padrão que achou bugs reais em toda milestone anterior.

### M12 — Platformer: colisão contra tiles `[mais autocontido]` — concluído

1. **`Grid2D`** (`ouroboros/core/grid2d.py`): container puro de dados (array
   denso tipado `[row,col]` + conversão world↔cell, `is_solid` como única
   convenção v1 — qualquer valor `!= 0`), sem semântica de pathfinding
   embutida. Deliberadamente decoupled de `ouroboros.roguelite.generation`
   (`TILE_DTYPE`/`TileType`) — agnóstico de gênero.
2. **`GravitySystem`/`TileCollisionSystem`** (novos, `ouroboros/core/
   systems/`): gravidade trivial (soma numa pool inteira, sem intersecção)
   + resolução AABB-vs-grade-sólida por eixo (X depois Y, evita pegar
   quina na diagonal — usa `prev_y` reconstruído pra resolver X), expondo
   `is_grounded(entity_index)` via scratch pré-alocado (mesmo idioma de
   `JudgmentSystem._processed_scratch`). **Ordem de registro obrigatória**:
   `PhysicsSystem` → `TileCollisionSystem` → `GravitySystem` — é também o
   que faz `grounded` se auto-sustentar a cada frame em repouso (gravidade
   reintroduz uma velocidade Y residual mínima antes do frame terminar, o
   próximo frame a resolve de novo). `CompositionRoot.build()`/
   `build_world()` ganharam `tile_grid`/`gravity_y` opcionais (mesmo
   espírito de `spatial_grid` — `None` preserva 100% o comportamento de
   sempre) — nenhum script de composição de produto precisa de acesso
   direto a `MemoryManager` bruto, só `world.get_pool(...)`.
3. **`games/platformer/`**: nível ASCII hardcoded (`level.py`, valida que o
   ponto de spawn não cai numa célula sólida — falha na composição, nunca
   silenciosamente em runtime), jogador com corrida+pulo (`PlayerRunSystem`/
   `PlayerJumpSystem`, este último só permite pular com `is_grounded()`),
   sem inimigos/pontuação.

Achados reais da crítica (incorporados antes de implementar): validação
explícita de que `hitbox.half_width/half_height <= cell_size/2` (o algoritmo
v1 só amostra a borda de avanço, uma hitbox maior violaria isso
silenciosamente); `intersect_entity_indices` já é variádico (não precisou
compor duas chamadas); e o achado mais importante — `GameLoop.run()` nunca
limitava `delta_time`, o que **antes do M12 só degradava detecção por um
frame, mas a partir da primeira colisão real contra geometria estática vira
"atravessar o chão pra sempre"** num pico de tempo real (janela arrastada,
pausa de GC) — corrigido com `MAX_DELTA_TIME_SECONDS = 0.1` em
`ouroboros/bootstrap/game_loop.py`. Achado real dos MEUS PRÓPRIOS testes
(não da crítica): o viés de epsilon na borda de avanço estava na direção
errada — subtraía epsilon em vez de somar, apagando exatamente o afundamento
marginal que o cenário de repouso contínuo precisa detectar a cada frame.

Verificado: suite completa (403 testes, incluindo `test_grid2d.py`,
`test_gravity_system.py`, `test_tile_collision_system.py`,
`test_game_loop_delta_time_clamp.py`, `test_platformer_composition_headless.py`
novos) + `lint-imports` (3 kept, 0 broken) + verificação manual headless
(queda livre, corrida esquerda/direita, pulo só no chão, assentamento sobre
o chão a partir do spawn).

Fora de escopo (deferido): rampas, plataformas móveis, drop-through de
plataforma de mão única, hitbox maior que uma célula, formato de nível
data-driven (1 nível hardcoded não justifica um pipeline ainda).

### M13 — Turn-based Tactics: grid + pathfinding + turno `[promove ModifierStack]` — concluído

1. **`ouroboros.tactics`** (pacote novo, irmão de `roguelite`/`rhythm` —
   `import_linter_contracts.ini` atualizado nos dois contratos relevantes
   NESTE marco, não adiado pro M14 como o stub original sugeria): 
   `BattlefieldGrid` (terreno estático + ocupação RECONSTRUÍDA por inteiro a
   cada chamada — nunca um patch incremental, mesmo idioma de
   `UniformGrid.rebuild`; deliberadamente NÃO reusa `Grid2D` do M12 — uma é
   contínua/testada todo frame, a outra é consultada por evento discreto,
   as semânticas divergem demais pra convergir sem indireção artificial),
   `pathfinding.py` (`find_path` A* ortogonal, `reachable_cells`
   Dijkstra-com-orçamento, `has_line_of_sight` Bresenham com regra
   explícita de canto — tudo fora do hot-path, scratch Python/heapq
   aceitável), `turn_queue.py` (`TurnQueue`, bookkeeping puro de
   iniciativa, sem conceito de fase/UI).
2. **`TacticsBattleScene`** (`games/tactics/battle_scene.py`): cena única
   com fase implícita (de quem é `TurnQueue.current_entity_index` agora),
   mesmo idioma de `WizardScene`/`MenuScene` — lê input direto, nunca
   depende de `ISystem` (nunca chama `world.step()`, já que não há nada
   pra simular por frame). Guarda uma `GameplayScene` só pra delegar
   `render()` a ela (mesmo idioma de `PauseScene`).
3. **Promoveu `ModifierStack`**: `ouroboros/roguelite/modifiers/*` →
   `ouroboros/core/modifiers/*` (mesmo código, Tactics é o 2º consumidor
   real) + `ModifierApplicationSystem` (já 100% genérico) também
   promovido — atualizados os ~6 chamadores reais no Roguelite + 3 testes
   (2 deles movidos pra `tests/core/`).
4. **`games/tactics/`**: batalha 10x8 hardcoded (muro com brecha + 2
   células `DIFFICULT`), Warrior+Scout (jogador) vs. 2 Grunts (inimigo),
   atributos ataque/defesa/alcance num ÚNICO `ModifierStack` compartilhado
   (mesmo idioma do sistema de arma do Roguelite), iniciativa
   ENTRELAÇADA entre times (prova que o sort de `TurnQueue` importa de
   verdade). IA trivial: mira uma célula ADJACENTE ao inimigo mais
   próximo (nunca a célula dele — corretamente ocupada/inalcançável),
   anda até o orçamento acabar, ataca se ficar adjacente.

Achado real e crítico da crítica: `World.destroy_entity()` é DIFERIDO (só
`World.flush()` desanexa de verdade) — como `TacticsBattleScene` nunca
chama `world.step()`, uma unidade morta ficaria como ocupante fantasma da
própria célula PRA SEMPRE sem um `world.flush()` explícito logo após
`destroy_entity()`, antes de reconstruir a ocupação. 2 bugs reais achados
pelos MEUS PRÓPRIOS testes (a crítica não pegou): `BattlefieldGrid.__init__`
deixava `move_cost` em `0.0` (default de `np.zeros`) em vez de `1.0`,
quebrando a admissibilidade da heurística de Manhattan silenciosamente;
`TurnQueue.build` ordenava ascendente-estável e invertia o resultado pra
simular descendente — inverter um sort estável inverte o desempate
TAMBÉM (o oposto do desejado).

Verificado: 40 testes novos de engine (`tests/tactics/`) + 8 de composição
(`tests/games/test_tactics_composition_headless.py`, incluindo uma batalha
completa jogada do início ao fim sem crashar) + suite completa (451
testes) + `lint-imports` (3 kept, 0 broken) + sessão manual headless
confirmando movimento/bloqueio por parede/ocupação/ataque/morte/vitória de
ponta a ponta.

Fora de escopo (deferido): fog of war, turno em rede, altura de terreno,
movimento diagonal, passar por aliado no pathing, RNG determinístico
estilo `StrictRandom`, loader data-driven de mapa de batalha.

### M14 — Card Game: cartas + zonas + efeitos `[reusa ModifierStack, sem ECS]` — concluído

Volume de cartas em jogo (dezenas, mutado por evento de turno, não por
frame) é o oposto do que `ComponentPool`/`World.step()` otimizam —
deliberadamente sem ECS/Zero-GC pro estado de carta/zona/efeito: nenhuma
entidade existe neste produto (nem `transform`/`sprite`), e `MatchScene`
nunca chama `world.step()` (mesmo idioma de `MenuScene` — o `World`
associado ao `GameLoop` é um placeholder genérico nunca consultado).

1. **`ouroboros.cardgame`** (pacote novo, irmão de `roguelite`/`rhythm`/
   `tactics`): `CardLoader` (mesmo desenho de validação/`stable_id_from_name`/
   erro customizado de `WeaponLoader`, lendo `data/cards/*.json` — 7 cartas:
   5 `ACTION` + 2 `CREATURE`); `Zone`/`CardInstance` (listas Python puras —
   deck/mão/descarte/campo por jogador, `random.Random` injetável pro
   shuffle, não `StrictRandom`); vocabulário fechado de 5 `EffectOp`
   (`DAMAGE_TARGET`/`HEAL_TARGET`/`DRAW_CARDS`/`BUFF_STAT`/`GAIN_RESOURCE`,
   alvo de cada um FIXO/implícito — sem seleção de alvo pelo jogador),
   resolvidos por `apply_effect` (dispatcher plano). `BUFF_STAT` é o
   primeiro consumidor real a de fato empurrar (`push()`) um modificador no
   `ModifierStack` promovido no M13 (Tactics só o registrava, nunca
   empurrava) — `source_id` sempre `CardInstance.instance_id` (nunca
   `card_def_id`, o template compartilhado por cópias da mesma carta).
2. **Criaturas no v1 têm APENAS `base_attack`** (sem HP/defesa própria):
   nada as danifica depois de jogadas (sem combate criatura-vs-criatura/
   bloqueio, ver "fora de escopo"), então são fontes permanentes de ataque
   que disparam a cada fase de combate — um campo de HP/defesa seria nunca
   lido.
3. **`MatchScene(IScene)`** (`games/card_game/match_scene.py`): ciclo
   contínuo `DRAW→MAIN→COMBAT→END→DRAW...` de um ÚNICO lado real (não há
   "turno do oponente" — o oponente é estático/sem IA, nunca joga carta
   nenhuma). Ação de entrada de fase e transição pra próxima são atômicas
   dentro da MESMA chamada de `update()` que primeiro observa a fase
   (nunca há um frame onde uma fase foi "entrada" mas ainda não
   processada — evita reexecutar `_run_draw_phase`/`_run_combat_phase`
   duas vezes por ciclo de turno).
4. **`import_linter_contracts.ini`**: `ouroboros.cardgame` adicionado ao
   contrato 1 (`source_modules`) e à camada de produtos do contrato 3
   (`ouroboros.roguelite | ouroboros.rhythm | ouroboros.tactics |
   ouroboros.cardgame`).
5. **`games/card_game/`**: 1 baralho hardcoded (15 cópias, 7 cartas
   distintas), mão de abertura de 3, jogador (HP 20) vs. oponente
   estático (HP 15, sem deck/mão/campo — apenas um alvo de HP).

Achados reais da crítica (incorporados antes de implementar):
`attribute_capacity`/`entry_capacity` do `ModifierStack` da partida têm que
ser dimensionados a partir da COMPOSIÇÃO REAL do baralho (cópias de
`CREATURE`/`BUFF_STAT`, não a contagem de `CardDefinition` distintas) — como
nenhuma criatura é removida do campo e não existe efeito de remoção de buff
no vocabulário do v1, atributos e entradas se acumulam pra sempre ao longo
de uma partida; cursor de mão precisa ser clampado após TODA mutação
(compra ou jogar carta) e a navegação precisa ser protegida contra mão
vazia — `MenuScene` (linhas imutáveis) não cobria esse caso, já que a mão
de `MatchScene` cresce/encolhe ao vivo; `CardLoader` precisa validar o
CONTEÚDO dos argumentos de cada efeito (não só o nome da operação) — um
`operation`/`attribute` inválido em `buff_stat` só surgiria em runtime, no
meio de uma partida, sem essa validação na carga. Achado real dos MEUS
PRÓPRIOS testes (não da crítica): jogar a carta no ÚLTIMO índice da mão
deixava o cursor obsoleto (`== len(hand)` após a remoção) — corrigido
clampando o cursor em toda mutação de mão, não só na compra.

Verificado: 38 testes novos (`tests/cardgame/` — `CardLoader`/`Zone`/
`apply_effect`, incluindo o teste que prova que 2 cópias da mesma carta
nunca se afetam mutuamente via buff; `tests/games/
test_card_game_match_scene.py` — mão vazia, cursor obsoleto, mana
insuficiente, fase atômica; `tests/games/
test_card_game_composition_headless.py`, incluindo uma partida completa
jogada do início ao fim sem crashar) + suite completa (501 testes, só as 12
falhas pré-existentes e não relacionadas de `numba`/DLL do Windows) +
`lint-imports` (3 kept, 0 broken) + sessão manual headless confirmando
compra/custo-mana/jogar carta/resolver efeito/combate/vitória de ponta a
ponta.

Fora de escopo (deferido): habilidades gatilho, combate criatura-vs-criatura
com bloqueio, resposta em pilha, scripting arbitrário de carta, persistência
de baralho entre sessões (nenhum save/load existe hoje em lugar nenhum da
engine — dívida técnica registrada, não resolvida aqui).

## Ordem e dependências (Fase 3)

```
M12 (Platformer -- autocontido, decide o padrão de sistema opt-in -- concluído)
  │
M13 (Tactics -- promove ModifierStack, único marco que mexe no Roguelite -- concluído)
  │
M14 (Card Game -- reusa o ModifierStack já promovido -- concluído)
```

Sequencial (decisão do usuário): M12 primeiro por ser o menor risco/escopo;
M13 antes de M14 porque a promoção do `ModifierStack` (2º consumidor real)
é o que permite o M14 reusá-lo em vez de duplicar o mesmo vocabulário de
buff uma 3ª vez. **Fase 3 (M12–M14) concluída inteira.**
