"""
Módulo para converter CSV do Oracle para banco SQLite.
Cria/atualiza o banco de dados a partir do CSV mais recente.
"""
import sqlite3
import pandas as pd
import os
from pathlib import Path
from core.shared.paths import get_data_dir, get_lol_db2026_dir


def _oracle_csv_candidates_in_dir(directory):
    """
    (path, mtime) de CSVs usáveis para montar o SQLite (Oracle's Elixir / match data).
    Exclui oracle_prepared.csv (só rascunho/picks, sem linhas position=team/dragons).
    """
    if not directory or not os.path.exists(directory):
        return []
    out = []
    try:
        for name in os.listdir(directory):
            if not str(name).lower().endswith(".csv"):
                continue
            if "oracle_prepared" in name.lower():
                continue
            # Mesmo critério flexível de antes, mas sem o CSV agregado do projeto
            if not (
                "LoL_esports" in name
                or "lol_esports" in name.lower()
                or "oracle" in name.lower()
                or "2026" in name
            ):
                continue
            fp = os.path.join(directory, name)
            if os.path.isfile(fp):
                out.append((fp, os.path.getmtime(fp)))
    except OSError:
        return []
    return out


def find_latest_csv():
    r"""
    Encontra o CSV mais recente para o banco LoL.
    Padrão (desktop): .exe (empacotado) > ``Documents/db2026`` > ``data/`` do projeto.

    No Railway / Docker use ``data/`` commitado antes de qualquer outra coisa, para
    bater com o ficheiro versionado: defina ``RAILWAY_ENVIRONMENT`` (Railway cria) ou
    ``ORACLE_CSV_PREFER_APP_DATA=1``.

    Override absoluto: ``ORACLE_CSV`` ou ``LOL_ELIXIR_CSV`` = caminho completo a um
    ficheiro .csv (o mesmo do seu db2026 / projeto mãe, se quiser n iguais).

    Nunca usa ``oracle_prepared.csv`` (não contém objectivos agregados por jogo).
    """
    import sys

    def _pick_newest(tuples_list):
        if not tuples_list:
            return None
        tuples_list.sort(key=lambda x: x[1], reverse=True)
        return tuples_list[0][0]

    def _from_data_dir():
        return _pick_newest(_oracle_csv_candidates_in_dir(get_data_dir()))

    def _from_db2026_dir():
        db2026_dir = get_lol_db2026_dir()
        if not os.path.isdir(db2026_dir):
            return None
        return _pick_newest(_oracle_csv_candidates_in_dir(db2026_dir))

    # 0) Caminho forçado (recomendado no Railway: ficheiro em /app/data/...)
    for key in ("ORACLE_CSV", "LOL_ELIXIR_CSV"):
        p = (os.environ.get(key) or "").strip()
        if p and os.path.isfile(p):
            return p

    # 1) Empacotado: pastas do .exe
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        folders = [os.path.dirname(exe_dir), exe_dir] if "_internal" in exe_dir else [exe_dir]
        for folder in folders:
            if folder and os.path.exists(folder):
                c = _oracle_csv_candidates_in_dir(folder)
                p = _pick_newest(c)
                if p:
                    return p

    prefer_app_data = (os.environ.get("ORACLE_CSV_PREFER_APP_DATA", "") or "").lower() in (
        "1",
        "true",
        "yes",
    ) or bool((os.environ.get("RAILWAY_ENVIRONMENT") or "").strip())

    if prefer_app_data:
        p = _from_data_dir() or _from_db2026_dir()
    else:
        p = _from_db2026_dir() or _from_data_dir()
    if p:
        return p
    return None


