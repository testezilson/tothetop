# -*- mode: python ; coding: utf-8 -*-
# Arquivo de especificação do PyInstaller - Modo ONEDIR COM CONSOLE (para debug)
# Execute: pyinstaller build_pyinstaller_debug.spec --clean

import os

block_cipher = None

# Obter diretório atual (raiz do projeto)
ROOT_DIR = os.getcwd()

a = Analysis(
    ['src/app/main.py', 'src/load_and_predict_v3.py'],
    pathex=['src', '.'],
    binaries=[],
    datas=[
        # Usar caminhos absolutos para garantir que sejam encontrados
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
        # Módulos do scipy que o PyInstaller não detecta automaticamente
        'scipy._lib.array_api_compat.numpy.fft',
        'scipy._lib.array_api_compat.numpy',
        'scipy._lib.array_api_compat',
        'scipy._lib',
        'scipy.sparse._sputils',
        'scipy.sparse._base',
        'scipy.sparse',
        # Módulos do projeto
        'src.load_and_predict_v3',
        'app.ui.main_window',
        'app.ui.pages.lol_prebets',
        'app.ui.pages.lol_draft',
        'core.shared.paths',
        'core.shared.db',
        'core.shared.utils',
        'core.lol.draft',
        'core.lol.prebets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'IPython',
        'jupyter',
        'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Modo ONEDIR COM CONSOLE (para ver logs de debug)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # Importante para onedir
    name='LoLOracleML',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # COM CONSOLE para ver debug
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# COLLECT - agrupa tudo em uma pasta
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LoLOracleML',
)
