# -*- mode: python ; coding: utf-8 -*-
# Arquivo de especificação do PyInstaller
# Execute este arquivo da raiz do projeto: pyinstaller build_pyinstaller.spec

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Caminhos relativos à raiz do projeto (onde o pyinstaller é executado)
# Incluir explicitamente src/load_and_predict_v3.py para garantir que seja empacotado
a = Analysis(
    ['src/app/main.py', 'src/load_and_predict_v3.py'],  # Incluir ambos os arquivos
    pathex=['src', '.'],  # Adicionar src e raiz ao path para imports funcionarem
    binaries=[],
    datas=[
        # Incluir todos os arquivos de data/ e model_artifacts/
        # Formato: (origem, destino_no_bundle)
        # No modo onefile, os arquivos vão para _MEIPASS/destino
        (os.path.join(os.getcwd(), 'data'), 'data'),
        (os.path.join(os.getcwd(), 'model_artifacts'), 'model_artifacts'),
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
        # Módulos do projeto (usar imports absolutos)
        'src.load_and_predict_v3',
        'app.ui.main_window',
        'app.ui.pages.lol_prebets',
        'app.ui.pages.lol_prebets_secondary',
        'app.ui.pages.lol_prebets_player',
        'app.ui.pages.lol_draft',
        'app.ui.pages.lol_compare',
        # Incluir todos os submódulos de core para garantir que sejam encontrados
        *collect_submodules('core'),
        'core.shared.paths',
        'core.shared.db',
        'core.shared.utils',
        'core.lol.draft',
        'core.lol.prebets',
        'core.lol.prebets_secondary',
        'core.lol.prebets_player',
        'core.lol.db_converter',
        'core.lol.compare',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Excluir módulos desnecessários para reduzir tamanho
        'matplotlib',
        'PIL',
        'IPython',
        'jupyter',
        # Excluir pkg_resources se não for necessário (evita problema com jaraco)
        'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Usar --onedir em vez de --onefile para facilitar distribuição
# No onedir, os arquivos ficam na mesma pasta do .exe
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
