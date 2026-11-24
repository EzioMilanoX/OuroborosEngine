# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Colisao 3D (ROADMAP M21, passo 1): primitivas, testes de sobreposicao, raycast, chao por
mapa de alturas e um mundo com grade espacial e movimento que desliza nas paredes.

Puro (so math + NumPy): nao importa pygame nem moderngl, e serve tanto ao jogo em 3D na GPU
quanto a regras testadas sem janela. As malhas que desenham as mesmas formas estao em
`ouroboros.interfaces.malhas3d` (o `terreno` usa este mesmo `Relevo`).

    mundo = MundoColisao3D((-50, -50, 50, 50), tamanho_celula=4.0)
    mundo.definir_relevo(Relevo.de_funcao(altura, -50, 50, -50, 50, 1.0))
    mundo.adicionar(AABB((0, 0, 0), (4, 3, 0.3)))             # uma parede
    mundo.adicionar(Capsula.em_pe((8, 0, 2), 12.0, 0.4))       # um tronco
    mundo.construir()                                          # na carga do mapa
    r = mundo.mover_capsula(pe, 1.7, 0.3, (vx * dt, vy * dt, vz * dt))
    pe = tuple(r.posicao); vx, vy, vz = r.ajustar_velocidade(vx, vy, vz)
    if mundo.tem_visao(olhos_do_monstro, olhos_do_jogador): ...
"""
from ouroboros.core.colisao3d.mundo import (
    NENHUMA,
    RELEVO,
    TODAS_CAMADAS,
    MundoColisao3D,
    ResultadoMovimento,
    ResultadoRaio,
)
from ouroboros.core.colisao3d.primitivas import (
    AABB,
    INF,
    Capsula,
    Esfera,
    Forma,
    Raio,
    Vec3,
    contato,
    raio_triangulo,
    raycast,
    sobrepoe,
)
from ouroboros.core.colisao3d.relevo import Relevo

__all__ = [
    "AABB", "Capsula", "Esfera", "Forma", "INF", "MundoColisao3D", "NENHUMA", "RELEVO", "Raio", "Relevo",
    "ResultadoMovimento", "ResultadoRaio", "TODAS_CAMADAS", "Vec3", "contato", "raio_triangulo", "raycast",
    "sobrepoe",
]
