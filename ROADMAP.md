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

---

## Fase 4 — Jogo Musical: modo Osu! (M15) — concluído

Pedido do usuário: um novo modo DENTRO do Jogo Musical já existente (não um
produto novo) — círculos/sliders em posição arbitrária da tela, ao invés das
4 lanes fixas. Investigação confirmou que o Jogo Musical de hoje é 100%
orientado a índice de lane (dtype de nota, beatmap JSON, `JudgmentSystem`) —
nenhum conceito de posição x/y existia em lugar nenhum, e `IInputProvider`
não expunha posição de cursor/mouse (só ações digitais + eixo `[-1,1]`).
Decisões do usuário: escopo círculos + sliders (não só círculos); integração
como modo novo dentro do produto existente (reusa `MenuScene`/
`SongCatalogLoader`/`IAudioClock`/juice de partícula-screenshake); chart de
demonstração gerado por um algoritmo determinístico (não escrito à mão).

1. **`SongEntry.mode`** (`ouroboros/rhythm/loaders/song_catalog_loader.py`):
   campo opcional `"lane"` (default) ou `"osu"` — 100% aditivo,
   `demo_track.json`/`second_track.json` continuam carregando sem nenhuma
   mudança. `MenuScene` nunca lê este campo; só o `on_confirm` de
   `games/rhythm_game/composition.py` o inspeciona pra escolher
   `_start_song` vs. `start_osu_song` (dispatch por igualdade de string, não
   um registry — só 2 modos existem).
2. **Schema paralelo, não extensão** de `SCHEDULED_THREAT_DTYPE`/
   `NOTE_STATE_DTYPE`: `OSU_SCHEDULED_HIT_DTYPE`/`OSU_NOTE_STATE_DTYPE`
   (`ouroboros/rhythm/runtime/schemas.py`) — sem campo `lane`, com
   `x`/`y`/`end_x`/`end_y`/`duration_seconds` (trajeto de slider v1 é
   sempre uma RETA de 2 pontos, sem polyline/Bezier) e acumuladores de
   tracking `tracked_time_seconds`/`good_time_seconds` PONDERADOS POR TEMPO
   REAL (nunca contagem de frames — ver achado da crítica abaixo).
   `OsuBeatmapLoader` (`ouroboros/rhythm/runtime/osu_beatmap_loader.py`)
   mirra `BeatmapLoader`, reusa `BeatmapFormatError`.
3. **Gerador determinístico de posição** (`ouroboros/rhythm/offline/
   osu_placement.py`): deriva x/y/sliders a partir dos onsets JÁ extraídos
   de um beatmap lane-mode existente (nunca reanalisa áudio), seedado por
   `stable_id_from_name(f"{track_id}:osu_placement")`. Ferramenta manual
   `games/rhythm_game/tools/generate_osu_beatmap.py` gerou
   `data/beatmaps/demo_track_osu.beatmap.json` (39 hit-objects, 9 sliders) a
   partir de `demo_track.beatmap.json`.
4. **`IInputProvider.get_cursor_position()`** (capacidade nova de Pilar 2,
   pixels de tela): implementada em `PygameInputProvider` (cacheia
   `pygame.mouse.get_pos()` dentro de `poll()`, mesmo contrato de
   `is_action_held`) e `NullInputProvider` (+ `set_cursor_position` de
   teste). Clique reusa `MOUSE_LEFT` via bindings JSON (`"click"` em
   `data/input_bindings/rhythm_keyboard.json`) — zero capacidade nova de
   parsing de binding.
5. **3 sistemas novos** (`ouroboros/rhythm/runtime/`): `OsuSpawnerSystem`
   (cópia autônoma da lógica de cursor/`searchsorted` de
   `RhythmSpawnerSystem` — os sistemas de ritmo não compartilham base além
   de `ISystem`), `OsuPresentationSystem` (encolhe o anel de aproximação,
   move a bola de slider em tracking — primeiro sistema do motor a animar
   `scale_x/y` por frame), `OsuJudgmentSystem` (julga clique por posição+
   tempo, resolve slider pela fração `good_time_seconds/tracked_time_seconds`
   ao fim da duração, reusa o `Judgment` IntEnum existente).
