import os
import sys
import pickle
import itertools
import pandas as pd

# Ajustar caminho
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from src.load_and_predict_v3 import predict_game

MODEL_PATH = os.path.join(ROOT_DIR, "model_artifacts")
DATA_PATH = os.path.join(ROOT_DIR, "data")

# === Caminhos de dados ===
SYNERGY_PATH = os.path.join(DATA_PATH, "champion_synergies_simples.pkl")
MATCHUP_PATH = os.path.join(DATA_PATH, "matchup_synergies_simple.pkl")

MIN_SYNERGY_GAMES = 5
MIN_MATCHUP_GAMES = 5

# Ligas Major
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}

# Caminho para dados brutos (para recalcular impactos)
ORACLE_PREPARED_PATH = os.path.join(DATA_PATH, "oracle_prepared.csv")


# =========================================================
# FUNÇÕES DE CARREGAMENTO
# =========================================================

def carregar_pickle(path, nome):
    try:
        df = pd.read_pickle(path)
        df.columns = df.columns.str.strip()
        print(f"{nome} carregado ({len(df)} linhas)")
        return df
    except FileNotFoundError:
        print(f"Arquivo {nome} não encontrado: {path}")
        return None
    except Exception as e:
        print(f"Erro ao carregar {nome}: {e}")
        return None


# =========================================================
# SINERGIAS DE DRAFT
# =========================================================

def mostrar_sinergias_draft(leagues, team1, team2, synergy_df):
    if synergy_df is None:
        return

    # Se leagues é string, converter para lista
    if isinstance(leagues, str):
        leagues = [leagues]
    
    # Filtrar por ligas
    df_league = synergy_df[
        (synergy_df["league"].isin(leagues))
        & (synergy_df["n_games"] >= MIN_SYNERGY_GAMES)
    ]

    pairs_t1 = [tuple(sorted(p)) for p in itertools.combinations(team1, 2)]
    pairs_t2 = [tuple(sorted(p)) for p in itertools.combinations(team2, 2)]

    sin_t1, sin_t2 = [], []
    for c1, c2 in pairs_t1:
        mask = (
            (df_league["champ1"].str.lower() == c1.lower())
            & (df_league["champ2"].str.lower() == c2.lower())
        )
        if mask.any():
            sin_t1.append(df_league[mask].iloc[0])

    for c1, c2 in pairs_t2:
        mask = (
            (df_league["champ1"].str.lower() == c1.lower())
            & (df_league["champ2"].str.lower() == c2.lower())
        )
        if mask.any():
            sin_t2.append(df_league[mask].iloc[0])

    # Formatar nome das ligas para exibição
    if isinstance(leagues, list):
        if len(leagues) == len(MAJOR_LEAGUES) and set(leagues) == MAJOR_LEAGUES:
            league_display = "MAJOR (todas)"
        else:
            league_display = ", ".join(leagues)
    else:
        league_display = leagues
    
    print(f"\nSinergias simples detectadas (liga(s): {league_display}, n ≥ {MIN_SYNERGY_GAMES}):")

    if not sin_t1 and not sin_t2:
        print("   Nenhuma sinergia relevante encontrada para este draft.")
        return

    def fmt(row):
        return f"{row['champ1']} + {row['champ2']} → {row['sinergia_bruta']:+.2f} kills (n={row['n_games']})"

    if sin_t1:
        print("   Time 1:")
        for r in sin_t1:
            print("    - " + fmt(r))
    if sin_t2:
        print("   Time 2:")
        for r in sin_t2:
            print("    - " + fmt(r))


# =========================================================
# MATCHUPS DE CHAMPIONS (por role e anyrole)
# =========================================================

