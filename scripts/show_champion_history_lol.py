"""
Histórico de partidas de um campeão específico no LoL.
Fonte: data/oracle_prepared.csv.
Uso:
  Interativo (escolhe campeão e liga no terminal):
    python scripts/show_champion_history_lol.py
  Linha de comando (escolher campeão e liga por argumentos):
    python scripts/show_champion_history_lol.py --campeao karma --liga LCK
    python scripts/show_champion_history_lol.py --campeao ezreal --liga MAJOR
    python scripts/show_champion_history_lol.py --campeao ryze --liga "LPL"
    python scripts/show_champion_history_lol.py --campeao lee sin
"""
import argparse
import os
import sys

import pandas as pd

# Raiz do projeto (pasta que contém data/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}


def determinar_vencedor(df_game):
    """Determina qual time venceu a partida."""
    if len(df_game) != 2:
        return None
    if "result" in df_game.columns:
        t1_result = df_game.iloc[0]["result"]
        t2_result = df_game.iloc[1]["result"]
        if pd.notna(t1_result) and pd.notna(t2_result):
            if t1_result == 1 or str(t1_result).lower() in ["1", "true", "win", "w"]:
                return df_game.iloc[0]["teamname"]
            if t2_result == 1 or str(t2_result).lower() in ["1", "true", "win", "w"]:
                return df_game.iloc[1]["teamname"]
    t1_kills = df_game.iloc[0]["teamkills"]
    t2_kills = df_game.iloc[1]["teamkills"]
    if t1_kills > t2_kills:
        return df_game.iloc[0]["teamname"]
    if t2_kills > t1_kills:
        return df_game.iloc[1]["teamname"]
    return None


def obter_campeoes_disponiveis(df):
    """Lista de todos os campeões presentes no banco."""
    campeoes = set()
    for col in ["pick1", "pick2", "pick3", "pick4", "pick5"]:
        if col in df.columns:
            campeoes.update(df[col].dropna().astype(str).str.strip())
    return sorted([c for c in campeoes if c and c.lower() != "nan"])