6. **Renderização sem nenhum primitivo novo de `IRenderer`**: anel/bola são
   entidades companheiras (`transform`+`sprite`, arquétipo
   `osu_visual_marker`) desenhadas de graça pelo `draw_batch` genérico já
   existente; o trajeto do slider reusa a pool `fx`/`FxTtlSystem` JÁ
   existentes (nunca usados pelo Jogo Musical antes) — zero código novo de
   desenho.
7. **`games/rhythm_game/osu/composition.py`** (`start_osu_song`): mesma
   forma de `_start_song`, reusa `ParticleStorage`/`ScreenShake`/
   `PauseScene`/`QuitOnActionSystem` verbatim. `hud.py` ganhou
   `judgment_line_y`/`lane_x_positions` opcionais (default `None`) — reusado
   sem mudança pros dois modos.

Achados reais da crítica (incorporados antes de implementar, o marco mais
extenso desta engine até aqui): **bug quase-certo de crash no 1º frame** —
`NULL_PACKED_HANDLE` empacota `index = -1`, que via máscara de bits vira
`0xFFFFFFFF` (positivo enorme, não `-1`); resolver `ring_entity_id`/
`ball_entity_id` sem mascarar `!= NULL_PACKED_HANDLE` ANTES de
`unpack_batch` estourava `IndexError` assim que qualquer CIRCLE (cujo
`ball_entity_id` é permanentemente o sentinela) entrasse em campo —
corrigido em `OsuPresentationSystem`; **handle obsoleto/contaminação
cruzada** — ao destruir o anel no clique de um slider, `ring_entity_id`
precisa ser resetado pra `NULL_PACKED_HANDLE` NA HORA (não lido
preguiçosamente depois): `MemoryManager` recicla índices em LIFO, então o
índice recém-liberado é o PRÓXIMO devolvido por qualquer `create_entity` —
sem o reset, um leitor vetorizado escreveria silenciosamente na entidade
nova errada; **vazamento de entidade órfã** — um slider NUNCA clicado que
auto-erra precisa destruir AMBAS as companheiras (anel E bola, as duas
ainda vivas), não só o anel como um círculo; **viés de taxa de quadros** —
ponderar a fração de tracking por CONTAGEM DE FRAMES em vez de tempo real
puniria o mesmo comportamento físico do jogador com mais peso numa máquina
mais lenta — corrigido com acumuladores em segundos reais de `delta_time`;
**duração de slider podendo sobrepor o próximo onset** — verificado
numericamente contra o beatmap real (gaps de ~0.488s/0.511s, mais curtos
que 1 batida a 117bpm): o gerador agora clampa `duration_seconds` contra o
intervalo real até o próximo onset. Achado real dos MEUS PRÓPRIOS testes
(não da crítica): `hud.py` computava `min(lane_x_positions)`/`max(...)`
EAGERMENTE fora do closure retornado — chamar com `lane_x_positions=None`
(modo Osu!) levantava `TypeError` antes de qualquer frame renderizar,
corrigido computando as duas variáveis condicionalmente.

Verificado: 44 testes novos (`tests/rhythm/test_osu_beatmap_loader.py`/
`test_osu_placement.py` — incluindo o teste que prova o clamp de duração
contra o gap real do beatmap/`test_osu_spawner_system.py`/
`test_osu_presentation_system.py` — regressão direta do bug de
`NULL_PACKED_HANDLE`/`test_osu_judgment_system.py` — regressão do reset de
handle obsoleto, do vazamento de entidade órfã, e da invariância de taxa de
quadros do tracking; `tests/games/test_rhythm_game_osu_composition_headless.py`,
incluindo ~4s de frames reais sem crashar) + suite completa (545 testes,
todos passando) + `lint-imports` (3 kept, 0 broken) + sessão manual headless
confirmando spawn/aproximação/clique/tracking/julgamento de ponta a ponta.

