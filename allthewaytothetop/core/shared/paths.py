"""
Sistema de paths que funciona tanto em desenvolvimento quanto no .exe empacotado.
Este é o módulo mais crítico para o funcionamento do executável.
"""
import os
import sys


def get_base_dir():
    """
    Retorna o diretório base do aplicativo.
    Funciona tanto em desenvolvimento quanto quando empacotado com PyInstaller.
    """
    if getattr(sys, 'frozen', False):
        # Rodando como executável empacotado
        exe_dir = os.path.dirname(sys.executable)
        
        # No modo --onedir, o PyInstaller cria uma pasta _internal onde coloca os arquivos
        # No modo --onefile, os dados estão em _MEIPASS (diretório temporário)
        
        # Debug: imprimir informações
        print(f"[PATHS DEBUG] sys.executable: {sys.executable}")
        print(f"[PATHS DEBUG] exe_dir: {exe_dir}")
        
        # PRIORIDADE 1: _MEIPASS (modo onefile - dados extraídos temporariamente)
        if hasattr(sys, '_MEIPASS'):
            meipass_dir = sys._MEIPASS
            print(f"[PATHS DEBUG] _MEIPASS encontrado: {meipass_dir}")
            data_dir_meipass = os.path.join(meipass_dir, 'data')
            models_dir_meipass = os.path.join(meipass_dir, 'model_artifacts')
            print(f"[PATHS DEBUG] Verificando _MEIPASS: data={os.path.exists(data_dir_meipass)}, models={os.path.exists(models_dir_meipass)}")
            if os.path.exists(data_dir_meipass) and os.path.exists(models_dir_meipass):
                print(f"[PATHS DEBUG] Usando _MEIPASS: {meipass_dir}")
                return meipass_dir
        
        # PRIORIDADE 2: _internal (modo onedir - PyInstaller coloca arquivos aqui)
        internal_dir = os.path.join(exe_dir, '_internal')
        print(f"[PATHS DEBUG] Verificando _internal: {internal_dir}")
        print(f"[PATHS DEBUG] _internal existe: {os.path.exists(internal_dir)}")
        
        if os.path.exists(internal_dir):
            data_dir_internal = os.path.join(internal_dir, 'data')
            models_dir_internal = os.path.join(internal_dir, 'model_artifacts')
            print(f"[PATHS DEBUG] Verificando arquivos em _internal: data={os.path.exists(data_dir_internal)}, models={os.path.exists(models_dir_internal)}")
            if os.path.exists(data_dir_internal) and os.path.exists(models_dir_internal):
                print(f"[PATHS DEBUG] Usando _internal: {internal_dir}")
                return internal_dir
            # Se _internal existe mas não tem os arquivos, ainda assim usar (PyInstaller pode ter colocado em outro lugar)
            print(f"[PATHS DEBUG] _internal existe mas arquivos não encontrados, usando mesmo assim: {internal_dir}")
            return internal_dir
        
        # PRIORIDADE 3: Diretório do .exe (modo onedir com arquivos na mesma pasta)
        data_dir_exe = os.path.join(exe_dir, 'data')
        models_dir_exe = os.path.join(exe_dir, 'model_artifacts')
        print(f"[PATHS DEBUG] Verificando exe_dir: data={os.path.exists(data_dir_exe)}, models={os.path.exists(models_dir_exe)}")
        if os.path.exists(data_dir_exe) and os.path.exists(models_dir_exe):
            print(f"[PATHS DEBUG] Usando exe_dir: {exe_dir}")
            return exe_dir
        
        # PRIORIDADE 4: Pasta pai (caso .exe esteja em subpasta)
        parent_dir = os.path.dirname(exe_dir)
        data_dir_parent = os.path.join(parent_dir, 'data')
        models_dir_parent = os.path.join(parent_dir, 'model_artifacts')
        print(f"[PATHS DEBUG] Verificando parent_dir: data={os.path.exists(data_dir_parent)}, models={os.path.exists(models_dir_parent)}")
        if os.path.exists(data_dir_parent) and os.path.exists(models_dir_parent):
            print(f"[PATHS DEBUG] Usando parent_dir: {parent_dir}")
            return parent_dir
        
        # Fallback: usar _internal se existir (mesmo sem verificar arquivos)
        if os.path.exists(internal_dir):
            print(f"[PATHS DEBUG] Fallback: usando _internal: {internal_dir}")
            return internal_dir
        
        # Último fallback: usar diretório do .exe
        print(f"[PATHS DEBUG] Último fallback: usando exe_dir: {exe_dir}")
        return exe_dir
    else:
        # Cópia no backend web (allthewaytothetop/): shared -> core -> raiz do app
        # Projeto mãe (src/core/shared): 3x ..  ->  usamos 2x .. para base = allthewaytothetop
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        return base_dir


def get_data_dir():
    """
    Retorna o diretório onde estão os dados (data/).
    No .exe, os dados estarão na mesma pasta do executável.
    """
    base_dir = get_base_dir()
    data_dir = os.path.join(base_dir, 'data')
    
    # Criar se não existir (útil para histórico de apostas)
    os.makedirs(data_dir, exist_ok=True)
    
    return data_dir


