"""
Win rate dos times que pegam first drake, first tower e first herald.
Por padrão pergunta quais ligas analisar; em branco = todas.
"""
import os
import sys
import sqlite3
import pandas as pd

# Evitar erro de encoding ao criar banco (db_converter usa emojis no print)
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ligas Major (sugestão quando usuário pede ajuda)
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}

# Raiz do projeto (pasta onde está este script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _find_csv_in_data_dir():
    """Procura o CSV do Oracle na pasta data/. Prefere o bruto do Oracle's Elixir (tem gameid, firstdragon, etc.)."""
    if not os.path.isdir(DATA_DIR):
        return None
    # Preferir CSV bruto do Oracle's Elixir (ex: 2026_LoL_esports_match_data_from_OraclesElixir.csv)
    raw_candidates = []
    other_candidates = []
    for f in os.listdir(DATA_DIR):
        if not f.endswith(".csv"):
            continue
        path = os.path.join(DATA_DIR, f)
        mtime = os.path.getmtime(path)
        if "OraclesElixir" in f or ("LoL_esports" in f and "match_data" in f):
            raw_candidates.append((path, mtime))
        elif "LoL_esports" in f or "2026" in f:
            other_candidates.append((path, mtime))
    for lst in (raw_candidates, other_candidates):
        if lst:
            lst.sort(key=lambda x: x[1], reverse=True)
            return lst[0][0]
    return None


def get_db_path():
    """
    Retorna o caminho do banco, usando a MESMA lógica das análises pré-secondary
    (db2026, oracle_2025, lol/data, data do projeto, etc.).
    Assim os números batem com as 130 partidas LPL que você vê nas estatísticas por liga.
    """
    # Mesma ordem de prioridade que core.lol.prebets_secondary.get_db_path()
    possible_paths = [
        r"C:\Users\Lucas\Documents\db2026\lol_esports.db",
        r"C:\Users\Lucas\Documents\db2026\oracle_2026.db",
        r"C:\Users\Lucas\Documents\db2026\oracle.db",
        r"C:\Users\Lucas\Documents\oracle_2025.db",
        r"C:\Users\Lucas\lol\data\lol_esports.db",
    ]
    try:
        from core.shared.paths import get_data_dir
        data_dir = get_data_dir()
    except Exception:
        data_dir = DATA_DIR
    possible_paths.extend([
        os.path.join(data_dir, "lol_esports.db"),
        os.path.join(data_dir, "oracle_2026.db"),
        os.path.join(data_dir, "oracle_2025.db"),
        os.path.join(data_dir, "oracle.db"),
        os.path.join(DATA_DIR, "lol_esports.db"),
    ])
    for path in possible_paths:
        if os.path.exists(path):
            return path
    # Fallback: criar a partir do CSV na pasta data/ do projeto
    csv_path = _find_csv_in_data_dir()
    data_db = os.path.join(DATA_DIR, "lol_esports.db")
    if csv_path:
        try:
            from core.lol.db_converter import create_oracle_db_from_csv
            print(f"Criando banco a partir do CSV: {os.path.basename(csv_path)}")
            create_oracle_db_from_csv(csv_path, data_db)
            if os.path.exists(data_db):
                return data_db
        except Exception as e:
            print(f"Aviso: não foi possível criar o banco: {e}")
    return None


def load_df_from_csv(csv_path, leagues=None):
    """Carrega do CSV do Oracle's Elixir: uma linha por (gameid, team) com result e first*.
    leagues: set/list de ligas ou None = todas."""
    df_raw = pd.read_csv(csv_path, low_memory=False)
    df_raw.columns = df_raw.columns.str.strip().str.lower()
    if leagues is not None:
        df_raw = df_raw[df_raw["league"].isin(leagues)]
    if df_raw.empty:
        return df_raw
    needed = ["gameid", "teamname", "league", "result", "firstdragon", "firsttower", "firstherald"]
    missing = [c for c in needed if c not in df_raw.columns]
    if missing:
        return pd.DataFrame()
    # Por (gameid, teamname) há 5 linhas (jogadores); first* pode estar só em algumas. Agregar com max.
    agg = {
        "league": "first",
        "result": "first",
        "firstdragon": "max",
        "firsttower": "max",
        "firstherald": "max",
    }
    df = df_raw[needed].groupby(["gameid", "teamname"], as_index=False).agg(agg)
    df = df.rename(columns={"teamname": "team"})
    res = df["result"].astype(str).str.lower()
    df["result"] = (res.isin(["1", "true", "win", "w"])).astype(int)
    return df


def _parse_leagues_input(text):
    """Interpreta o input do usuário: em branco = None (todas), senão set de ligas."""
    t = (text or "").strip()
    if not t:
        return None
    return {x.strip().upper() for x in t.split(",") if x.strip()}


