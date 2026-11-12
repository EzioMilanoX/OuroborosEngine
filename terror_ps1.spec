# -*- mode: python ; coding: utf-8 -*-
"""
Receita do executavel da demo de terror PS1:  python -m PyInstaller terror_ps1.spec

Sai em dist/TerrorPS1/ (TerrorPS1.exe e a pasta _internal ao lado). Leva o
config.json da demo e os dois arquivos de data/ que ele aponta; `main.py` os
acha pelo `ResourceRoot`, nunca pelo diretorio atual. `onedir`, nao `onefile`:
o Controle Inteligente de Aplicativos barra o onefile (ver karmabound.spec).
O moderngl acha o contexto OpenGL pelo pacote `glcontext`, importado por nome.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

RAIZ = Path(SPECPATH).resolve()

datas = [
    (str(RAIZ / "games" / "terror_ps1" / "config.json"), "games/terror_ps1"),
    (str(RAIZ / "data" / "input_bindings" / "terror_ps1_teclado.json"), "data/input_bindings"),
    (str(RAIZ / "data" / "difficulties" / "card_game" / "basic.json"), "data/difficulties/card_game"),
]
icone = RAIZ / "games" / "terror_ps1" / "icone.ico"

analysis = Analysis(
    [str(RAIZ / "games" / "terror_ps1" / "main.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=[n for n in collect_submodules("ouroboros") if not n.startswith("ouroboros.rhythm.offline")]
    + collect_submodules("games.terror_ps1") + collect_submodules("games.vitrine_estilos")
    + collect_submodules("glcontext") + ["moderngl"],
    excludes=["tkinter", "unittest", "pytest", "numpy.testing", "pygame.tests",
              "scipy", "matplotlib", "PIL", "ouroboros.rhythm.offline"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="TerrorPS1", debug=False,
          strip=False, upx=False, console=False, icon=str(icone) if icone.is_file() else None)
collected = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="TerrorPS1")