Fora de escopo (deferido): spinners; sliders curvos/Bezier/multi-waypoint
(só reta, 2 pontos); pontuação separada de cabeça/cauda/tick de slider;
resolução de empilhamento/sobreposição de hit-objects além da
rejeição-e-reamostra com teto fixo; replay/trilha de cursor; curvas de
approach-rate/circle-size por dificuldade (constantes escalares simples);
hit-test compensado por screen-shake; promoção do padrão de RNG
determinístico do gerador pra `ouroboros.core`; mais de 1 beatmap Osu! real
(só `demo_track_osu` — `second_track` continua só lane-mode).

## Fase 5 — Primitivas vetoriais de UI e fontes (M16) — concluído

Pedido vindo de um produto novo, o **Karmabound** (torneio por turnos com uma
roleta em forma de mandala de selos com kanji, envolta por correntes). A tela
dele precisa de círculos, arcos, linhas e polígonos em coordenadas de tela, e
de texto em kanji com uma fonte de pincel. O `IRenderer` não tinha nenhuma das
duas coisas: `draw_batch` só aproximaria formas com sprites, e `draw_text`
usava sempre a fonte padrão do backend, sem glifos CJK.

1. **`load_font(font_id, file_path)`** e **`draw_text(..., font_id=None)`**
   (`ouroboros/interfaces/renderer.py`): mesmo modelo de `load_texture` —
   registra o arquivo sob um inteiro; um `font_id` nunca carregado cai na
   fonte padrão. **Não é abstrato** (fonte é apresentação, como `draw_text`),
   então todo backend existente continua válido. `font_id` é parâmetro
   opcional no fim da assinatura: chamadas antigas não mudam.
2. **`draw_ui_line/circle/arc/polygon`**: mesma família de `draw_ui_rect` —
   coordenadas de TELA, alpha respeitado, sem camera offset, só na camada de
   cenas/UI, default no-op. Arco em radianos, 0 = direita, anti-horário como
   visto na tela.
3. **`PygameRenderer`**: cache de fontes passou de `{tamanho}` para
   `{(font_id, tamanho)}` e o de texto ganhou `font_id` na chave; `load_font`
   invalida só as entradas daquela fonte. Primitivas opacas desenham direto;
   translúcidas passam por uma `SRCALPHA` do tamanho da caixa da forma.
   Antialiasing em linha fina, círculo e contorno de polígono.
4. **`NullRenderer`** registra fontes em `_loaded_fonts` (espelho de
   `_loaded_textures`) e herda os no-ops das primitivas.

Achado durante os testes: o pygame-ce **aceita abrir** um arquivo que não é
fonte e só falha no primeiro `render`. `load_font` renderiza um glifo ao
carregar, para o erro aparecer no carregamento e não no meio de um frame.

Compatibilidade verificada nos consumidores: `HBPygameRenderer` (Hertz &
Beats) herda de `PygameRenderer` mas usa fontes próprias, sem tocar no cache
interno; os renderers falsos dos testes do Penumbra sobrescrevem `draw_text`
sem `font_id`, o que continua válido porque nenhum chamador deles passa o
parâmetro.

Verificado: 12 testes novos (`tests/interfaces/test_ui_primitives.py`, lendo
pixels da tela real sob o driver dummy: preenchido vs. contorno, alpha,
convenção do arco, polígono, formas degeneradas, troca de fonte, fallback de
id desconhecido, arquivo inválido, `NullRenderer`) + suíte completa (605
testes, todos passando). `lint-imports` não rodou localmente (não instalado);
as mudanças só tocam `ouroboros.interfaces` (importa `typing`) e
`ouroboros.adapters` (importa `math`), sem import novo entre camadas.

Fora de escopo: texto rotacionado; espessura em linha antialiasada; curvas de
Bézier; gradientes; versão nova do pacote (fica em 0.2.2 até a próxima
release).

## Fase 6 — Volume da faixa (M17) — concluído

Pedido do **Karmabound**, que ganhou música (faixas sintetizadas em loop) e uma
tela de opções com volume. Os efeitos já tinham volume por disparo
(`play_one_shot(volume=...)`); a faixa em stream não tinha como baixar.

1. **`IAudioEngine.set_track_volume(volume)`**: 0.0 (mudo) a 1.0, limitado;
   vale para a faixa atual e para as próximas `play_track`. **Não é abstrato**
   (default no-op, como `register_tone`): todo backend existente continua válido.
