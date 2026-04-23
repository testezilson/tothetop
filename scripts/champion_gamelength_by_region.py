#!/usr/bin/env python3
"""
Média de duração de jogo (gamelength) por campeão, com corte por região e por MAJOR.

Fonte: CSV OraclesElixir (mesma prioridade do app: db2026 > data/).

Regiões: agregação por código de liga (Korea, China, EMEA, Americas, Pacifico, etc.).
MAJOR: união das ligas LPL, LCK, LEC, CBLOL, LCS, LCP (igual ao resto do projeto).

Uso:
  python scripts/champion_gamelength_by_region.py
    (sem --slices: abre menu na consola para escolher regiões / ALL / MAJOR)
  python scripts/champion_gamelength_by_region.py --slices ALL MAJOR EMEA Korea
  python scripts/champion_gamelength_by_region.py --all-regions   (tudo, sem menu)
  python scripts/champion_gamelength_by_region.py -i              (força menu mesmo com outros args)
  python scripts/champion_gamelength_by_region.py --no-console   (só ficheiro, sem tabela no ecrã)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.lol.db_converter import find_latest_csv
from core.shared.utils import MAJOR_LEAGUES

# Aliases de liga (igual oracle_team_games / atualizar database)
LEAGUE_ALIASES = {
    "Demacia Cup": "LPL",
    "Kespa Cup": "LCK",
    "DCup": "LPL",
    "KeSPA": "LCK",
}

# Mapeamento liga (Oracle code) -> região agregada. Ligas não listadas -> "Outro"
# Ajuste aqui se adicionares novos códigos no CSV.
LEAGUE_TO_REGION: dict[str, str] = {
    # Korea
    "LCK": "Korea",
    "LCKC": "Korea",
    # China
    "LPL": "China",
    # Major-style / global pro (região explícita)
    "LEC": "EMEA",
    "LCS": "Americas",
    "CBLOL": "Americas",
    "LCP": "Pacifico",
    # EMEA (ERL e semelhantes)
    "LFL": "EMEA",
    "LIT": "EMEA",
    "NLC": "EMEA",
    "EBL": "EMEA",
    "LPLOL": "EMEA",
    "LFL2": "EMEA",
    "LRN": "EMEA",
    "LRS": "EMEA",
    "NL": "EMEA",
    "LES": "EMEA",
    "PRM": "EMEA",
    "TCL": "EMEA",
    "AL": "EMEA",
    "EM": "EMEA",
    "HLL": "EMEA",
    "HM": "EMEA",
    "HW": "EMEA",
    "CD": "EMEA",
    "FST": "EMEA",
    "HC": "EMEA",
    "AC": "EMEA",
    "RL": "EMEA",
    "ROL": "EMEA",
    "CCWS": "EMEA",
    # Americas (tier 2+)
    "NACL": "Americas",
    "LAS": "Americas",
    # Pacifico
    "LJL": "Pacifico",
    "VCS": "Pacifico",
    # Eventos / cross-region
    "EWC": "Internacional",
}

MIN_GAMELENGTH = 300  # 5 min; ajusta com --min-gamelength (ex. 600 como noutros scripts)
MIN_GAMES = 1


def _resolve_csv(explicit: Path | None) -> Path:
    if explicit and explicit.is_file():
        return explicit
    p = find_latest_csv()
    if p:
        return Path(p)
    fallback = PROJECT_ROOT / "data" / "2026_LoL_esports_match_data_from_OraclesElixir.csv"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        "CSV não encontrado. Coloca o OraclesElixir em Documents/db2026/ ou passa --csv."
    )


def _normalize_league(s: str) -> str:
    t = str(s).strip()
    return LEAGUE_ALIASES.get(t, t)


def _region_for_league(code: str) -> str:
    u = str(code).strip().upper()
    return LEAGUE_TO_REGION.get(u, "Outro")


def load_player_rows(csv_path: Path, min_gamelength: int) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    need = {"gameid", "league", "champion", "gamelength", "position"}
    miss = need - set(df.columns)
    if miss:
        raise ValueError(f"Colunas em falta no CSV: {miss}")
    if "league" in df.columns:
        df["league"] = df["league"].map(_normalize_league)
    df["league_u"] = df["league"].astype(str).str.strip().str.upper()
    df["region"] = df["league_u"].map(_region_for_league)
    df["is_major"] = df["league_u"].isin({x.upper() for x in MAJOR_LEAGUES})
    pos = df["position"].astype(str).str.strip().str.lower()
    # Linhas de rota (exclui team, bench, trinket, etc., como no OraclesElixir padrão)
    mask_lane = pos.isin({"top", "jng", "mid", "bot", "sup"})
    df = df[mask_lane].copy()
    df = df[df["gamelength"].notna() & (df["gamelength"] >= min_gamelength)]
    df["champion"] = df["champion"].astype(str).str.strip()
    df = df[df["champion"].ne("") & df["champion"].str.lower().ne("nan")]
    return df


def _agg_champion_by_scope(sub: pd.DataFrame) -> pd.DataFrame:
    g = (
        sub.groupby("champion", as_index=False)
        .agg(
            mean_gamelength_s=("gamelength", "mean"),
            n_games=("gamelength", "count"),
        )
    )
    g["mean_gamelength_min"] = g["mean_gamelength_s"] / 60.0
    g["mean_gamelength_s"] = g["mean_gamelength_s"].round(1)
    g["mean_gamelength_min"] = g["mean_gamelength_min"].round(2)
    return g.sort_values("champion")


def _print_results_table(long: pd.DataFrame, title: str) -> None:
    print()
    print(title)
    with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 200):
        print(long.to_string(index=False))
    print()


def run_slices(
    df: pd.DataFrame,
    slices: list[str],
    min_games: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for name in slices:
        name_u = name.strip().upper()
        if name_u == "ALL":
            sub = df
        elif name_u == "MAJOR":
            sub = df[df["is_major"]]
        else:
            # região (comparação case-insensitive)
            reg = name.strip()
            sub = df[df["region"].str.lower() == reg.lower()]
        if sub.empty:
            continue
        part = _agg_champion_by_scope(sub)
        part = part[part["n_games"] >= min_games]
        if name_u == "ALL":
            sc = "ALL"
        elif name_u == "MAJOR":
            sc = "MAJOR"
        else:
            sc = str(sub["region"].iloc[0]) if not sub.empty else name.strip()
        part.insert(0, "scope", sc)
        rows.append(part)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def default_slice_list(df: pd.DataFrame) -> list[str]:
    out = ["ALL", "MAJOR"]
    for r in sorted(df["region"].dropna().unique()):
        if r and str(r).strip():
            out.append(str(r).strip())
    return out


def _menu_options(df: pd.DataFrame) -> list[str]:
    """Ordem fixa: ALL, MAJOR, depois regiões presentes no dataset (A-Z)."""
    reg = sorted({str(x).strip() for x in df["region"].dropna().unique() if str(x).strip()})
    return ["ALL", "MAJOR", *reg]


def _parse_menu_numbers(line: str) -> list[int] | None:
    """Se a linha for só índices (1,2  ou 1-3), devolve 1-based; senão None."""
    s = line.strip().replace(" ", "")
    if not s or not re.match(r"^[\d,\-]+$", s):
        return None
    try:
        parts = [p for p in s.split(",") if p]
        selected: set[int] = set()
        for p in parts:
            if "-" in p[1:]:
                a, b = p.split("-", 1)
                if not a or not b:
                    return None
                ia, ib = int(a), int(b)
                for k in range(min(ia, ib), max(ia, ib) + 1):
                    selected.add(k)
            else:
                selected.add(int(p))
        return sorted(selected)
    except ValueError:
        return None


def prompt_slices_interactive(df: pd.DataFrame) -> list[str]:
    """
    Pede as regiões na consola. Aceita:
    - Números: 1,2,3 ou 1,3,5-7
    - Nomes: MAJOR EMEA (várias palavras, separadas por espaço)
    - a / tudo / all = menu completo
    """
    opts = _menu_options(df)
    print("\n--- Escolhe os escopos (regiões) ---")
    for i, name in enumerate(opts, start=1):
        print(f"  {i:2}  {name}")
    print(
        "\nNúmeros: ex. 1,2,4  ou  2,5-8  |  Nomes: ex. MAJOR EMEA  |  a = todos\n"
    )
    uopts = {o.lower(): o for o in opts}
    while True:
        line = input("> ").strip()
        if not line:
            print("Repete com alguma opção.")
            continue
        low = line.lower()
        if low in ("a", "all", "tudo", "todos", "*"):
            return opts
        nums = _parse_menu_numbers(line)
        if nums is not None:
            bad = [k for k in nums if k < 1 or k > len(opts)]
            if bad:
                print(f"Índices têm de ser de 1 a {len(opts)}. Corrige: {bad}")
                continue
            return [opts[k - 1] for k in nums]
        # Nomes (tokens separados por espaço)
        out: list[str] = []
        bad_token = False
        for t in line.split():
            k = t.lower()
            if k in uopts:
                out.append(uopts[k])
                continue
            match = [o for o in opts if o.lower() == k or o.lower().startswith(k)]
            if len(match) == 1:
                out.append(match[0])
            else:
                print(
                    f"Não encontrei '{t}'. Opções: {', '.join(opts)}. "
                    f"({len(match)} matches se ambíguo)"
                )
                bad_token = True
                break
        if bad_token:
            continue
        if not out:
            print("Nenhum nome válido. Usa números (1,2) ou MAJOR EMEA, etc.")
            continue
        return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Média de gamelength por campeão e região / MAJOR")
    ap.add_argument("--csv", type=Path, default=None, help="Caminho do CSV OraclesElixir")
    ap.add_argument(
        "-o", "--output", type=Path, default=None, help="CSV de saída (formato longo)"
    )
    ap.add_argument(
        "--pivot", action="store_true", help="Em vez de longo, tabela larga: campeão x scope (min)"
    )
    ap.add_argument(
        "--slices",
        nargs="*",
        default=None,
        help="Escopos: ALL, MAJOR, e nomes de região (se omitir, abre o menu interativo)",
    )
    ap.add_argument(
        "--all-regions",
        action="store_true",
        help="Inclui ALL, MAJOR e todas as regiões do dataset (sem menu; ignora interativo)",
    )
    ap.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Força o menu de escolha mesmo se passares outras opções (útil a testar)",
    )
    ap.add_argument("--min-games", type=int, default=MIN_GAMES, help="Mínimo de jogos por campeão no corte")
    ap.add_argument("--min-gamelength", type=int, default=MIN_GAMELENGTH, help="Duração mínima (s)")
    ap.add_argument(
        "--no-console",
        action="store_true",
        help="Não mostra tabela no terminal (só grava CSV; por defeito a tabela aparece no ecrã)",
    )
    args = ap.parse_args()
    csv_path = _resolve_csv(args.csv)
    print(f"CSV: {csv_path}")
    df = load_player_rows(csv_path, min_gamelength=args.min_gamelength)
    print(f"Linhas (jogadores válidos): {len(df)} | Partidas (aprox.): {df['gameid'].nunique()}")

    if args.all_regions:
        slices = default_slice_list(df)
    elif args.interactive:
        # -i força o menu; ignora --slices
        slices = prompt_slices_interactive(df)
    elif args.slices:
        slices = list(args.slices)
    else:
        slices = prompt_slices_interactive(df)
    if not slices:
        print("Nada selecionado, a sair.")
        return
    long = run_slices(df, slices, args.min_games)
    if long.empty:
        print("Sem dados para os slices pedidos.")
        return

    out = args.output
    if out is None:
        out = PROJECT_ROOT / "data" / "champion_mean_gamelength_by_region.csv"

    n_champs = long["champion"].nunique()
    scopes = ", ".join(str(s) for s in sorted(long["scope"].unique()))
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.pivot:
        pv = long.pivot_table(
            index="champion",
            columns="scope",
            values="mean_gamelength_min",
            aggfunc="first",
        )
        # Ordem: mais partidas (max entre escopos) -> menos
        gmax = long.groupby("champion", observed=True)["n_games"].max()
        ch_order = gmax.sort_values(ascending=False).index
        pv = pv.reindex(ch_order)
        if not args.no_console:
            _print_results_table(
                pv.reset_index(),
                f"Média duração (min) | {scopes} | {n_champs} campeões (mais jogos primeiro, tabela: {len(pv)} linhas)",
            )
        pv.to_csv(out)
        print(f"Gravado (pivot, min): {out}")
    else:
        # Por escopo: n_games decrescente; empate -> nome A-Z
        long_out = long.sort_values(
            by=["scope", "n_games", "champion"],
            ascending=[True, False, True],
        )
        if not args.no_console:
            _print_results_table(
                long_out,
                f"Média duração por campeão (s e min) | {scopes} — mais jogos (n_games) primeiro, por escopo",
            )
        long_out.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"Gravado (formato longo): {out}  |  linhas: {len(long_out)}  |  campeões: {n_champs}")


if __name__ == "__main__":
    main()
