# Changelog

O que mudou na engine, do ponto de vista de quem escreve um jogo sobre ela. O porquê
de cada marco e os detalhes técnicos ficam no [ROADMAP.md](ROADMAP.md).

## 0.4.0 (2026-11-24)

### Novo: colisão 3D (`ouroboros.core.colisao3d`) — M21, passo 1

- Primitivas `AABB`, `Esfera`, `Capsula` (com `Capsula.em_pe(pe, altura, raio)` para
  personagens) e `Raio`; `sobrepoe`, `contato` (normal + profundidade para empurrar para
  fora), `raycast` e `raio_triangulo`, puros e testados contra força bruta.
- `Relevo`: chão por mapa de alturas (`Relevo.de_funcao(altura, x0, x1, z0, z1, passo)`),
  com `altura`, `normal` e `raycast` exatos — a mesma superfície que o `terreno` desenha.
- `MundoColisao3D`: o cenário sólido em arrays pré-alocados, grade espacial em x/z
  (broadphase), camadas/máscara, `consultar`, `sobrepoe_esfera/capsula`, `raycast`
  (percorre a grade célula a célula) e `tem_visao`.
- Movimento que desliza: `mover_capsula`/`mover_esfera` em passos de meio raio (não
  atravessa parede fina), assenta no chão, rampa até `rampa_max_graus` é chão e mais
  íngreme é parede; `ResultadoMovimento.no_chao`/`bateu`/`ajustar_velocidade`.
- Zero-GC no caminho quente: mover e lançar raio não disparam o coletor (há teste).

### Novo: construtores de malha (`ouroboros.interfaces.malhas3d`) — M21, passo 1

- `caixa`, `bloco` (mesma assinatura da vitrine/TerrorPS1), `plano`, `terreno(relevo)`,
  `disco`, `cilindro` (afinando, ou `cone`), `esfera` (icosfera) e `extrusao` (polígono em
  x/z levantado, convexo ou não; `triangular_poligono` por corte de orelhas).
- Tudo devolve `Malha` (os arrays de `IRenderer3D.criar_malha`), com os triângulos virados
  para fora; `+`/`juntar`, `transformada`, `girada`, `com_cor`, `aabb`, `criar_em(r3d)` e
  `Malha.de_triangulos` (lê o formato antigo de lista de triângulos).

### Novo: replay (`ouroboros.bootstrap.replay`)

- Subiu do BulletHell e ficou genérico: `ReplayRecorder` (entradas por quadro em bits, dt,
  eixos e cursor opcionais, semente, versão do jogo, `meta`; arrays pré-alocados),
  `ReplayInputProvider` (um `IInputProvider` que toca a gravação), `Replay.save`/`load`
  (JSON com arrays comprimidos, escrita atômica pelo `SaveFile`, `ReplayError` para
  arquivo ruim, formato novo demais ou outra versão do jogo).
- Dessincronização opcional: `hash_every=N` + `world_state_hash(world, pools)` grava um
  CRC32 do estado a cada N quadros; `ReplayInputProvider.verify` aponta o primeiro quadro
  diferente (`desync_frame`).

### Ferramentas

- `ruff check .` volta a passar: regras fixadas em `[tool.ruff]` (as antigas regras padrão,
  E4/E7/E9/F — o ruff 0.16 ampliou o padrão) e 16 imports/variáveis sem uso removidos.
- Contrato do import-linter: `ouroboros.bootstrap.replay` também não pode importar pygame.