2. **`PygameAudioEngine`** guarda o volume e o reaplica a cada `play_track`,
   porque carregar outra faixa no `pygame.mixer.music` pode voltar ao volume cheio.
3. **`NullAudioEngine`** registra o volume em `_track_volume`, para inspeção em teste.

Verificado: 3 testes novos (`tests/interfaces/test_track_volume.py`: default
no-op, limites no Null, pygame sob driver dummy mantendo o volume entre faixas)
+ suíte completa (608 testes, todos passando).

## Fase 7 — Imagem na camada de UI (M18) — concluído

Pedido do **Ryoiki**, que passou a pintar os chefes como sprites (gerados em 4x com
contorno e sombreamento, reduzidos com suavização) e precisava desenhá-los em coordenadas
de tela, junto das outras primitivas de UI. Até aqui textura só entrava por `draw_batch`.

1. **`IRenderer.draw_ui_image(texture_id, x, y, *, anchor, flip_x, alpha, scale)`**:
   desenha uma textura já carregada por `load_texture`. `anchor` é a fração da imagem que
   cai em `(x, y)` (`(0.5, 1.0)` = os pés). **Não é abstrato** (default no-op): todo
   backend existente continua válido.
2. **`PygameRenderer`** cacheia cada variação (espelho, escala) em
   `_texture_scale_cache`, para não refazer `flip`/`smoothscale` a cada quadro.

Verificado: 5 testes novos (`tests/interfaces/test_ui_image.py`: âncora nos pés, espelho,
escala e alfa, textura desconhecida, default no-op) + suíte completa passando.

## Fase 8 — Vários estilos de arte (M19–M22) — planejada

Pedido do Enzo depois dos sprites do Ryoiki: a engine deve servir bem a **quatro estilos**
(ilustração cel-shading, pixel art, tinta/sumi-e e flat vetorial com luz), priorizando
**desempenho, pipeline de arte e câmera/projeções**, com a GPU como **backend novo e
opcional** (nenhum dos jogos atuais muda sem pedir).

**Medição que orienta a ordem (2026-11-11):** reaproveitar superfícies translúcidas de UI
no backend pygame (em vez de criar uma por chamada) ficou ~45% *mais lento* (0,060 contra
0,042 ms por trio círculo + polígono + retângulo): criar uma Surface pequena já zerada é
barato, limpar uma reaproveitada custa mais. Foi revertido. O ganho de desempenho de
verdade está em desenhar na GPU (M21), não em micro-otimizar o backend de CPU.

1. **M19 — Pipeline de arte.** Spritesheet/atlas (um PNG + JSON, compatível com o JSON do
   Aseprite); `Animacao` (quadros, fps, laço, eventos por quadro, ex.: "impacto");
   filtro por textura: `suave` (ilustração) ou `nitido` (pixel art: escala por vizinho mais
   próximo, só múltiplos inteiros); troca de paleta para pixel art. Generalizar o
   `Pintor` do Ryoiki (`tools/gerar_sprites.py`: peças com contorno, sombra e brilho por
   máscara, 4x reduzido) como ferramenta da engine para gerar arte cel-shading.
2. **M20 — Câmera e projeções.** `Projecao` com `tela_de(x, y, z)` / `mundo_de`:
   de cima, 3/4 (achata o chão, como o Ryoiki faz hoje), isométrica; e uma fila de
   desenho por profundidade (y, depois z) para figuras em pé, sombras e projéteis.
3. **M21 — Backend GPU opcional** (`pygame._sdl2.video`: `Renderer`/`Texture`): o mesmo
   `IRenderer` com as primitivas de UI e `draw_ui_image` na GPU; escala, rotação e
   transparência quase de graça; modos de mistura (aditivo, multiplicar). Cada jogo
   escolhe o backend no `EngineConfig`; medir com o mesmo benchmark acima.
4. **M22 — Estilos.** Tinta/sumi-e: traço de pincel com espessura variável e textura
   (manchas, respingos); flat com luz: brilho aditivo e bloom (camada fora da tela
   borrada); cel-shading e pixel art já cobertos por M19.