def get_models_dir():
    """
    Retorna o diretório onde estão os modelos ML (model_artifacts/).
    """
    base_dir = get_base_dir()
    models_dir = os.path.join(base_dir, 'model_artifacts')
    return models_dir


def get_user_data_dir():
    """
    Retorna o diretório onde o app salva dados do usuário (histórico de apostas, etc.).
    Usa %APPDATA% no Windows.
    """
    if sys.platform == 'win32':
        appdata = os.getenv('APPDATA', os.path.expanduser('~'))
        user_dir = os.path.join(appdata, 'LoLOracleML')
    else:
        # Linux/Mac
        user_dir = os.path.join(os.path.expanduser('~'), '.lol_oracle_ml')
    
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def get_lol_db2026_dir():
    """
    Pasta padrão do CSV / SQLite LoL (Oracle's Elixir).
    Pode ser sobrescrita pelo ambiente (LOL_DB2026_DIR) para testes.
    """
    override = os.environ.get("LOL_DB2026_DIR", "").strip()
    if override and os.path.isdir(override):
        return os.path.normpath(override)
    return os.path.join(os.path.expanduser("~"), "Documents", "db2026")


def get_lol_db_path():
    """
    Retorna o caminho do banco LoL (lol_esports.db).

    Se existir a pasta ``Documents/db2026`` (mesma do CSV do Oracle's Elixir),
    o caminho canónico é *sempre* ``<essa pasta>/lol_esports.db`` — mesmo que o
    ficheiro ainda não exista (será criado por 'Atualizar Banco' / ensure_db_exists).
    Isto evita que um .db antigo em ``data/`` ou em ``dist/`` fique à frente do CSV atualizado.
    """
    db2026 = get_lol_db2026_dir()
    if os.path.isdir(db2026):
        return os.path.join(db2026, "lol_esports.db")

    possible = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        if "_internal" in exe_dir:
            possible.append(os.path.join(os.path.dirname(exe_dir), "lol_esports.db"))
        possible.append(os.path.join(exe_dir, "lol_esports.db"))
    if not getattr(sys, "frozen", False):
        try:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            dist_db = os.path.join(base, "dist", "LoLOracleML", "lol_esports.db")
            if os.path.exists(dist_db):
                possible.append(dist_db)
        except Exception:
            pass
    # Legado (caminho absoluto antigo) — mantido para máquinas sem Documents/db2026
    possible.extend(
        [
            os.path.join(db2026, "lol_esports.db"),
            os.path.join(db2026, "oracle_2026.db"),
            os.path.join(db2026, "oracle.db"),
        ]
    )
    possible.extend(
        [
            os.path.join(r"C:\Users\Lucas\Documents", "oracle_2025.db"),
            os.path.join(r"C:\Users\Lucas\lol\data", "lol_esports.db"),
        ]
    )
    data_dir = get_data_dir()
    possible.extend(
        [
            os.path.join(data_dir, "lol_esports.db"),
            os.path.join(data_dir, "oracle_2026.db"),
            os.path.join(data_dir, "oracle_2025.db"),
            os.path.join(data_dir, "oracle.db"),
        ]
    )
    for p in possible:
        if os.path.exists(p):
            return p
    return None


def path_in_data(filename):
    """
    Retorna o caminho completo de um arquivo dentro de data/.
    
    Exemplo:
        path_in_data("oracle_prepared.csv")
        -> "C:/Users/Lucas/Documents/lol_oracle_ml_v3/data/oracle_prepared.csv"
    """
    return os.path.join(get_data_dir(), filename)


def path_in_models(filename):
    """
    Retorna o caminho completo de um arquivo dentro de model_artifacts/.
    """
    return os.path.join(get_models_dir(), filename)


def path_in_user_data(filename):
    """
    Retorna o caminho completo de um arquivo dentro do diretório de dados do usuário.
    """
    return os.path.join(get_user_data_dir(), filename)


def get_football_api_key():
    """
    Chave API-Sports (API-Football v3: v3.football.api-sports.io).
    Ordem: variável de ambiente FOOTBALL_API_KEY (ou APISPORTS_KEY) →
    ficheiro data/football_api_key.txt (uma linha, sem aspas).
    Nunca comitar a chave no repositório.
    """
    for env_name in ("FOOTBALL_API_KEY", "APISPORTS_KEY", "X_APISPORTS_KEY"):
        v = os.environ.get(env_name, "").strip()
        if v:
            return v
    p = path_in_data("football_api_key.txt")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                line = (f.read() or "").strip().splitlines()
                if line:
                    return line[0].strip()
        except OSError:
            pass
    return ""


# Caminhos principais (para facilitar importação)
BASE_DIR = get_base_dir()
DATA_DIR = get_data_dir()
MODELS_DIR = get_models_dir()
USER_DATA_DIR = get_user_data_dir()