def main():
    # Garantir que imports do projeto (core.*) funcionem
    if os.path.exists(os.path.join(BASE_DIR, "src")):
        src_path = os.path.join(BASE_DIR, "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

    # Input de ligas: em branco = todas (pode vir do argumento ou do prompt)
    if len(sys.argv) > 1:
        raw = sys.argv[1].strip()
    else:
        try:
            prompt = "Ligas (separadas por vírgula; em branco = todas). Ex: LCK,LPL,LEC ou MAJOR: "
            raw = input(prompt).strip()
        except EOFError:
            raw = ""
    if raw.upper() == "MAJOR":
        leagues = MAJOR_LEAGUES
    else:
        leagues = _parse_leagues_input(raw)

    db_path = get_db_path()
    if db_path:
        print(f"Banco: {db_path}\n")
    df = None
    if db_path:
        conn = sqlite3.connect(db_path)
        try:
            if leagues is None:
                query = """
                    SELECT gameid, team, league, result, firstdragon, firsttower, firstherald
                    FROM oracle_matches
                    WHERE result IS NOT NULL
                    GROUP BY gameid, team
                """
                df = pd.read_sql_query(query, conn)
            else:
                placeholders = ",".join("?" for _ in leagues)
                query = f"""
                    SELECT gameid, team, league, result, firstdragon, firsttower, firstherald
                    FROM oracle_matches
                    WHERE league IN ({placeholders}) AND result IS NOT NULL
                    GROUP BY gameid, team
                """
                df = pd.read_sql_query(query, conn, params=list(leagues))
        except sqlite3.OperationalError as e:
            if "no such column" in str(e).lower() or "firstdragon" in str(e).lower():
                df = None
            else:
                raise
        conn.close()
    if df is None or df.empty:
        csv_path = _find_csv_in_data_dir()
        if csv_path:
            print(f"Usando CSV diretamente: {os.path.basename(csv_path)}")
            df = load_df_from_csv(csv_path, leagues=leagues)
    if df is None or df.empty:
        print("Nenhum dado encontrado para as ligas informadas.")
        print("  Coloque um CSV do Oracle's Elixir (ex: 2026_LoL_esports_...) na pasta data/")
        return

    # Se o banco não tem firstdragon/firsttower/firstherald preenchidos, usar CSV para esses objetivos
    first_cols = ["firstdragon", "firsttower", "firstherald"]
    db_has_first = all(
        col in df.columns and pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int).eq(1).any()
        for col in first_cols
    )
    if not db_has_first and df is not None and not df.empty:
        csv_path = _find_csv_in_data_dir()
        if csv_path:
            df_csv = load_df_from_csv(csv_path, leagues=leagues)
            if not df_csv.empty and any(
                pd.to_numeric(df_csv.get(c, pd.Series([0])), errors="coerce").fillna(0).astype(int).eq(1).any()
                for c in first_cols if c in df_csv.columns
            ):
                print("Banco não tem dados de first drake/tower/herald; usando CSV para esses objetivos.\n")
                df = df_csv

    if leagues is None:
        leagues_label = sorted(df["league"].unique().tolist())
    else:
        leagues_label = sorted(leagues)
    n_games = len(df)
    print("=" * 60)
    print("WIN RATE - QUEM PEGA FIRST OBJETIVO")
    print("=" * 60)
    print(f"Ligas: {', '.join(leagues_label)}")
    print(f"Total de registros (uma por time por jogo): {n_games}")
    print(f"Partidas únicas: {df['gameid'].nunique()}")
    print()

    # First drake = firstdragon (no LoL é "dragon", primeiro dragão = first drake)
    # First tower = firsttower (torre = tower = turret, mesmo conceito)
    objectives = [
        ("First Drake", "firstdragon"),
        ("First Tower", "firsttower"),
        ("First Herald", "firstherald"),
    ]

    for label, col in objectives:
        if col not in df.columns:
            print(f"{label}: coluna '{col}' ausente.")
            continue
        # Garantir numérico (CSV pode vir 1.0/0.0)
        serie = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        got_it = df.loc[serie == 1]
        if len(got_it) == 0:
            print(f"{label}: sem dados (nenhum time pegou esse objetivo).")
            continue
        total = len(got_it)
        if total == 0:
            print(f"{label}: 0 jogos (nenhum time pegou esse objetivo nos dados).")
            continue
        wins = got_it["result"].sum()
        wr = wins / total if total else 0
        print(f"{label}:")
        print(f"  Jogos em que o time pegou: {total}")
        print(f"  Vitórias: {int(wins)}")
        print(f"  Win rate: {wr * 100:.2f}%")
        print()

    print("=" * 60)


if __name__ == "__main__":
    main()