def buscar_partidas_campeao(df, campeao, liga=None, apenas_major=False, apenas_nao_major=False):
    """Busca partidas onde o campeão apareceu (em qualquer pick)."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    pick_cols = [c for c in ["pick1", "pick2", "pick3", "pick4", "pick5"] if c in df.columns]
    if not pick_cols:
        return pd.DataFrame()

    mask = pd.Series(False, index=df.index)
    for col in pick_cols:
        mask = mask | (df[col].astype(str).str.strip().str.casefold() == campeao.strip().casefold())

    if liga:
        if "league" not in df.columns:
            return pd.DataFrame()
        mask = mask & (df["league"].astype(str).str.strip().str.casefold() == liga.strip().casefold())
    elif apenas_major:
        mask = mask & (df["league"].astype(str).str.strip().str.upper().isin(MAJOR_LEAGUES))
    elif apenas_nao_major:
        mask = mask & (~df["league"].astype(str).str.strip().str.upper().isin(MAJOR_LEAGUES))

    partidas = df.loc[mask].copy()
    if partidas.empty:
        return partidas

    # Normalizar nome da coluna de resultado
    res_col = "result"
    if res_col not in partidas.columns and "result" in partidas.columns:
        res_col = "result"

    partidas["venceu"] = False
    for gameid in partidas["gameid"].unique():
        df_game = df[df["gameid"] == gameid]
        if len(df_game) != 2:
            continue
        vencedor = determinar_vencedor(df_game)
        if vencedor is None:
            continue
        partidas.loc[partidas["gameid"] == gameid, "venceu"] = (
            partidas.loc[partidas["gameid"] == gameid, "teamname"].values == vencedor
        )
    return partidas


def calcular_estatisticas(partidas):
    """Calcula estatísticas das partidas do campeão."""
    if partidas is None or len(partidas) == 0:
        return None
    col_league = "league" if "league" in partidas.columns else None
    stats = {
        "total_jogos": len(partidas),
        "vitorias": int(partidas["venceu"].sum()),
        "derrotas": int((~partidas["venceu"]).sum()),
        "win_rate": (partidas["venceu"].sum() / len(partidas)) * 100,
        "media_total_kills": float(partidas["total_kills"].mean()),
        "mediana_total_kills": float(partidas["total_kills"].median()),
        "min_total_kills": float(partidas["total_kills"].min()),
        "max_total_kills": float(partidas["total_kills"].max()),
        "desvio_total_kills": float(partidas["total_kills"].std()) if len(partidas) > 1 else 0.0,
        "por_liga": {},
    }
    if col_league:
        for liga in partidas[col_league].unique():
            partidas_liga = partidas[partidas[col_league] == liga]
            stats["por_liga"][liga] = {
                "jogos": len(partidas_liga),
                "vitorias": int(partidas_liga["venceu"].sum()),
                "win_rate": (partidas_liga["venceu"].sum() / len(partidas_liga)) * 100 if len(partidas_liga) > 0 else 0,
                "media_total_kills": float(partidas_liga["total_kills"].mean()),
            }
    return stats


def exibir_historico(partidas, campeao, stats):
    """Exibe histórico e estatísticas no terminal."""
    print("\n" + "=" * 80)
    print(f"HISTÓRICO DO CAMPEÃO: {campeao.upper()}")
    print("=" * 80)

    print("\nESTATÍSTICAS GERAIS:")
    print(f"  Total de jogos: {stats['total_jogos']}")
    print(f"  Vitórias: {stats['vitorias']} | Derrotas: {stats['derrotas']}")
    print(f"  Win Rate: {stats['win_rate']:.2f}%")
    print("\n  Total de Kills (por partida):")
    print(f"    Média: {stats['media_total_kills']:.2f}")
    print(f"    Mediana: {stats['mediana_total_kills']:.2f}")
    print(f"    Mínimo: {stats['min_total_kills']:.0f}")
    print(f"    Máximo: {stats['max_total_kills']:.0f}")
    print(f"    Desvio padrão: {stats['desvio_total_kills']:.2f}")

    if stats.get("por_liga"):
        print("\n  ESTATÍSTICAS POR LIGA:")
        for liga, liga_stats in sorted(stats["por_liga"].items()):
            print(f"    {liga}:")
            print(f"      Jogos: {liga_stats['jogos']} | Win Rate: {liga_stats['win_rate']:.2f}%")
            print(f"      Média Total Kills: {liga_stats['media_total_kills']:.2f}")

    print("\n" + "=" * 80)
    print(f"HISTÓRICO DETALHADO ({len(partidas)} partidas)")
    print("=" * 80)

    if "date" in partidas.columns:
        partidas = partidas.copy()
        partidas["_date"] = pd.to_datetime(partidas["date"], errors="coerce")
        partidas = partidas.sort_values("_date", ascending=False)

    for idx, row in partidas.iterrows():
        data = row.get("date", "N/A")
        if pd.notna(data):
            data_str = data.strftime("%Y-%m-%d") if hasattr(data, "strftime") else str(data)[:10]
        else:
            data_str = "N/A"
        liga = row.get("league", "N/A")
        time = row.get("teamname", "N/A")
        adversario = row.get("opponent", "N/A")
        resultado = "VITÓRIA" if row["venceu"] else "DERROTA"
        total_kills = row.get("total_kills", 0)
        teamkills = row.get("teamkills", 0)
        posicoes = []
        for i in range(1, 6):
            col = f"pick{i}"
            if col in row and str(row[col]).strip().casefold() == campeao.strip().casefold():
                posicoes.append(f"Pos{i}")
        posicao_str = ", ".join(posicoes) if posicoes else "?"
        print(f"\n  {data_str} | {liga} | {time} vs {adversario}")
        print(f"    Resultado: {resultado} | Total Kills: {total_kills:.0f} | Kills do Time: {teamkills:.0f}")
        print(f"    Posição: {posicao_str}")


def _resolve_campeao(busca, campeoes):
    """Retorna nome exato do campeão a partir de busca (parcial)."""
    busca = busca.strip()
    matches = [c for c in campeoes if busca.casefold() in str(c).casefold()]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Primeiro que começa com a busca, senão o primeiro da lista
    for c in matches:
        if str(c).casefold().startswith(busca.casefold()):
            return c
    return matches[0]


def _resolve_liga(liga_arg, df):
    """Retorna (liga_filtro, apenas_major, apenas_nao_major) para usar em buscar_partidas_campeao."""
    ligas_disponiveis = sorted(df["league"].dropna().astype(str).str.strip().unique().tolist())
    liga_arg = (liga_arg or "").strip().upper()
    if not liga_arg:
        return None, False, False
    if liga_arg == "MAJOR":
        return None, True, False
    if liga_arg == "NAO-MAJOR":
        return None, False, True
    # Liga específica (case-insensitive match)
    for lg in ligas_disponiveis:
        if lg.upper() == liga_arg:
            return lg, False, False
    return None, False, False


def main():
    parser = argparse.ArgumentParser(
        description="Histórico de partidas de um campeão no LoL (oracle_prepared.csv)."
    )
    parser.add_argument(
        "--campeao", "-c",
        type=str,
        default=None,
        help="Nome do campeão (ou parte do nome). Se omitido, modo interativo.",
    )
    parser.add_argument(
        "--liga", "-l",
        type=str,
        default=None,
        help="Liga: MAJOR, NAO-MAJOR ou nome exato (ex: LCK, LPL, LEC). Se omitido, todas.",
    )
    parser.add_argument(
        "--salvar", "-s",
        action="store_true",
        help="Salvar histórico em CSV em data/historico_<campeao>.csv",
    )
    parser.add_argument(
        "--listar-ligas",
        action="store_true",
        help="Listar ligas disponíveis e sair.",
    )
    args = parser.parse_args()

    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo não encontrado: {DATA_PATH}")
        sys.exit(1)

    print("=" * 80)
    print("HISTÓRICO DE CAMPEÃO - LoL Oracle ML v3")
    print("=" * 80)
    print(f"\n[OK] Carregando dados de {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df.columns = df.columns.str.strip()
    print(f"[OK] {len(df)} linhas carregadas.")

    ligas_disponiveis = sorted(df["league"].dropna().astype(str).str.strip().unique().tolist())
    if args.listar_ligas:
        print("\nLigas disponíveis:")
        for lg in ligas_disponiveis:
            tipo = "MAJOR" if lg.upper() in MAJOR_LEAGUES else "não-MAJOR"
            print(f"  {lg} ({tipo})")
        print("\nUse: --liga MAJOR | --liga NAO-MAJOR | --liga LCK (exemplo)")
        sys.exit(0)

    campeoes = obter_campeoes_disponiveis(df)
    print(f"[OK] {len(campeoes)} campeões no banco.")

    # ---- Campeão ----
    if args.campeao:
        campeao = _resolve_campeao(args.campeao, campeoes)
        if not campeao:
            print(f"[ERRO] Nenhum campeão encontrado com '{args.campeao}'.")
            sys.exit(1)
        print(f"\n[OK] Campeão: {campeao}")
    else:
        print("\n" + "=" * 80)
        print("SELECÃO DE CAMPEÃO")
        print("=" * 80)
        busca = input("\nDigite o nome do campeão (ou parte do nome): ").strip()
        if not busca:
            print("[ERRO] Nome não pode estar vazio.")
            sys.exit(1)
        campeao = _resolve_campeao(busca, campeoes)
        if not campeao:
            print(f"[ERRO] Nenhum campeão encontrado com '{busca}'.")
            sys.exit(1)
        if len([c for c in campeoes if busca.casefold() in str(c).casefold()]) > 1:
            print(f"[OK] Campeão selecionado: {campeao}")

    # ---- Liga ----
    if args.liga is not None:
        liga_filtro, apenas_major, apenas_nao_major = _resolve_liga(args.liga, df)
        if args.liga.strip().upper() not in ("MAJOR", "NAO-MAJOR", "") and liga_filtro is None:
            print(f"[AVISO] Liga '{args.liga}' não encontrada. Use --listar-ligas para ver opções.")
    else:
        print("\n" + "=" * 80)
        print("FILTRO POR LIGA (opcional)")
        print("=" * 80)
        print("  1. MAJOR (LPL, LCK, LEC, CBLOL, LCS, LCP)")
        print("  2. NAO-MAJOR")
        print("  3. Liga específica")
        print("  4. Todas as ligas")
        escolha = input("\nEscolha (1/2/3/4) [4]: ").strip() or "4"
        if escolha == "1":
            liga_filtro, apenas_major, apenas_nao_major = None, True, False
        elif escolha == "2":
            liga_filtro, apenas_major, apenas_nao_major = None, False, True
        elif escolha == "3":
            for i, lg in enumerate(ligas_disponiveis, 1):
                print(f"  {i}. {lg}")
            try:
                idx = int(input("Número da liga: ").strip()) - 1
                if 0 <= idx < len(ligas_disponiveis):
                    liga_filtro = ligas_disponiveis[idx]
                    apenas_major, apenas_nao_major = False, False
                else:
                    liga_filtro, apenas_major, apenas_nao_major = None, False, False
            except (ValueError, EOFError):
                liga_filtro, apenas_major, apenas_nao_major = None, False, False
        else:
            liga_filtro, apenas_major, apenas_nao_major = None, False, False

    partidas = buscar_partidas_campeao(df, campeao, liga_filtro, apenas_major, apenas_nao_major)
    if len(partidas) == 0:
        print(f"\n[ERRO] Nenhuma partida encontrada para '{campeao}'.")
        if liga_filtro:
            print(f"       Liga: {liga_filtro}")
        elif apenas_major:
            print("       Filtro: MAJOR")
        elif apenas_nao_major:
            print("       Filtro: NAO-MAJOR")
        sys.exit(1)

    print(f"\n[OK] {len(partidas)} partidas encontradas.")
    stats = calcular_estatisticas(partidas)
    exibir_historico(partidas, campeao, stats)

    safe_name = campeao.replace(" ", "_").replace("'", "")
    if args.salvar:
        out_name = f"historico_{safe_name}.csv"
        output_path = os.path.join(BASE_DIR, "data", out_name)
        partidas.to_csv(output_path, index=False)
        print(f"\n[OK] Histórico salvo em: {output_path}")
    elif not args.campeao:
        print("\n" + "=" * 80)
        salvar = input("Salvar histórico em CSV? (s/n): ").strip().lower()
        if salvar in ("s", "sim", "y", "yes"):
            out_name = f"historico_{safe_name}.csv"
            output_path = os.path.join(BASE_DIR, "data", out_name)
            partidas.to_csv(output_path, index=False)
            print(f"[OK] Salvo em: {output_path}")

    print("\n" + "=" * 80)
    print("[OK] Análise concluída.")
    print("=" * 80)


if __name__ == "__main__":
    main()
