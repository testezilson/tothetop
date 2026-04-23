# -*- mode: python ; coding: utf-8 -*-
# Arquivo de especificação do PyInstaller (mais controle que linha de comando)

import os

block_cipher = None

# Obter diretório raiz do projeto
# SPECPATH é definido pelo PyInstaller quando executa o .spec
try:
    # Tentar usar SPECPATH (definido pelo PyInstaller)
    ROOT_DIR = os.path.normpath(os.path.join(os.path.dirname(SPECPATH), '..'))
except NameError:
    # Fallback: calcular a partir do caminho deste arquivo
    # Este arquivo está em build_scripts/, então voltamos um nível
    current_file = os.path.abspath(__file__)
    ROOT_DIR = os.path.normpath(os.path.join(os.path.dirname(current_file), '..'))

a = Analysis(
    [os.path.join(ROOT_DIR, 'src', 'app', 'main.py')],
    pathex=[ROOT_DIR],
    binaries=[],
    datas=[
        (os.path.join(ROOT_DIR, 'data'), 'data'),
        (os.path.join(ROOT_DIR, 'model_artifacts'), 'model_artifacts'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'pandas',
        'numpy',
        'sklearn',
        'joblib',
        'sqlite3',
        'src.load_and_predict_v3',
        'src.core.shared.paths',
        'src.core.shared.db',
        'src.core.shared.utils',
        'src.core.lol.draft',
        'src.core.lol.prebets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LoLOracleML',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Sem console (janela)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='resources/icon.ico',  # Descomentar se tiver ícone
)