def create_oracle_db_from_csv(csv_path, db_path):
    """
    Cria/atualiza banco SQLite a partir do CSV do Oracle.
    
    Args:
        csv_path: Caminho do CSV
        db_path: Caminho do banco SQLite a ser criado/atualizado
    """
    print(f"[CSV] Carregando: {csv_path}")
    print(f"[DB] Gravando em: {db_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    
    # Normalizar nomes das colunas
    df.columns = df.columns.str.strip().str.lower()
    # Mostrar periodo dos dados (para o usuario saber se o CSV esta desatualizado)
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce").dropna()
        if len(dates) > 0:
            print(f"   Periodo do CSV: {dates.min()} a {dates.max()}")
            print("   (Se os ultimos jogos estao antigos, baixe o CSV mais recente do Oracle's Elixir.)")
    
    # Criar conexão com banco
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Criar tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oracle_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            gameid TEXT,
            league TEXT,
            team TEXT,
            teamname TEXT,
            opponent TEXT,
            result INTEGER,
            teamkills INTEGER,
            teamdeaths INTEGER,
            teamassists INTEGER,
            opponentkills INTEGER,
            opponentdeaths INTEGER,
            opponentassists INTEGER,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            playername TEXT,
            champion TEXT,
            position TEXT,
            dragons INTEGER,
            opp_dragons INTEGER,
            barons INTEGER,
            opp_barons INTEGER,
            towers INTEGER,
            opp_towers INTEGER,
            firstdragon INTEGER,
            firsttower INTEGER,
            firstherald INTEGER,
            gamelength REAL,
            totalgold INTEGER,
            teamgold INTEGER,
            opponentgold INTEGER,
            golddiff INTEGER,
            xpdiff INTEGER,
            cs INTEGER,
            gold REAL,
            UNIQUE(date, gameid, team, playername)
        )
    """)
    
    # Migração: adicionar colunas se não existirem (para bancos antigos)
    cursor.execute("PRAGMA table_info(oracle_matches)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    for col in (
        'teamname', 'firstdragon', 'firsttower', 'firstherald',
        'opp_dragons', 'opp_barons', 'opp_towers',
        'opponentkills', 'opponentdeaths', 'opponentassists'
    ):
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE oracle_matches ADD COLUMN {col} INTEGER")
                print(f"   Migração: coluna {col} adicionada.")
            except sqlite3.OperationalError:
                pass
    
    # SEMPRE limpar dados antigos antes de inserir novos (modo REPLACE)
    print("Limpando dados antigos (modo REPLACE)...")
    cursor.execute("DELETE FROM oracle_matches")
    conn.commit()
    
    print("Processando dados...")
    
    # No CSV Oracle's Elixir, towers/dragons/barons (e às vezes firstdragon, gamelength) vêm só nas linhas position='team'.
    # Montar lookup (gameid, teamname) -> valores da linha team para preencher nas linhas de jogador.
    team_rows = df[df['position'].astype(str).str.strip().str.lower() == 'team']
    team_lookup = {}
    # Por jogo: lista de (teamname, teamkills, teamdeaths, teamassists) para montar opponentkills
    game_teams = {}
    for _, trow in team_rows.iterrows():
        gid = trow.get('gameid')
        tname = trow.get('teamname') if pd.notna(trow.get('teamname')) else trow.get('team', None)
        if gid is None or pd.isna(gid) or tname is None or (isinstance(tname, float) and pd.isna(tname)):
            continue
        gid = str(gid).strip()
        tname = str(tname).strip()
        key = (gid, tname)
        team_lookup[key] = {
            'dragons': int(trow['dragons']) if pd.notna(trow.get('dragons')) else None,
            'opp_dragons': int(trow['opp_dragons']) if pd.notna(trow.get('opp_dragons')) else None,
            'barons': int(trow['barons']) if pd.notna(trow.get('barons')) else None,
            'opp_barons': int(trow['opp_barons']) if pd.notna(trow.get('opp_barons')) else None,
            'towers': int(trow['towers']) if pd.notna(trow.get('towers')) else None,
            'opp_towers': int(trow['opp_towers']) if pd.notna(trow.get('opp_towers')) else None,
            'firstdragon': int(trow['firstdragon']) if pd.notna(trow.get('firstdragon')) else None,
            'firsttower': int(trow['firsttower']) if pd.notna(trow.get('firsttower')) else None,
            'firstherald': int(trow['firstherald']) if pd.notna(trow.get('firstherald')) else None,
            'gamelength': float(trow['gamelength']) if pd.notna(trow.get('gamelength')) else None,
        }
        tk = int(trow['teamkills']) if pd.notna(trow.get('teamkills')) else 0
        td = int(trow['teamdeaths']) if pd.notna(trow.get('teamdeaths')) else 0
        ta = int(trow['teamassists']) if pd.notna(trow.get('teamassists')) else 0
        game_teams.setdefault(gid, []).append((tname, tk, td, ta))
    print(f"   Lookup de linhas 'team' para objetivos: {len(team_lookup)} jogos")
    # Fallback: por gameid, qualquer linha team do jogo (para objetivos quando nome do time não bater)
    gameid_team_vals = {}
    for (gid, _), vals in team_lookup.items():
        if gid not in gameid_team_vals:
            gameid_team_vals[gid] = vals

    # opponentkills/opponentdeaths/opponentassists = kills/deaths/assists do OUTRO time na mesma partida (total da partida = team + opponent)
    opponent_lookup = {}
    for gid, teams in game_teams.items():
        if len(teams) != 2:
            continue
        (t1, k1, d1, a1), (t2, k2, d2, a2) = teams[0], teams[1]
        opponent_lookup[(gid, t1)] = (k2, d2, a2)
        opponent_lookup[(gid, t2)] = (k1, d1, a1)
    print(f"   Lookup opponent kills/deaths/assists: {len(opponent_lookup)} entradas")

    def get_team_vals(gid, tname):
        """Retorna valores da linha team para (gameid, team). Fallback: match case-insensitive; depois por gameid."""
        if not gid:
            return {}
        gid = str(gid).strip()
        if tname:
            key = (gid, str(tname).strip())
            if key in team_lookup:
                return team_lookup[key]
            tlower = str(tname).strip().lower()
            for (k_gid, k_team), vals in team_lookup.items():
                if k_gid == gid and (k_team or "").strip().lower() == tlower:
                    return vals
        # Fallback: objetivos de qualquer linha team desse jogo (evita barons/towers zerados quando nome do time não bate)
        return gameid_team_vals.get(gid, {})

    def get_opponent_vals(gid, tname):
        """Retorna (opponentkills, opponentdeaths, opponentassists) para o time no jogo. Fallback case-insensitive."""
        if not gid or not tname:
            return (None, None, None)
        key = (str(gid).strip(), str(tname).strip())
        if key in opponent_lookup:
            return opponent_lookup[key]
        tlower = tname.strip().lower()
        for (k_gid, k_team), vals in opponent_lookup.items():
            if k_gid == str(gid).strip() and (k_team or "").strip().lower() == tlower:
                return vals
        return (None, None, None)

    # Mapear colunas do CSV para o banco
    batch_size = 1000
    inserted = 0
    skipped_team = 0
    first_error = None
    error_count = 0

    for idx, row in df.iterrows():
        try:
            # Pular apenas linhas de agregação "team" (participantid 100/200)
            position = str(row.get('position', '')).strip().lower() if pd.notna(row.get('position')) else ''
            if position == 'team':
                skipped_team += 1
                continue

            # Extrair dados básicos (tentar playername ou player para compatibilidade com CSVs)
            playername_val = row.get('playername') if pd.notna(row.get('playername')) else row.get('player')
            playername = str(playername_val).strip() if playername_val is not None and str(playername_val).strip() else None

            date = str(row.get('date', '')) if pd.notna(row.get('date')) else None
            gameid = str(row.get('gameid', '')) if pd.notna(row.get('gameid')) else None
            league = str(row.get('league', '')) if pd.notna(row.get('league')) else None
            # Usar teamname (como no banco original oracle_2025.db)
            team = str(row.get('teamname', '')) if pd.notna(row.get('teamname')) else str(row.get('team', '')) if pd.notna(row.get('team')) else None
            champion = str(row.get('champion', '')) if pd.notna(row.get('champion')) else None
            
            # Estatísticas do time
            teamkills = int(row.get('teamkills', 0)) if pd.notna(row.get('teamkills')) else None
            teamdeaths = int(row.get('teamdeaths', 0)) if pd.notna(row.get('teamdeaths')) else None
            teamassists = int(row.get('teamassists', 0)) if pd.notna(row.get('teamassists')) else None
            # Kills totais da partida = teamkills + opponentkills; preencher da lookup (linhas team do mesmo jogo)
            opp_k, opp_d, opp_a = get_opponent_vals(gameid, team) if gameid and team else (None, None, None)
            opponentkills = opp_k
            opponentdeaths = opp_d
            opponentassists = opp_a

            # Estatísticas do player
            kills = int(row.get('kills', 0)) if pd.notna(row.get('kills')) else None
            deaths = int(row.get('deaths', 0)) if pd.notna(row.get('deaths')) else None
            assists = int(row.get('assists', 0)) if pd.notna(row.get('assists')) else None
            
            # Objetivos: SEMPRE preferir a linha "team" (gameid, teamname); nas linhas de jogador o CSV traz 0
            # para barons/opp_barons/towers/dragons, então usar team_vals quando existir.
            team_vals = get_team_vals(gameid, team) if gameid and team else {}
            def _obj(col, cast=int):
                v = team_vals.get(col) if team_vals else None
                if v is not None:
                    return v
                return cast(row.get(col)) if pd.notna(row.get(col)) else None
            dragons = _obj('dragons')
            opp_dragons = _obj('opp_dragons')
            barons = _obj('barons')
            opp_barons = _obj('opp_barons')
            towers = _obj('towers')
            opp_towers = _obj('opp_towers')
            firstdragon = _obj('firstdragon')
            firsttower = _obj('firsttower')
            firstherald = _obj('firstherald')
            gamelength = team_vals.get('gamelength') if team_vals else (float(row.get('gamelength')) if pd.notna(row.get('gamelength')) else None)
            
            # Resultado (1 = vitória, 0 = derrota) — suporta 1.0, Win/Loss, etc. (0 é derrota válida)
            _rv = row.get("result", None)
            if _rv is None or pd.isna(_rv) or (isinstance(_rv, str) and str(_rv).strip() == ""):
                result = None
            else:
                s = str(_rv).strip().lower()
                if s in ("1", "1.0", "true", "t", "win", "w", "victory", "1."):
                    result = 1
                elif s in ("0", "0.0", "false", "f", "loss", "l", "defeat"):
                    result = 0
                else:
                    try:
                        iv = int(float(str(_rv).replace(",", ".")))
                        result = 1 if iv == 1 else 0 if iv == 0 else None
                    except (TypeError, ValueError):
                        result = None
            
            # Gold
            totalgold = int(row.get('totalgold', 0)) if pd.notna(row.get('totalgold')) else None
            teamgold = int(row.get('teamgold', 0)) if pd.notna(row.get('teamgold')) else None
            opponentgold = int(row.get('opponentgold', 0)) if pd.notna(row.get('opponentgold')) else None
            golddiff = int(row.get('golddiff', 0)) if pd.notna(row.get('golddiff')) else None
            xpdiff = int(row.get('xpdiff', 0)) if pd.notna(row.get('xpdiff')) else None
            
            # CS e Gold do player
            cs = int(row.get('cs', 0)) if pd.notna(row.get('cs')) else None
            gold = float(row.get('gold', 0)) if pd.notna(row.get('gold')) else None
            
            # Inserir dados (modo REPLACE - sempre substitui se já existir)
            # Inserir tanto teamname quanto team para compatibilidade; opponentkills para total da partida (kills)
            cursor.execute("""
                INSERT OR REPLACE INTO oracle_matches (
                    date, gameid, league, teamname, team, playername, champion, position,
                    result, teamkills, teamdeaths, teamassists, opponentkills, opponentdeaths, opponentassists,
                    kills, deaths, assists,
                    dragons, opp_dragons, barons, opp_barons, towers, opp_towers,
                    firstdragon, firsttower, firstherald, gamelength,
                    totalgold, teamgold, opponentgold, golddiff, xpdiff,
                    cs, gold
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, gameid, league, team, team, playername, champion, position,
                result, teamkills, teamdeaths, teamassists, opponentkills, opponentdeaths, opponentassists,
                kills, deaths, assists,
                dragons, opp_dragons, barons, opp_barons, towers, opp_towers,
                firstdragon, firsttower, firstherald, gamelength,
                totalgold, teamgold, opponentgold, golddiff, xpdiff,
                cs, gold
            ))
            
            inserted += 1
            
            if inserted % batch_size == 0:
                conn.commit()
                print(f"   Processados {inserted} registros...")
        
        except Exception as e:
            error_count += 1
            if first_error is None:
                first_error = (idx, e)
            continue

    if first_error is not None:
        print(f"   Aviso: {error_count} linhas com erro. Primeiro erro (linha {first_error[0]}): {first_error[1]}")
    if skipped_team > 0:
        print(f"   Linhas puladas (position=team): {skipped_team}")

    conn.commit()

    # Criar índices para melhorar performance
    print("Criando indices...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gameid ON oracle_matches(gameid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team ON oracle_matches(team)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_playername ON oracle_matches(playername)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_league ON oracle_matches(league)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON oracle_matches(date)")
    
    conn.commit()
    conn.close()
    
    print(f"[OK] Banco criado/atualizado: {db_path}")
    print(f"   Total de registros inseridos: {inserted}")
    
    return True