def mostrar_matchups(leagues, team1, team2, matchup_df):
    if matchup_df is None:
        return

    # Se leagues é string, converter para lista
    if isinstance(leagues, str):
        leagues = [leagues]
    
    # Filtrar por ligas
    df_league = matchup_df[
        (matchup_df["league"].isin(leagues))
        & (matchup_df["n_games"] >= MIN_MATCHUP_GAMES)
    ]

    # Formatar nome das ligas para exibição
    if isinstance(leagues, list):
        if len(leagues) == len(MAJOR_LEAGUES) and set(leagues) == MAJOR_LEAGUES:
            league_display = "MAJOR (todas)"
        else:
            league_display = ", ".join(leagues)
    else:
        league_display = leagues

    print(f"\nMatchups detectadas (liga(s): {league_display}, n ≥ {MIN_MATCHUP_GAMES}):")

    roles = ["top", "jung", "mid", "adc", "sup"]
    found = False
    matchups_diretos = set()

    for i, role in enumerate(roles):
        c1 = team1[i]
        c2 = team2[i]

        mask = (
            (df_league["role"].str.lower() == role)
            & (df_league["champ1"].str.lower() == c1.lower())
            & (df_league["champ2"].str.lower() == c2.lower())
        )
        if not mask.any():
            mask = (
                (df_league["role"].str.lower() == role)
                & (df_league["champ1"].str.lower() == c2.lower())
                & (df_league["champ2"].str.lower() == c1.lower())
            )

        if mask.any():
            row = df_league[mask].iloc[0]
            found = True
            print(
                f"   {role.upper():>4}: {c1} vs {c2} → {row['impacto_matchup']:+.2f} kills (n={row['n_games']})"
            )
            matchups_diretos.add(tuple(sorted([c1.lower(), c2.lower()])))

    # Anyrole sem duplicar
    df_any = df_league[df_league["role"].str.lower() == "anyrole"]
    any_matches = []

    for c1 in team1:
        for c2 in team2:
            key = tuple(sorted([c1.lower(), c2.lower()]))
            if key in matchups_diretos:
                continue

            mask = (
                (df_any["champ1"].str.lower() == c1.lower())
                & (df_any["champ2"].str.lower() == c2.lower())
            )
            if not mask.any():
                mask = (
                    (df_any["champ1"].str.lower() == c2.lower())
                    & (df_any["champ2"].str.lower() == c1.lower())
                )
            if mask.any():
                any_matches.append(df_any[mask].iloc[0])

    if any_matches:
        print("\n   Anyrole matchups (fora das lanes diretas):")
        for row in any_matches[:5]:
            print(
                f"    - {row['champ1']} vs {row['champ2']} → {row['impacto_matchup']:+.2f} kills (n={row['n_games']})"
            )

    if not found and not any_matches:
        print("   Nenhum matchup encontrado para este jogo.")


# =========================================================
# MAIN
# =========================================================

def get_available_leagues(impacts):
    """Obtém lista de ligas disponíveis nos dados"""
    if impacts is None or impacts.empty:
        return []
    return sorted(impacts["league"].unique().tolist())

def selecionar_liga(available_leagues):
    """Permite ao usuário selecionar liga: major, não-major, ou específica"""
    major_disponiveis = [lg for lg in available_leagues if lg in MAJOR_LEAGUES]
    nao_major_disponiveis = [lg for lg in available_leagues if lg not in MAJOR_LEAGUES]
    
    print("\n" + "="*60)
    print("SELECAO DE LIGA")
    print("="*60)
    print("Opcoes:")
    print("  1. MAJOR (todas as ligas major: LCK, LPL, LCS, CBLOL, LCP, LEC)")
    if nao_major_disponiveis:
        print("  2. NAO-MAJOR (todas as ligas que nao sao major)")
    print("  3. Liga especifica")
    print("="*60)
    
    escolha = input("Escolha uma opcao (1/2/3): ").strip()
    
    if escolha == "1":
        # Incluir todas as ligas major, mesmo que não estejam em champion_impacts.csv
        # Verificar se existem em oracle_prepared.csv
        try:
            oracle_df = pd.read_csv(ORACLE_PREPARED_PATH)
            oracle_leagues = set(oracle_df["league"].unique())
            # Incluir todas as ligas major que existem em oracle_prepared.csv
            # Ordem específica: LCK, LPL, LCS, CBLOL, LCP, LEC
            ordem_major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]
            major_final = [lg for lg in ordem_major if lg in MAJOR_LEAGUES and lg in oracle_leagues]
            if major_final:
                print(f"\n[OK] Usando todas as ligas MAJOR: {', '.join(major_final)}")
                return major_final
        except:
            pass
        
        # Fallback: usar apenas as que estão em champion_impacts.csv
        if major_disponiveis:
            print(f"\n[OK] Usando ligas MAJOR disponíveis: {', '.join(major_disponiveis)}")
            return major_disponiveis
        else:
            print("[AVISO] Nenhuma liga major disponivel. Usando primeira liga disponivel.")
            return [available_leagues[0]]
    
    elif escolha == "2" and nao_major_disponiveis:
        print(f"\n[OK] Usando ligas NAO-MAJOR: {', '.join(nao_major_disponiveis)}")
        return nao_major_disponiveis
    
    elif escolha == "3":
        print(f"\nLigas disponiveis:")
        for i, lg in enumerate(available_leagues, 1):
            tipo = "MAJOR" if lg in MAJOR_LEAGUES else "nao-MAJOR"
            print(f"  {i}. {lg} ({tipo})")
        
        try:
            idx = int(input("\nEscolha o numero da liga: ").strip()) - 1
            if 0 <= idx < len(available_leagues):
                liga_escolhida = available_leagues[idx]
                print(f"[OK] Liga selecionada: {liga_escolhida}")
                return liga_escolhida
            else:
                print(f"[ERRO] Numero invalido. Usando primeira liga disponivel.")
                return available_leagues[0]
        except (ValueError, EOFError):
            print(f"[ERRO] Entrada invalida. Usando primeira liga disponivel.")
            return available_leagues[0]
    
    else:
        print(f"[AVISO] Opcao invalida. Usando primeira liga disponivel.")
        return available_leagues[0]