**Vitrine (2026-11-11):** `games/vitrine_estilos/` mostra os quatro estilos na mesma cena,
para escolher o rumo antes de M19–M22. Hoje cada estilo é pintado pelo próprio jogo
(`arte.py`) e só exibido pela engine; conforme M19–M22 saírem, o que cada estilo usa
(o pintor cel-shading, o filtro nítido, o pincel, o bloom) passa para dentro da engine e a
vitrine vira o teste visual de cada um.

**Pesquisa de técnicas (2026-11-11), já aplicada na vitrine** (cada uma vira peça da
engine em M19/M22):

- *Cel-shading:* a sombra puxa a cor para o frio, não para o preto (a "troca de matiz",
  como nas notas de render ilustrativo do Team Fortress 2); a luz de recorte contorna a
  silhueta do lado da luz de trás; tons chapados, sem degradê; contorno externo mais
  grosso que as linhas internas; sombra de contato nos pés.
- *Pixel art:* rampas de cor com o matiz girando (sombra para o azul/roxo, luz para o
  amarelo); contorno seletivo (o tom mais escuro da própria peça, não preto);
  pontilhado ordenado (Bayer) para transições; paleta curta; ampliar só por vizinho mais
  próximo; o movimento menor que um pixel se faz trocando cores, não posição.
- *Sumi-e:* o pincel como um feixe de cerdas que muda ao longo do traço (modelo de
  Strassmann, 1986): pressão, falhas de pincel seco, cerdas soltas; a tinta se espalha
  nas fibras (difusão; os modelos sérios usam autômatos celulares); o grão do papel
  multiplica a tinta.
- *Flat com luz:* bloom = recortar o que brilha (limiar com joelho suave), borrar numa
  pirâmide de reduções (dual Kawase, mais barato que o gaussiano largo) e somar; a
  aberração cromática entra por último; o chão molhado espelha a luz.

## Fase 9 — 3D (estudo; nada implementado)

**Como as engines 3D se organizam.** O Godot é o exemplo mais claro: três camadas,
*cena* (a árvore de nós), *servidores* (renderização, física, áudio: singletons que
devolvem identificadores opacos, os RIDs) e *drivers*. No 3D, tudo que aparece é um
recurso (malha, material) mais uma instância dentro de um "cenário", vista por uma câmera
num viewport; no 2D o papel do cenário é o do canvas. A OuroborosEngine já tem a mesma
forma: núcleo ECS em cima, interfaces (`IRenderer`) no meio, adaptadores (pygame) embaixo.
Um 3D aqui seria um "servidor de render 3D" atrás de uma interface nova, não um remendo
no `IRenderer` 2D.

**Opções em Python.**
- *Panda3D:* maduro (Disney/CMU), núcleo em C++, grafo de cena próprio, licença BSD.
- *Ursina:* por cima do Panda3D, entidades simples, MIT; mais fácil, menos maduro.
- *ModernGL:* OpenGL 3.3 puro (shaders, framebuffers, texturas): nada pronto, controle
  total; casa com o pygame-ce (o pygame cuida da janela e da entrada, o GL desenha).
  Efeitos em cadeia = um framebuffer por passo, a saída de um vira a entrada do próximo.
  Risco: empacotar com PyInstaller e exigir OpenGL 3.3.