def ensure_db_exists():
    r"""
    Garante que o banco SQLite existe e está atualizado a partir de ``find_latest_csv()``.

    Ordem: ``Documents/db2026/lol_esports.db`` (canónico, ao lado do CSV) >
    (empacotado) ``lol_esports.db`` na pasta do .exe > ``data/lol_esports.db``.

    O CSV de ``db2026`` passa a ter prioridade em ``find_latest_csv``; o ficheiro
    ``oracle_prepared.csv`` nunca alimenta este banco.
    """
    import sys

    def _sync_from_csv(target_db: str) -> bool:
        """Cria ou atualiza ``target_db`` se existir um CSV (por data de modificação)."""
        csv_path = find_latest_csv()
        if not csv_path or not os.path.exists(csv_path):
            return os.path.exists(target_db)
        if not os.path.exists(target_db):
            print(f"Criando banco a partir do CSV: {csv_path}")
            try:
                create_oracle_db_from_csv(csv_path, target_db)
            except Exception as e:
                print(f"Erro ao criar banco: {e}")
                import traceback

                traceback.print_exc()
                return os.path.exists(target_db)
            return os.path.exists(target_db)
        db_mtime = os.path.getmtime(target_db)
        csv_mtime = os.path.getmtime(csv_path)
        if csv_mtime > db_mtime:
            print("CSV mais recente detectado. Atualizando banco...")
            try:
                create_oracle_db_from_csv(csv_path, target_db)
            except Exception as e:
                print(f"Erro ao atualizar banco: {e}")
                import traceback

                traceback.print_exc()
        return os.path.exists(target_db)

    db2026_dir = get_lol_db2026_dir()
    db2026_path = os.path.join(db2026_dir, "lol_esports.db")

    # 1) Sempre que existir (ou puder ser criada) a pasta db2026: banco = ficheiro ao lado do CSV
    try:
        os.makedirs(db2026_dir, exist_ok=True)
    except OSError:
        pass
    if os.path.isdir(db2026_dir):
        if _sync_from_csv(db2026_path):
            return db2026_path
        if os.path.exists(db2026_path):
            return db2026_path

    # 2) Empacotado: mesma pasta do utilizador / .exe
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        user_dir = os.path.dirname(exe_dir) if "_internal" in exe_dir else exe_dir
        user_db_path = os.path.join(user_dir, "lol_esports.db")
        if _sync_from_csv(user_db_path) or os.path.exists(user_db_path):
            return user_db_path

    # 3) Fallback: data/ do projeto
    data_dir = get_data_dir()
    db_path = os.path.join(data_dir, "lol_esports.db")
    if _sync_from_csv(db_path) or os.path.exists(db_path):
        return db_path
    if not find_latest_csv():
        print("Nenhum CSV encontrado em:")
        print(f"   - {db2026_dir}")
        print(f"   - {data_dir}")
    return None
