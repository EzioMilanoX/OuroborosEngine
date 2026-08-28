# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Armazenamento SoA de particulas (ROADMAP M3): nascimento em lote, integracao vetorizada, morte por ttl."""
from __future__ import annotations

import numpy as np

PARTICLE_DTYPE: np.dtype = np.dtype([
    ("position_x", np.float32),
    ("position_y", np.float32),
    ("velocity_x", np.float32),
    ("velocity_y", np.float32),
    ("ttl_seconds", np.float32),
    ("ttl0_seconds", np.float32),
    ("size", np.float32),
    ("tint_r", np.uint8),
    ("tint_g", np.uint8),
    ("tint_b", np.uint8),
    ("tint_a", np.uint8),
])
"""Schema de UMA particula. Definido AQUI (nao em `ouroboros.core.components.schemas`)
porque, diferente de `fx`, particulas nao sao uma pool generica compartilhada via
`World`/`COMPONENT_SCHEMAS` -- e um schema privado de quem possui a `ParticleStorage`,
mesma convencao de `DungeonStreamingSystem.ROOM_INSTANCE_DTYPE`."""


class ParticleStorage:
    """
    Armazenamento denso de particulas, com capacidade fixa. Diferente de
    `ComponentPool` (Pilar 1), NAO tem endereçamento esparso por
    `entity_index`: particulas nao tem identidade externa estavel --
    nada em outro lugar do codigo jamais precisa endereçar "a particula
    N" entre frames (diferente de `room_id` em `DungeonStreamingSystem`,
    que É um indice de dominio estavel reaproveitado de proposito).
    Forcar particulas por `ComponentPool` inventaria uma identidade
    estavel que nada usa, so pra ganhar uma API que nao serve
    nascimento/morte em massa anonimos.

    Nao gera nenhuma aleatoriedade propria -- `emit_burst` recebe
    arrays ja prontos do chamador (que usa seu proprio gerador, ex.
    `ouroboros.roguelite.generation.random.StrictRandom` se quiser
    determinismo).

    Integracao de desenho: NAO ha pool `World`-registrada de particulas
    nem cena dedicada -- `ParticleUpdateSystem` (mesmo modulo irmao
    `ouroboros.core.systems.particle_update_system`) ja roda
    `update()` sozinho via `world.register_system(...)` (congela
    durante uma pausa, de graca, mesma semantica de tudo mais); o
    desenho e so mais uma chamada a `IRenderer.draw_particles(...)`,
    tipicamente de dentro do callback de `GameLoop.set_on_draw_ui`
    (global, ja chamado todo frame independente da cena ativa).
    """

    def __init__(self, capacity: int) -> None:
        """Pre-aloca `capacity` linhas -- nunca redimensionado depois."""
        self._dense = np.zeros(capacity, dtype=PARTICLE_DTYPE)
        self._capacity = capacity
        self._count = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def count(self) -> int:
        """Numero de particulas atualmente vivas (linhas validas em `active_view()`)."""
        return self._count

    def active_view(self) -> np.ndarray:
        """View (SEM copia) de `dense[:count]`: layout SoA das particulas vivas."""
        return self._dense[: self._count]

    def emit_burst(
        self,
        position_x: np.ndarray,
        position_y: np.ndarray,
        velocity_x: np.ndarray,
        velocity_y: np.ndarray,
        ttl_seconds: np.ndarray,
        size: np.ndarray,
        tint_rgba: np.ndarray,
    ) -> int:
        """
        Emite `len(position_x)` novas particulas de uma vez, a partir de
        arrays paralelos ja prontos. Trunca SILENCIOSAMENTE se exceder a
        capacidade restante -- divergencia DELIBERADA do idioma irmao
        `ComponentPool.attach` (que levanta `IndexError` em excesso):
        aqui um estouro e puramente cosmetico (uma tela cheia de
        explosoes nao devia travar o jogo por causa disso). Retorna
        quantas particulas foram de fato emitidas (pode ser menor que o
        pedido -- cabe ao chamador decidir se quer checar).

        `ttl0_seconds` (o ttl no momento do nascimento) e gravado
        automaticamente a partir do proprio `ttl_seconds` recebido aqui --
        nao ha parametro separado pra isso, ja que "atual" e "inicial" sao
        o mesmo valor no instante da emissao. Existe pra quem precisa de
        fade-por-idade no desenho (`tint_a = 255 * ttl_seconds/ttl0_seconds`),
        algo que `update()` nao calcula sozinho (so integra posicao e
        decrementa `ttl_seconds`) -- sem isso, a fracao de vida restante de
        cada particula seria irrecuperavel apos a primeira compactacao por
        morte de outra particula (`update()` reordena o array denso; nao ha
        identidade estavel por particula pra um chamador rastrear o ttl
        inicial por fora).
        """
        requested = position_x.shape[0]
        available = self._capacity - self._count
        actual = min(requested, available)
        if actual <= 0:
            return 0

        start, end = self._count, self._count + actual
        view = self._dense
        view["position_x"][start:end] = position_x[:actual]
        view["position_y"][start:end] = position_y[:actual]
        view["velocity_x"][start:end] = velocity_x[:actual]
        view["velocity_y"][start:end] = velocity_y[:actual]
        view["ttl_seconds"][start:end] = ttl_seconds[:actual]
        view["ttl0_seconds"][start:end] = ttl_seconds[:actual]
        view["size"][start:end] = size[:actual]
        view["tint_r"][start:end] = tint_rgba[:actual, 0]
        view["tint_g"][start:end] = tint_rgba[:actual, 1]
        view["tint_b"][start:end] = tint_rgba[:actual, 2]
        view["tint_a"][start:end] = tint_rgba[:actual, 3]
        self._count = end
        return actual

    def update(self, delta_time: float) -> None:
        """Integra posicao por velocidade, decrementa ttl, e compacta (remove)
        particulas expiradas -- tudo vetorizado, nenhum laco Python por particula."""
        if self._count == 0:
            return
        view = self._dense[: self._count]
        view["position_x"] += view["velocity_x"] * delta_time
        view["position_y"] += view["velocity_y"] * delta_time
        view["ttl_seconds"] -= delta_time

        alive_mask = view["ttl_seconds"] > 0.0
        alive_count = int(np.count_nonzero(alive_mask))
        if alive_count == self._count:
            return  # nada morreu neste frame -- evita a copia de compactacao
        # `view[alive_mask]` sempre materializa uma copia nova em NumPy (fancy
        # indexing booleano nunca e uma view) -- a atribuicao abaixo le essa
        # copia ja pronta antes de escrever no prefixo do MESMO buffer, sem
        # risco de aliasing mesmo quando os dois se sobrepoem.
        self._dense[:alive_count] = view[alive_mask]
        self._count = alive_count
