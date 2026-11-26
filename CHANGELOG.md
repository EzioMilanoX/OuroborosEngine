# Changelog

O que mudou na engine, do ponto de vista de quem escreve um jogo sobre ela. O porquê
de cada marco e os detalhes técnicos ficam no [ROADMAP.md](ROADMAP.md).

## 0.5.0 (2026-11-26)

### Novo: projeções de câmera (`ouroboros.core.projecao`) — M20

- `Projecao(modo, centro=, tela=, zoom=, escala_y=0.62, escala_iso=0.5, escala_z=1.0)` com três
  modos: `DE_CIMA`, `TRES_QUARTOS` (o chão achatado por `escala_y` e a altura z subindo na
  tela, as mesmas contas do Ryoiki) e `ISOMETRICA` (chão girado 45° e achatado, o losango 2:1).
- `tela_de(x, y, z)` / `mundo_de(sx, sy, z=0)` (a inversa no plano da altura z), `tela_x`/
  `tela_y` (escalar sem tupla), `profundidade(x, y)` (a chave de ordem de desenho, que não
  depende da câmera) e `centralizar`.
- Em lote, escrevendo em arrays já alocados: `tela_de_lote`, `mundo_de_lote`,
  `profundidade_lote` (`reservar(n)` no carregamento e não aloca mais).
- No chão: `eixos_elipse_chao(raio)`, `pontos_elipse_chao(x, y, raio, out=)` e
  `sombra(x, y, z, raio)` (encolhe e clareia com a altura).
- `FilaProfundidade(capacidade)`: `adicionar(id, profundidade, z, camada)` por quadro e
  `ordenar()` devolve os ids de trás para a frente (profundidade, depois z, depois camada),
  ordenando no lugar, sem alocar.

### Novo: modo ASCII (`ouroboros.core.ascii` + adapter pygame) — M22

- `TelaAscii(colunas, linhas, cor=, fundo=)`: caracteres, cor de frente e fundo opcional em
  arrays NumPy; `limpar`, `por`, `texto`, `linha` (escolhe `-|/\` pela inclinação),
  `retangulo`, `elipse` (cheia ou só a borda) e `sprite`.
- `SpriteAscii(arte, cor=, cor_por_caractere=, mapa_cores=, paleta=, transparente=" ",
  ancora=)`: arte de várias linhas, caractere transparente, âncora nos pés e espelho pronto
  (troca `/`↔`\`, `(`↔`)`, `<`↔`>`, `[`↔`]`…); `AnimacaoAscii(quadros, fps, laco)`.
- `IRenderer.draw_ascii(tela, x, y, tamanho)` e `ascii_cell_size(tamanho)`: no pygame, fonte
  monoespaçada com cache de glifos por caractere + cor (nada é renderizado de novo a cada
  quadro).
- Filtro ASCII: `IRenderer.set_ascii_filter(FiltroAscii(...))` converte o quadro já desenhado
  em caracteres pela luminância de cada célula (rampa `" .:-=+*#%@"`), com a cor média da
  célula, realce, fundo e `area` (deixe o HUD de fora). Desligado por padrão; também liga pelo
  JSON da configuração (`"ascii_filter": true` ou um objeto com os campos). Ainda não vale no
  `GLRenderer` (`draw_ascii` vale).
- Novos métodos da interface não são abstratos (no-op/`None`): nenhum backend quebra.

### Demo: ASCII Knight (`games/ascii_knight/`)

- Cavaleiro em arte ASCII (parado, andando, golpe de espada, pulo; vira para os dois lados) numa
  arena 3/4 com pilares, árvores, duas gosmas e um morcego, ordenados pela fila de
  profundidade, com sombra elíptica e pulo. F troca ASCII nativo / filtro ASCII / render
  normal; P troca a projeção. `python -m games.ascii_knight.main`.

### Ferramentas

- Zero-GC conferido com `gc.callbacks` nos testes de projeção, fila e primitivas ASCII.

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
