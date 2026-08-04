# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
UNICA camada do projeto autorizada a importar bibliotecas graficas/audio
concretas (pygame, godot, etc.) -- ver tooling/import_linter_contracts.ini.
Nenhum outro pacote (core, interfaces, roguelite, rhythm) pode importar
daqui para dentro.
"""