- *Godot* (GDScript/C#, não Python): o caminho se um jogo for 3D de verdade.

**3D com cara de 2D** (o que o Ryoiki ganharia): no Guilty Gear Xrd, o contorno é um
*casco invertido* (a malha empurrada pelas normais, com a espessura corrigida na tela),
o sombreamento é um degrau (duas cores, aceso ou não), as normais são editadas à mão para
a sombra cair como num desenho, as linhas internas vão pintadas na textura e cada
personagem tem a própria luz.

**Leitura para a OuroborosEngine** (a decidir com o Enzo):
1. **Recomendado:** fazer o M21 (GPU) com ModernGL. Ele já entrega shaders para os
   quatro estilos (bloom de verdade, toon, tinta) e é a base de qualquer 3D depois.
2. Uma camada 3D própria sobre ModernGL (malha, câmera em perspectiva, toon com casco
   invertido), convivendo com o ECS: grande, mas mantém o Data-Oriented e o Zero-GC.
3. Usar Panda3D/Ursina como backend: 3D rápido, mas com grafo de cena próprio
   brigando com o ECS e sem o controle de memória que a engine promete.
4. Para um projeto que precise de 3D pleno: Godot, e a OuroborosEngine segue 2D/2.5D.

**Prova de polígonos (2026-11-11): o 5º estilo da vitrine, low poly, é 3D de verdade**
(`arte._cena_3d` + `arte._render_3d`, só numpy e polígonos do pygame, ~700 triângulos):
malhas de triângulos, câmera em perspectiva que passeia, uma cor por face (normal contra a
luz, sombra puxada para o frio), neblina pela distância, descarte de faces de costas e o
algoritmo do pintor (do longe ao perto). O que ela ensinou:
- **Funciona na CPU para poucos triângulos e quadros pré-pintados** (12 quadros em <1 s).
  Em tempo real e com muitos triângulos, não: precisa de GPU (z-buffer, M21).
- **Triângulo que cruza a câmera some inteiro** sem recorte no plano próximo; o chão teve
  de virar ladrilhos. Uma camada 3D séria precisa recortar triângulos (clipping).
- **O pintor erra quando faces se cruzam** (ordenar pela profundidade média não basta);
  na GPU o z-buffer resolve por pixel.
- **Utilidade mais imediata: 3D para virar sprite** (o que Dead Cells faz): modelar um
  personagem uma vez em polígonos e renderizar todos os ângulos e quadros como sprites,
  com o estilo que quiser (cel, pixel). Para o Ryoiki, isso daria o feiticeiro e os
  chefes em 8 direções sem desenhar cada uma.

**Animação na vitrine (2026-11-11):** 12 quadros a 8 qps davam um golpe travado (4 quadros
para o corte inteiro e volta seca para a guarda). Agora são 48 quadros a 24 qps, e a pose
é função do tempo (`pose_t`), com os princípios clássicos: respira em guarda, **antecipa**
(a espada recua e o corpo abaixa), **corta** rápido desacelerando no fim (ease-out),
**segura** o golpe enquanto o rastro se desfaz e **volta** suave (ease-in-out); o laço
fecha sem salto. No sumi-e o traço muda de 4 em 4 quadros (o "tremor de mão" das animações
desenhadas), em vez de a cada quadro. Para não pesar a abertura, o cel-shading pinta só a
região do personagem, o fundo do pixel art é pintado uma vez, e os quadros ficam num cache
em disco por estilo, refeito só quando `arte.py` muda (1ª abertura ~14 s, depois ~1,5 s).
Isso é o embrião do M19: `Animacao` por tempo com curvas e eventos, e cache de arte gerada.


**3D da vitrine em módulo próprio (2026-11-11):** `games/vitrine_estilos/tres_d.py`. Malhas
fechadas agora são viradas para fora de verdade (antes as caixas tinham as normais invertidas e o
culling mostrava as faces de trás — passava despercebido por serem convexas, mas quebraria com
z-buffer). Luz por vértice (hemisférica + direcional + pontual + foco), como o PS1 e as GPUs antigas.
- **lowpoly:** luz de três pontos (chave quente por trás, preenchimento frio), sombras projetadas no
  chão ao longo da luz (uma camada multiplicada, sem escurecer duas vezes), lanternas de pedra que
  acendem o entorno, pinheiros, vaga-lumes, brilho no que emite luz; pintor em camadas
  (fundo → chão → sombras → objetos).
- **terror (PS1):** 320×180 ampliado 3× sem suavizar; vértices grudados no pixel inteiro (o tremor);
  **z-buffer por pixel em numpy** com cor Gouraud afim (sem correção de perspectiva); neblina preta
  pela profundidade; cor de 15 bits com Bayer; grão e vinheta; só a lanterna ilumina, e ela falha.
  ~0,1 s por quadro na CPU. Por que funciona como terror: a baixa resolução e a neblina deixam
  lacunas que o jogador preenche com o pior; o tremor faz o mundo parecer instável; rostos de
  poucos polígonos caem no estranho.
- O z-buffer daqui é o núcleo do que um backend 3D (M21, ModernGL) faria na GPU: mesmas entradas
  (malha, câmera, luz por vértice), saída por pixel.
