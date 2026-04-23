"""
PyInstaller hook para core.lol.db_converter
Garante que o módulo seja incluído no executável.
"""
from PyInstaller.utils.hooks import collect_all

# Coletar o módulo e todas as suas dependências
datas, binaries, hiddenimports = collect_all('core.lol.db_converter')