def calcular_league_stats_agregado(leagues, league_stats):
    """Calcula estatísticas agregadas para múltiplas ligas"""
    if isinstance(leagues, str):
        return league_stats.get(leagues, league_stats.get(list(league_stats.keys())[0]))
    
    # Agregar estatísticas de múltiplas ligas
    stats_list = [league_stats.get(lg) for lg in leagues if lg in league_stats]
    if not stats_list:
        # Fallback para primeira liga disponível
        return league_stats.get(list(league_stats.keys())[0])
    
    # Calcular média ponderada
    total_games = sum(s["games"] for s in stats_list)
    if total_games == 0:
        return stats_list[0]
    
    mean_kills = sum(s["mean_kills"] * s["games"] for s in stats_list) / total_games
    # Para std, usar a maior (mais conservador)
    std_kills = max(s["std_kills"] for s in stats_list)
    
    return {
        "mean_kills": round(mean_kills, 2),
        "std_kills": round(std_kills, 2),
        "games": total_games
    }

def recalcular_impactos_agregados(leagues_list, campeao):
    """Recalcula o impacto de um campeão usando média agregada de múltiplas ligas"""
    if not os.path.exists(ORACLE_PREPARED_PATH):
        return None, 0
    
    # Carregar dados brutos
    df = pd.read_csv(ORACLE_PREPARED_PATH)
    
    # Filtrar apenas as ligas selecionadas
    df = df[df["league"].isin(leagues_list)]
    
    if len(df) == 0:
        return None, 0
    
    # Calcular média agregada de total_kills para todas as ligas selecionadas
    # Remover duplicatas por gameid (cada partida aparece 2 vezes - um por time)
    df_unique = df.drop_duplicates(subset=["gameid", "total_kills"])
    media_agregada = df_unique["total_kills"].mean()
    
    # Buscar todas as partidas onde o campeão jogou
    mask = (
        (df["pick1"].str.casefold() == campeao.casefold()) |
        (df["pick2"].str.casefold() == campeao.casefold()) |
        (df["pick3"].str.casefold() == campeao.casefold()) |
        (df["pick4"].str.casefold() == campeao.casefold()) |
        (df["pick5"].str.casefold() == campeao.casefold())
    )
    
    partidas_campeao = df[mask]
    
    if len(partidas_campeao) == 0:
        return None, 0
    
    # Remover duplicatas por gameid para calcular média correta
    partidas_campeao_unique = partidas_campeao.drop_duplicates(subset=["gameid", "total_kills"])
    
    # Calcular média de total_kills quando o campeão joga
    media_com_campeao = partidas_campeao_unique["total_kills"].mean()
    
    # Calcular impacto: média com campeão - média agregada
    impacto = media_com_campeao - media_agregada
    
    # Número de jogos
    n_jogos = len(partidas_campeao_unique)
    
    return float(impacto), int(n_jogos)

