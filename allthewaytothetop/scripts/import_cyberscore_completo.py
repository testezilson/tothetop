"""
Script completo e automatizado para importar e corrigir dados do CyberScore.

Uso:
    python import_cyberscore_completo.py <team_id>
"""

import os
import sys
import time
import re
import sqlite3
from datetime import datetime, timedelta

# Permite "from scrap_match_cyberscore_sel" quando o cwd não é allthewaytothetop/scripts
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from selenium import webdriver
from selenium.webdriver.common.by import By

from scrap_match_cyberscore_sel import build_chrome_options, scrap_match_page

_DEFAULT_DB = os.path.join(
    os.path.normpath(os.path.join(_SCRIPTS_DIR, "..")),
    "data",
    "cyberscore.db",
)
DB_PATH = os.path.normpath(
    os.path.abspath(
        os.environ.get("CYBERSCORE_DB_PATH", _DEFAULT_DB),
    )
)

# Partidas problemáticas que devem ser sempre excluídas
BLACKLISTED_MATCH_IDS = ["152127", "154190", "154275", "160532", "160633"]


def remove_blacklisted_matches():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    placeholders = ",".join("?" * len(BLACKLISTED_MATCH_IDS))
    cur.execute(f"DELETE FROM matches WHERE match_id IN ({placeholders})", BLACKLISTED_MATCH_IDS)

    deleted = cur.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        print(f"  🗑️  Removidas {deleted} partidas da blacklist: {', '.join(BLACKLISTED_MATCH_IDS)}")

    return deleted


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(matches)")
    existing_columns = {row[1] for row in cur.fetchall()}

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            team_radiant TEXT,
            team_dire TEXT,
            radiant_team TEXT,
            dire_team TEXT,
            score_radiant INTEGER,
            score_dire INTEGER,
            duration TEXT,
            kills_radiant INTEGER,
            kills_dire INTEGER,
            kills_total INTEGER,
            total_kills INTEGER,
            date TEXT,
            match_date TEXT,
            match_url TEXT,
            timestamp INTEGER,
            match_timestamp INTEGER,
            map_kills_text TEXT
        )
        """
    )

    columns_to_add = {
        "radiant_team": "TEXT",
        "dire_team": "TEXT",
        "total_kills": "INTEGER",
        "match_date": "TEXT",
        "match_timestamp": "INTEGER",
        "map_kills_text": "TEXT",
    }

    for col, col_type in columns_to_add.items():
        if col not in existing_columns:
            try:
                cur.execute(f"ALTER TABLE matches ADD COLUMN {col} {col_type}")
                print(f"  ✓ Adicionada coluna: {col}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()


def sync_columns():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        UPDATE matches SET radiant_team = team_radiant
        WHERE (radiant_team IS NULL OR radiant_team = '') AND team_radiant IS NOT NULL
    """)
    cur.execute("""
        UPDATE matches SET team_radiant = radiant_team
        WHERE (team_radiant IS NULL OR team_radiant = '') AND radiant_team IS NOT NULL
    """)

    cur.execute("""
        UPDATE matches SET dire_team = team_dire
        WHERE (dire_team IS NULL OR dire_team = '') AND team_dire IS NOT NULL
    """)
    cur.execute("""
        UPDATE matches SET team_dire = dire_team
        WHERE (team_dire IS NULL OR team_dire = '') AND dire_team IS NOT NULL
    """)

    cur.execute("""
        UPDATE matches SET total_kills = kills_total
        WHERE total_kills IS NULL AND kills_total IS NOT NULL
    """)
    cur.execute("""
        UPDATE matches SET kills_total = total_kills
        WHERE kills_total IS NULL AND total_kills IS NOT NULL
    """)

    cur.execute("""
        UPDATE matches SET match_date = date
        WHERE (match_date IS NULL OR match_date = '') AND date IS NOT NULL
    """)
    cur.execute("""
        UPDATE matches SET date = match_date
        WHERE (date IS NULL OR date = '') AND match_date IS NOT NULL
    """)

    cur.execute("""
        UPDATE matches SET match_timestamp = timestamp
        WHERE match_timestamp IS NULL AND timestamp IS NOT NULL
    """)
    cur.execute("""
        UPDATE matches SET timestamp = match_timestamp
        WHERE timestamp IS NULL AND match_timestamp IS NOT NULL
    """)

    conn.commit()
    conn.close()


