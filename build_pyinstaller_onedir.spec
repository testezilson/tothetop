# -*- mode: python ; coding: utf-8 -*-
# Arquivo de especificação do PyInstaller - Modo ONEDIR (recomendado)
# Execute: pyinstaller build_pyinstaller_onedir.spec

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Obter diretório atual (raiz do projeto)
ROOT_DIR = os.getcwd()

# Coletar todos os módulos do scipy e sklearn ANTES de criar o Analysis
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Coletar tudo do scipy (módulos, dados, binários)
scipy_datas, scipy_binaries, scipy_hiddenimports = collect_all('scipy')
sklearn_datas, sklearn_binaries, sklearn_hiddenimports = collect_all('sklearn')

# Combinar tudo
all_datas = [
    # Usar caminhos absolutos para garantir que sejam encontrados
    (os.path.join(ROOT_DIR, 'data'), 'data'),
    (os.path.join(ROOT_DIR, 'model_artifacts'), 'model_artifacts'),
    # Incluir scripts de atualização na raiz do diretório do .exe
    (os.path.join(ROOT_DIR, 'atualizar_database.py'), '.'),
    (os.path.join(ROOT_DIR, 'atualizar_apenas_2026.py'), '.'),
    # Garantir que o pacote core seja encontrado no .exe (evita ModuleNotFoundError: core.lol.prebets_player)
    (os.path.join(ROOT_DIR, 'src', 'core'), 'core'),
] + scipy_datas + sklearn_datas

all_binaries = scipy_binaries + sklearn_binaries

all_hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtWidgets',
    'PySide6.QtGui',
    'pandas',
    'numpy',
    'numpy._core',
    'numpy._core.multiarray',
    'numpy._core._multiarray_umath',
    'numpy._core._multiarray_tests',
    'numpy.core',
    'numpy.core.multiarray',
    'numpy.core._multiarray_umath',
    'numpy.core._multiarray_tests',
    'sklearn',
    'joblib',
    'sqlite3',
    'requests',
    'urllib3',
    # Módulos do projeto
    'src.load_and_predict_v3',
    'app.ui.main_window',
    'app.ui.pages.lol_prebets_secondary',
    'app.ui.pages.lol_prebets_player',
    'app.ui.pages.lol_draft',
    'app.ui.pages.lol_compare',
    'app.ui.pages.dota_prebets_secondary',
    'app.ui.pages.dota_draft',
    'app.ui.pages.database_update',
    'core.shared.paths',
    'core.shared.db',
    'core.shared.utils',
    'core.lol.draft',
    'core.lol.prebets_secondary',
    'core.lol.prebets_player',
    'core.lol.compare',
    'core.lol.db_converter',
    # Módulos Dota
    'core.dota.prebets_secondary',
    'core.dota.draft',
] + scipy_hiddenimports + sklearn_hiddenimports

# Coletar todos os submódulos de core.lol e core.dota
try:
    core_lol_submodules = collect_submodules('core.lol')
    all_hiddenimports.extend(core_lol_submodules)
    print(f"Coletados {len(core_lol_submodules)} submódulos de core.lol: {core_lol_submodules}")
except Exception as e:
    print(f"Aviso: Erro ao coletar submódulos de core.lol: {e}")

try:
    core_dota_submodules = collect_submodules('core.dota')
    all_hiddenimports.extend(core_dota_submodules)
    print(f"Coletados {len(core_dota_submodules)} submódulos de core.dota: {core_dota_submodules}")
except Exception as e:
    print(f"Aviso: Erro ao coletar submódulos de core.dota: {e}")

try:
    core_football_submodules = collect_submodules('core.football')
    all_hiddenimports.extend(core_football_submodules)
    print(f"Coletados {len(core_football_submodules)} submódulos de core.football: {core_football_submodules}")
except Exception as e:
    print(f"Aviso: Erro ao coletar submódulos de core.football: {e}")

# Coletar submódulos de app.ui.pages para garantir que todas as páginas sejam incluídas
try:
    app_pages_submodules = collect_submodules('app.ui.pages')
    all_hiddenimports.extend(app_pages_submodules)
    print(f"Coletados {len(app_pages_submodules)} submódulos de app.ui.pages: {app_pages_submodules}")
except Exception as e:
    print(f"Aviso: Erro ao coletar submódulos de app.ui.pages: {e}")

# Coletar submódulos críticos do numpy._core para pickle funcionar
try:
    numpy_core_submodules = collect_submodules('numpy._core')
    all_hiddenimports.extend(numpy_core_submodules)
    print(f"Coletados {len(numpy_core_submodules)} submódulos de numpy._core")
except Exception as e:
    print(f"Aviso: Erro ao coletar submódulos de numpy._core: {e}")

# Adicionar explicitamente o módulo db_converter
import sys
sys.path.insert(0, os.path.join(ROOT_DIR, 'src'))

a = Analysis(
    ['src/app/main.py', 'src/load_and_predict_v3.py'],
    pathex=['src', '.', os.path.join(ROOT_DIR, 'src')],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[ROOT_DIR],  # Adicionar diretório raiz para encontrar hooks
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

# Modo ONEDIR - cria uma pasta com o .exe e todos os arquivos
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
    console=False,
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
