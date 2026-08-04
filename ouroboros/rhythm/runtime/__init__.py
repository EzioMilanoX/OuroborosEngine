# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Runtime do jogo musical (DENTRO do loop de gameplay). Zero-GC estrito.
NUNCA importa nada de ouroboros.rhythm.offline nem librosa, direta ou
transitivamente.
"""
