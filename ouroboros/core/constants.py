# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Constantes globais de infraestrutura do nucleo ECS."""

DEFAULT_ENTITY_CAPACITY: int = 65_536
"""Capacidade padrao de entidades simultaneas, usada quando um produto
concreto (roguelite/rhythm) nao especifica a sua propria via config
data-driven. E sempre um teto FIXO -- nunca redimensionado em runtime."""

INVALID_ENTITY_INDEX: int = -1
"""Sentinela de indice de entidade invalido, usado em free-lists e em
mapas esparsos de ComponentPool ('sem componente anexado')."""

INVALID_DENSE_ROW: int = -1
"""Sentinela de linha densa invalida dentro de um ComponentPool
(equivalente a 'entidade nao possui este componente')."""