def extract_match_id(url: str):
    m = re.search(r"/matches/(\d+)/?$", url)
    return m.group(1) if m else None


def parse_cyberscore_date(raw_date: str):
    """
    Retorna:
      (timestamp:int|None, nice_str:"DD.MM.YY at HH:MM"|None)

    IMPORTANTE:
      Se raw_date vier None/vazio -> NÃO inventa timestamp.
    """
    now = datetime.now()

    if not raw_date:
        return None, None

    raw_date = raw_date.strip()

    # Today at HH:MM
    m = re.match(r"Today at (\d{1,2}):(\d{2})", raw_date, re.IGNORECASE)
    if m:
        hh, mm = map(int, m.groups())
        dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return int(dt.timestamp()), dt.strftime("%d.%m.%y at %H:%M")

    # Yesterday at HH:MM
    m = re.match(r"Yesterday at (\d{1,2}):(\d{2})", raw_date, re.IGNORECASE)
    if m:
        hh, mm = map(int, m.groups())
        dt = (now - timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        return int(dt.timestamp()), dt.strftime("%d.%m.%y at %H:%M")

    # Tomorrow at HH:MM (raríssimo, mas cobre)
    m = re.match(r"Tomorrow at (\d{1,2}):(\d{2})", raw_date, re.IGNORECASE)
    if m:
        hh, mm = map(int, m.groups())
        dt = (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        return int(dt.timestamp()), dt.strftime("%d.%m.%y at %H:%M")

    # Formato normal: "DD.MM.YY at HH:MM"
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2}) at (\d{2}):(\d{2})", raw_date)
    if m:
        dd, mm, yy, hh, mi = map(int, m.groups())
        year = 2000 + yy
        dt = datetime(year, mm, dd, hh, mi)
        return int(dt.timestamp()), raw_date

    # Se nada bater, não inventa timestamp
    return None, raw_date


def get_page1_links(team_id):
    url = f"https://cyberscore.live/en/teams/{team_id}/matches?page=1"

    options = build_chrome_options()
    if os.environ.get("SELENIUM_HEADLESS", "1") != "1" and not os.environ.get("RAILWAY_ENVIRONMENT"):
        try:
            options.add_argument("--start-maximized")
        except Exception:
            pass
    driver = webdriver.Chrome(options=options)

    print(f"\n🌐 Abrindo: {url}")
    driver.get(url)
    time.sleep(4)

    for _ in range(6):
        driver.execute_script("window.scrollBy(0, 1500);")
        time.sleep(0.7)

    raw_links = []
    for e in driver.find_elements(By.TAG_NAME, "a"):
        href = e.get_attribute("href")
        if href and re.search(r"/matches/\d+/?$", href):
            raw_links.append(href)

    driver.quit()

    links = list(set(raw_links))
    print(f"🔗 Partidas válidas encontradas: {len(links)}")
    return links


def match_exists_and_complete(match_id: str) -> bool:
    """
    Verifica se a partida já existe no banco.
    Se existe, considera completa e pula a extração.
    Verifica match_id como texto (padrão) e como número (fallback).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Verifica se a partida existe (match_id é TEXT no banco, mas verifica ambos formatos)
    # Tenta como texto primeiro (formato padrão do schema)
    cur.execute("SELECT COUNT(*) FROM matches WHERE match_id = ?", (match_id,))
    count = cur.fetchone()[0]
    
    # Se não encontrou como texto, tenta como número (caso alguém tenha inserido como INTEGER)
    if count == 0:
        try:
            match_id_int = int(match_id)
            cur.execute("SELECT COUNT(*) FROM matches WHERE match_id = ?", (match_id_int,))
            count = cur.fetchone()[0]
        except (ValueError, sqlite3.OperationalError):
            # Se match_id não é numérico ou erro ao converter, ignora
            pass
    
    conn.close()
    return count > 0


def insert_match(match_data, url):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    match_id = extract_match_id(url)
    raw_date = match_data.get("date")

    ts, nice_date = parse_cyberscore_date(raw_date)
    final_date = nice_date if nice_date is not None else raw_date

    cur.execute(
        """
        INSERT OR REPLACE INTO matches
        (match_id, team_radiant, team_dire, radiant_team, dire_team,
         score_radiant, score_dire, duration,
         kills_radiant, kills_dire, kills_total, total_kills,
         date, match_date, match_url, timestamp, match_timestamp, map_kills_text)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            match_id,
            match_data.get("team_radiant"),
            match_data.get("team_dire"),
            match_data.get("team_radiant"),
            match_data.get("team_dire"),
            match_data.get("score_radiant"),
            match_data.get("score_dire"),
            match_data.get("duration"),
            match_data.get("kills_radiant"),
            match_data.get("kills_dire"),
            match_data.get("kills_total"),
            match_data.get("kills_total"),
            final_date,
            final_date,
            url,
            ts,
            ts,
            match_data.get("map_kills_text"),
        ),
    )

    conn.commit()
    conn.close()