def main():
    print("=== LoL Oracle ML v4 - Análise de Draft (Impactos + Sinergias + Matchups) ===\n")

    # Carregar dados primeiro para obter ligas disponíveis
    try:
        impacts = pd.read_csv(os.path.join(DATA_PATH, "champion_impacts.csv"))
        impacts.columns = impacts.columns.str.strip().str.lower()
        
        with open(os.path.join(DATA_PATH, "league_stats_v3.pkl"), "rb") as f:
            league_stats = pickle.load(f)
        
        # Obter ligas disponíveis e selecionar
        available_leagues = get_available_leagues(impacts)
        if not available_leagues:
            print("[ERRO] Nenhuma liga encontrada nos dados!")
            return
        
        league = selecionar_liga(available_leagues)
        
    except Exception as e:
        print(f"Erro ao carregar dados para seleção de liga: {e}")
        print("Usando modo antigo (digite a liga manualmente)")
        league = input("Liga (ex: LCK, LPL, LEC, CBLOL, MSI, WORLDS): ").strip()
    
    threshold_str = input("Threshold (ex: 0.55): ").strip()
    threshold = float(threshold_str) if threshold_str else 0.55

    print("\nDigite os 5 campeões do Time 1:")
    team1 = [input(f"  Campeão {i+1}: ").strip() for i in range(5)]

    print("\nDigite os 5 campeões do Time 2:")
    team2 = [input(f"  Campeão {i+1}: ").strip() for i in range(5)]

    try:
        with open(os.path.join(MODEL_PATH, "trained_models_v3.pkl"), "rb") as f:
            models = pickle.load(f)
        with open(os.path.join(MODEL_PATH, "scaler_v3.pkl"), "rb") as f:
            scaler = pickle.load(f)
        with open(os.path.join(MODEL_PATH, "feature_columns_v3.pkl"), "rb") as f:
            feature_cols = pickle.load(f)
        with open(os.path.join(DATA_PATH, "league_stats_v3.pkl"), "rb") as f:
            league_stats = pickle.load(f)

        impacts = pd.read_csv(os.path.join(DATA_PATH, "champion_impacts.csv"))
        impacts.columns = impacts.columns.str.strip().str.lower()

        synergy_df = carregar_pickle(SYNERGY_PATH, "Sinergias simples")
        matchup_df = carregar_pickle(MATCHUP_PATH, "Matchups simples")

        print("\nModelos e dados carregados com sucesso!\n")

    except Exception as e:
        print("Erro ao carregar arquivos do modelo ou dados:", e)
        return

    # === IMPACTOS INDIVIDUAIS ===
    print("--- IMPACTOS INDIVIDUAIS ---")
    
    # Formatar nome das ligas para exibição
    if isinstance(league, list):
        if len(league) == len(MAJOR_LEAGUES) and set(league) == MAJOR_LEAGUES:
            league_display = "MAJOR (todas)"
        else:
            league_display = ", ".join(league)
    else:
        league_display = league
    
    leagues_list = league if isinstance(league, list) else [league]
    
    for label, team in [("Time 1", team1), ("Time 2", team2)]:
        print(f"{label}:")
        for champ in team:
            # Se múltiplas ligas, recalcular impacto usando média agregada
            if isinstance(league, list) and len(league) > 1:
                imp, n_games = recalcular_impactos_agregados(leagues_list, champ)
                if imp is not None:
                    print(f"  {champ:<12} {imp:+.2f} (n={n_games}) [recalculado com media agregada]")
                else:
                    print(f"  {champ:<12} sem dados")
            else:
                # Liga única: usar impacto já calculado
                mask = impacts["league"].isin(leagues_list) & \
                       (impacts["champion"].str.lower() == champ.lower())
                row = impacts[mask]
                
                if not row.empty:
                    imp = float(row["impact"].iloc[0])
                    if "games_played" in row.columns:
                        n_games = int(row["games_played"].iloc[0])
                    elif "n" in row.columns:
                        n_games = int(row["n"].iloc[0])
                    else:
                        n_games = "?"
                    print(f"  {champ:<12} {imp:+.2f} (n={n_games})")
                else:
                    print(f"  {champ:<12} sem dados")
        print()

    # === Predição principal ===
    try:
        # Para predição, usar primeira liga se for lista, ou calcular stats agregado
        if isinstance(league, list):
            league_for_pred = league[0]  # Usar primeira liga para predição
            league_stats_agregado = calcular_league_stats_agregado(league, league_stats)
            
            # Se múltiplas ligas, criar DataFrame temporário com impactos recalculados
            impacts_para_pred = impacts.copy()
            todos_campeoes = set(team1 + team2)
            
            for champ in todos_campeoes:
                imp, n_jogos = recalcular_impactos_agregados(leagues_list, champ)
                if imp is not None:
                    # Buscar ou criar entrada para este campeão na primeira liga
                    mask = (impacts_para_pred["league"] == league_for_pred) & \
                           (impacts_para_pred["champion"].str.lower() == champ.lower())
                    
                    if mask.any():
                        # Atualizar impacto existente
                        impacts_para_pred.loc[mask, "impact"] = imp
                        if "games_played" in impacts_para_pred.columns:
                            impacts_para_pred.loc[mask, "games_played"] = n_jogos
                    else:
                        # Criar nova linha se não existir
                        new_row = {}
                        # Preencher todas as colunas do DataFrame original com valores apropriados
                        for col in impacts_para_pred.columns:
                            if col == "league":
                                new_row[col] = league_for_pred
                            elif col == "champion":
                                new_row[col] = champ
                            elif col == "impact":
                                new_row[col] = float(imp)
                            elif col == "games_played" or col == "n":
                                new_row[col] = int(n_jogos)
                            elif col == "league_avg_kills":
                                new_row[col] = float(league_stats_agregado["mean_kills"])
                            elif col == "avg_kills_with_champ":
                                # Calcular média com campeão (impacto + média liga)
                                new_row[col] = float(imp + league_stats_agregado["mean_kills"])
                            elif col == "league_std_kills":
                                new_row[col] = float(league_stats_agregado.get("std_kills", 0.0))
                            else:
                                # Para outras colunas, usar valor padrão do tipo correto
                                dtype = impacts_para_pred[col].dtype
                                if pd.api.types.is_float_dtype(dtype):
                                    new_row[col] = 0.0
                                elif pd.api.types.is_integer_dtype(dtype):
                                    new_row[col] = 0
                                elif pd.api.types.is_string_dtype(dtype) or dtype == 'object':
                                    new_row[col] = ""
                                else:
                                    new_row[col] = 0.0
                        
                        # Criar DataFrame com as mesmas colunas e tipos, garantindo ordem
                        # Garantir que a ordem das colunas seja a mesma e tipos corretos
                        new_df = pd.DataFrame([new_row])
                        # Reordenar colunas para corresponder ao DataFrame original
                        new_df = new_df.reindex(columns=impacts_para_pred.columns)
                        # Preencher valores faltantes com base no tipo da coluna
                        for col in new_df.columns:
                            if new_df[col].isna().any():
                                dtype = impacts_para_pred[col].dtype
                                if pd.api.types.is_float_dtype(dtype):
                                    new_df[col] = new_df[col].fillna(0.0)
                                elif pd.api.types.is_integer_dtype(dtype):
                                    new_df[col] = new_df[col].fillna(0)
                                else:
                                    new_df[col] = new_df[col].fillna("")
                        # Usar pd.concat com sort=False para evitar warnings
                        impacts_para_pred = pd.concat([impacts_para_pred, new_df], ignore_index=True, sort=False)
        else:
            league_for_pred = league
            league_stats_agregado = league_stats.get(league, league_stats.get(list(league_stats.keys())[0]))
            impacts_para_pred = impacts
        
        game_data = {"league": league_for_pred, "team1": team1, "team2": team2}
        result = predict_game(
            game_data, models, scaler, impacts_para_pred, {league_for_pred: league_stats_agregado}, feature_cols, threshold
        )
    except Exception as e:
        print("\nErro durante a previsão:", e)
        return

    print(f"\nResultados para a liga(s): {league_display}")
    print(f"Impacto total Time 1: {result['impacto_t1']:+.2f}")
    print(f"Impacto total Time 2: {result['impacto_t2']:+.2f}")
    print(f"Kills estimados: {result['kills_estimados']:.2f}\n")

    print("=== RESULTADOS POR LINHA ===")
    for line, r in sorted(result["resultados"].items(), key=lambda kv: float(kv[0])):
        prob_under = float(r["Prob(UNDER)"])
        prob_over = 100.0 - prob_under

        if prob_over > 50 and prob_over >= prob_under:
            lado = "OVER"
            label_prob = "Prob(OVER )"
            prob_mostrar = prob_over
        elif prob_under > 50:
            lado = "UNDER"
            label_prob = "Prob(UNDER)"
            prob_mostrar = prob_under
        else:
            escolha = str(r["Escolha"]).strip().upper()
            if escolha == "OVER":
                lado = "OVER"
                label_prob = "Prob(OVER )"
                prob_mostrar = prob_over
            else:
                lado = "UNDER"
                label_prob = "Prob(UNDER)"
                prob_mostrar = prob_under

        print(
            f"Linha {float(line):>5.1f}: {lado:6} | {label_prob}: {prob_mostrar:6.2f}% | Confiança: {r['Confiança']}"
        )

    # === Sinergias e Matchups ===
    mostrar_sinergias_draft(league, team1, team2, synergy_df)
    mostrar_matchups(league, team1, team2, matchup_df)


if __name__ == "__main__":
    main()
