# -*- mode: python ; coding: utf-8 -*-
# Arquivo de especificação do PyInstaller (versão corrigida)
# Execute este arquivo da raiz do projeto: pyinstaller build_pyinstaller_fix.spec

import os

block_cipher = None

# Caminhos relativos à raiz do projeto (onde o pyinstaller é executado)
a = Analysis(
    ['src/app/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data', 'data'),
        ('model_artifacts', 'model_artifacts'),
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
    excludes=[
        # Excluir módulos desnecessários para reduzir tamanho
        'matplotlib',
        'PIL',
        'IPython',
        'jupyter',
        # Excluir pkg_resources para evitar problema com jaraco
        'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remover hook problemático do pkg_resources
# Isso evita o erro "No module named 'jaraco'"
for hook in a.hooksconfig:
    if 'pkg_resources' in str(hook):
        a.hooksconfig.pop(hook, None)

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