def fix_broken_matches(match_ids=None):
    """
    Reextrai partidas com dados ESSENCIAIS faltando.
    Considera quebrada apenas se faltar: times OU kills.
    Campos opcionais como duration, date não são considerados "quebrados".
    
    Se match_ids for fornecido, corrige apenas essas partidas específicas.
    Caso contrário, corrige todas as partidas quebradas (comportamento antigo).
    
    Args:
        match_ids: Lista de match_ids para corrigir. Se None, corrige todas.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(matches)")
    columns = {row[1] for row in cur.fetchall()}

    # Campos ESSENCIAIS: só considera quebrada se faltar DADOS CRÍTICOS
    # Quebrada = falta AMBOS os times OU falta AMBOS os kills
    # Campos opcionais como duration, date, map_kills_text NÃO contam como quebrados
    
    essential_conditions = []
    
    # Condição 1: Faltam ambos os times (radiant E dire)
    time_parts = []
    if "team_radiant" in columns:
        time_parts.append("(team_radiant IS NULL OR team_radiant = '')")
    elif "radiant_team" in columns:
        time_parts.append("(radiant_team IS NULL OR radiant_team = '')")
    
    if "team_dire" in columns:
        time_parts.append("(team_dire IS NULL OR team_dire = '')")
    elif "dire_team" in columns:
        time_parts.append("(dire_team IS NULL OR dire_team = '')")
    
    if len(time_parts) == 2:
        essential_conditions.append(f"({time_parts[0]} AND {time_parts[1]})")
    
    # Condição 2: Faltam ambos os kills (radiant E dire)
    if "kills_radiant" in columns and "kills_dire" in columns:
        essential_conditions.append("(kills_radiant IS NULL AND kills_dire IS NULL)")
    
    if not essential_conditions:
        conn.close()
        return 0
    
    # Quebrada se: faltar ambos os times OU faltar ambos os kills
    conditions_query = " OR ".join(essential_conditions)

    placeholders_blacklist = ",".join("?" * len(BLACKLISTED_MATCH_IDS))
    
    # Se match_ids foi fornecido, filtra apenas essas partidas
    if match_ids:
        placeholders_matches = ",".join("?" * len(match_ids))
        query = f"""
            SELECT DISTINCT match_id, COALESCE(match_url, '') as url
            FROM matches
            WHERE match_id IN ({placeholders_matches})
            AND ({conditions_query})
            AND match_id NOT IN ({placeholders_blacklist})
        """
        params = tuple(match_ids) + tuple(BLACKLISTED_MATCH_IDS)
    else:
        # Comportamento antigo: corrige todas as partidas quebradas
        query = f"""
            SELECT DISTINCT match_id, COALESCE(match_url, '') as url
            FROM matches
            WHERE ({conditions_query})
            AND match_id NOT IN ({placeholders_blacklist})
        """
        params = BLACKLISTED_MATCH_IDS

    cur.execute(query, params)
    broken = cur.fetchall()
    conn.close()

    if not broken:
        return 0

    print(f"\n🔧 Corrigindo {len(broken)} partidas quebradas.")
    fixed = 0

    for match_id, url in broken:
        if not url or url.strip() == "":
            url = f"https://cyberscore.live/en/matches/{match_id}/"

        print(f"  🔄 Reextraindo {match_id}.")
        try:
            match_data = scrap_match_page(url)
            if match_data and match_data.get("team_radiant") and match_data.get("map_kills"):
                insert_match(match_data, url)
                fixed += 1
                print("    ✓ Corrigido!")
            else:
                print("    ✗ Falhou ao reextrair (dados incompletos)")

            time.sleep(1.5)
        except Exception as e:
            print(f"    ✗ Erro: {e}")

    return fixed


def fill_missing_timestamps():
    """
    Só tenta preencher timestamp quando existir date parseável.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT match_id, COALESCE(date, match_date) as date_str
        FROM matches
        WHERE (timestamp IS NULL OR match_timestamp IS NULL)
          AND (date IS NOT NULL OR match_date IS NOT NULL)
    """)
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return 0

    print(f"\n⏰ Preenchendo {len(rows)} timestamps faltantes.")
    filled = 0

    for match_id, date_str in rows:
        if not date_str:
            continue

        # tenta parse direto no formato normalizado
        try:
            dt = datetime.strptime(date_str, "%d.%m.%y at %H:%M")
            ts = int(dt.timestamp())
        except:
            ts, _ = parse_cyberscore_date(date_str)

        if ts is None:
            continue

        cur.execute("""
            UPDATE matches
            SET timestamp = ?, match_timestamp = ?
            WHERE match_id = ?
        """, (ts, ts, match_id))
        filled += 1

    conn.commit()
    conn.close()
    return filled


def main():
    if len(sys.argv) < 2:
        print("Uso: python import_cyberscore_completo.py <team_id>")
        return

    global DB_PATH
    DB_PATH = os.path.normpath(
        os.path.abspath(
            os.environ.get("CYBERSCORE_DB_PATH", _DEFAULT_DB),
        )
    )
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)

    team_id = sys.argv[1]

    print("\n============================================================")
    print("ETAPA 0/4: Preparando banco")
    print("============================================================")
    init_db()
    remove_blacklisted_matches()

    print("\n============================================================")
    print("ETAPA 1/4: Coletando links da página 1")
    print("============================================================")
    links = get_page1_links(team_id)

    print("\n🟦 Processando partidas...\n")
    processed_match_ids = []
    skipped_count = 0
    inserted_count = 0
    
    for url in links:
        match_id = extract_match_id(url)
        if not match_id:
            continue
            
        # Verifica se a partida já existe e está completa
        exists = match_exists_and_complete(match_id)
        if exists:
            print(f"⏭️  Partida já existe e está completa → {url} (ID: {match_id})")
            skipped_count += 1
            processed_match_ids.append(match_id)  # Inclui mesmo as completas para correção se necessário
            continue
        
        print(f"📥 Nova partida → {url} (ID: {match_id})")
        try:
            match_data = scrap_match_page(url)
            if match_data and match_data.get("team_radiant") and match_data.get("map_kills"):
                insert_match(match_data, url)
                inserted_count += 1
                print("   ✅ Inserida/atualizada\n")
            else:
                print("   ❌ Falhou ao extrair dados\n")
            processed_match_ids.append(match_id)
            time.sleep(1.2)
        except Exception as e:
            print(f"   ❌ Erro: {e}\n")
            processed_match_ids.append(match_id)  # Inclui para tentar corrigir depois
    
    print(f"\n📊 Resumo da ETAPA 1:")
    print(f"   ✅ Inseridas/atualizadas: {inserted_count}")
    print(f"   ⏭️  Puladas (já existentes): {skipped_count}")
    print(f"   📋 Total processadas: {len(processed_match_ids)}")

    print("\n============================================================")
    print("ETAPA 2/4: Corrigindo partidas quebradas")
    print("============================================================")
    # Corrige apenas as partidas processadas nesta execução
    fix_broken_matches(processed_match_ids if processed_match_ids else None)

    print("\n============================================================")
    print("ETAPA 3/4: Sincronizando colunas e timestamps")
    print("============================================================")
    sync_columns()
    fill_missing_timestamps()

    print("\n✅ Import completo finalizado!")


if __name__ == "__main__":
    main()
