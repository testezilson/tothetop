"""
Aplicação principal - LoL Oracle ML Desktop App
"""
import sys
import os

# Adicionar src ao path para imports funcionarem
# Isso é necessário tanto em desenvolvimento quanto no .exe
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# No PyInstaller, os módulos já estão no sys.path, mas precisamos garantir
# que o diretório src esteja acessível
if getattr(sys, 'frozen', False):
    # Executável PyInstaller (onedir ou onefile)
    BASE_DIR = os.path.dirname(sys.executable)
    # No onedir, o .exe pode estar na raiz ou em _internal; dados e "core" ficam em _internal
    _internal = os.path.join(BASE_DIR, '_internal')
    if os.path.isdir(_internal) and _internal not in sys.path:
        sys.path.insert(0, _internal)
    # Pasta que contém o .exe (onde está o pacote "core" se foi incluído como data)
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    # Fallback: src ao lado do .exe (se existir)
    SRC_DIR = os.path.normpath(os.path.join(BASE_DIR, 'src'))
    if os.path.exists(SRC_DIR) and SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
else:
    # Desenvolvimento - adicionar src/ ao path
    SRC_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', '..'))
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Importar explicitamente TODOS os módulos core que podem ser necessários
# Isso garante que o PyInstaller os inclua no executável
try:
    import core
    import core.lol
    import core.lol.db_converter
    import core.lol.prebets_secondary
    import core.lol.prebets_player
    import core.lol.prebets
    import core.lol.draft
    import core.lol.compare
    import core.lol.win_prob_early
    import core.lol.win_prob_full
    import core.lol.draft_prior
    import core.dota
    import core.dota.prebets_secondary
    import core.dota.draft
    import core.dota.draft_testezudo
    import core.shared.paths
    import core.shared.db
    import core.shared.utils
    # Importar páginas UI para garantir que sejam incluídas
    try:
        import app.ui.pages.dota_prebets_secondary
    except ImportError:
        pass
    try:
        import app.ui.pages.dota_draft
    except ImportError:
        pass
    try:
        import app.ui.pages.dota_draft_teste
    except ImportError:
        pass
    try:
        import app.ui.pages.database_update
    except ImportError:
        pass
    try:
        import app.ui.pages.lol_win_prob_unified
    except ImportError:
        pass
except ImportError as e:
    # Em desenvolvimento, isso pode falhar se o path não estiver configurado
    # Mas no executável PyInstaller, deve funcionar
    print(f"Aviso: Erro ao importar módulos core: {e}")

from app.ui.main_window import MainWindow


def main():
    """Função principal da aplicação."""
    app = QApplication(sys.argv)
    app.setApplicationName("LoL Oracle ML")
    app.setOrganizationName("LoL Oracle")
    
    # Criar e mostrar janela principal
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
