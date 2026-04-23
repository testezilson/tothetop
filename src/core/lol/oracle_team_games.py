"""
Monta um DataFrame no formato de oracle_prepared (1 linha por time) a partir do CSV
Oracle's Elixir completo, usando o mesmo critério de partidas válidas que compute_champion_metrics_lol.

Prioridade de arquivo: find_latest_csv() (exe / db2026 / data). Cache em memória por mtime.
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from core.lol.db_converter import find_latest_csv

# Igual atualizar_database.py — normalizar nomes de ligas
LEAGUE_MAPPING = {
    "Demacia Cup": "LPL",
    "Kespa Cup": "LCK",
    "DCup": "LPL",
    "KeSPA": "LCK",
}

MIN_GAMELENGTH = 600

_cache_path: Optional[str] = None
_cache_mtime: Optional[float] = None
_cache_df: Optional[pd.DataFrame] = None


def invalidate_oracle_team_games_cache() -> None:
    global _cache_path, _cache_mtime, _cache_df
    _cache_path = None
    _cache_mtime = None
    _cache_df = None


def _apply_league_mapping(df: pd.DataFrame) -> pd.DataFrame:
    for old_league, new_league in LEAGUE_MAPPING.items():
        df.loc[df["league"] == old_league, "league"] = new_league
    return df


def build_team_game_dataframe_from_elixir(df: pd.DataFrame) -> pd.DataFrame:
    """Participantid 100/200, gamelength >= MIN_GAMELENGTH, 5 picks por lado."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    if "league" not in df.columns or "gameid" not in df.columns:
        return pd.DataFrame()
    df = _apply_league_mapping(df)

    blue = df[df["participantid"] == 100].copy()
    red = df[df["participantid"] == 200].copy()
    if blue.empty or red.empty:
        return pd.DataFrame()

    need_red = [
        "gameid",
        "teamname",
        "teamkills",
        "pick1",
        "pick2",
        "pick3",
        "pick4",
        "pick5",
    ]
    if not all(c in red.columns for c in need_red):
        return pd.DataFrame()

    red_sub = red[need_red].rename(
        columns={
            "teamname": "red_teamname",
            "teamkills": "red_teamkills",
            "pick1": "red_pick1",
            "pick2": "red_pick2",
            "pick3": "red_pick3",
            "pick4": "red_pick4",
            "pick5": "red_pick5",
        }
    )
    merged = blue.merge(red_sub, on="gameid", how="inner")

    rows: list[dict] = []
    for _, row in merged.iterrows():
        gl = row.get("gamelength")
        if pd.isna(gl) or float(gl) < MIN_GAMELENGTH:
            continue

        picks_b = [
            str(row.get(f"pick{i}")).strip()
            for i in range(1, 6)
            if pd.notna(row.get(f"pick{i}")) and str(row.get(f"pick{i}")).strip()
        ]
        picks_r = [
            str(row.get(f"red_pick{i}")).strip()
            for i in range(1, 6)
            if pd.notna(row.get(f"red_pick{i}")) and str(row.get(f"red_pick{i}")).strip()
        ]
        if len(picks_b) < 5 or len(picks_r) < 5:
            continue

        tk_b = int(row.get("teamkills") or 0)
        tk_r = int(row.get("red_teamkills") or 0)
        total_kills = tk_b + tk_r

        bname = row.get("teamname")
        rname = row.get("red_teamname")
        if pd.isna(bname) or pd.isna(rname):
            continue
        bname = str(bname).strip()
        rname = str(rname).strip()

        date = row.get("date")
        split = row.get("split") if "split" in row.index else None
        playoffs = row.get("playoffs") if "playoffs" in row.index else None
        league = row.get("league")
        if pd.isna(league):
            league = ""
        else:
            league = str(league).strip()

        gid = row["gameid"]

        rows.append(
            {
                "gameid": gid,
                "league": league,
                "date": date,
                "split": split,
                "playoffs": playoffs,
                "teamname": bname,
                "teamkills": tk_b,
                "pick1": picks_b[0],
                "pick2": picks_b[1],
                "pick3": picks_b[2],
                "pick4": picks_b[3],
                "pick5": picks_b[4],
                "opponent": rname,
                "total_kills": total_kills,
            }
        )
        rows.append(
            {
                "gameid": gid,
                "league": league,
                "date": date,
                "split": split,
                "playoffs": playoffs,
                "teamname": rname,
                "teamkills": tk_r,
                "pick1": picks_r[0],
                "pick2": picks_r[1],
                "pick3": picks_r[2],
                "pick4": picks_r[3],
                "pick5": picks_r[4],
                "opponent": bname,
                "total_kills": total_kills,
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def get_team_games_from_latest_elixir_csv(force_reload: bool = False) -> Optional[pd.DataFrame]:
    """
    Lê o CSV Oracle's Elixir mais recente e devolve DataFrame estilo oracle_prepared.
    Retorna None se não houver CSV ou se o processamento falhar.
    """
    global _cache_path, _cache_mtime, _cache_df

    path = find_latest_csv()
    if not path or not os.path.isfile(path):
        return None

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    if (
        not force_reload
        and _cache_df is not None
        and _cache_path == path
        and _cache_mtime == mtime
    ):
        return _cache_df

    try:
        raw = pd.read_csv(path, low_memory=False)
    except Exception:
        return None

    built = build_team_game_dataframe_from_elixir(raw)
    if built is None or built.empty:
        return None

    _cache_path = path
    _cache_mtime = mtime
    _cache_df = built
    return _cache_df


def get_draft_oracle_dataframe(force_reload: bool = False) -> pd.DataFrame:
    """
    Fonte para Draft Live / Compare: CSV bruto recente; se indisponível, oracle_prepared.csv.
    """
    live = get_team_games_from_latest_elixir_csv(force_reload=force_reload)
    if live is not None and not live.empty:
        return live

    from core.shared.paths import path_in_data

    fallback = path_in_data("oracle_prepared.csv")
    if os.path.isfile(fallback):
        try:
            return pd.read_csv(fallback, low_memory=False)
        except Exception:
            pass
    return pd.DataFrame()


def compute_kills_impact_from_team_games(
    df: pd.DataFrame,
    leagues_list: list,
    champ: str,
    min_games: int = 5,
) -> tuple[Optional[float], int]:
    """
    Igual a generate_champion_impacts.py: impacto = média(total_kills | campeão na comp)
    menos média de total_kills em todas as aparições (cada pick conta uma observação).
    Retorna (impacto, n_partidas_com_campeão); impacto None se n < min_games ou sem dados.
    """
    if df is None or df.empty or "total_kills" not in df.columns:
        return None, 0

    leagues = list(leagues_list)
    d = df[df["league"].isin(leagues)].copy()
    if d.empty:
        return None, 0

    champ_cf = str(champ).casefold()
    all_kills: list[float] = []
    for _, row in d.iterrows():
        tk = row["total_kills"]
        if pd.isna(tk):
            continue
        fv = float(tk)
        for i in range(1, 6):
            p = row.get(f"pick{i}")
            if pd.isna(p):
                continue
            if str(p).strip():
                all_kills.append(fv)
    if not all_kills:
        return None, 0
    league_avg = sum(all_kills) / len(all_kills)

    champ_kills: list[float] = []
    for _, row in d.iterrows():
        picks = [
            str(row.get(f"pick{i}")).strip()
            for i in range(1, 6)
            if pd.notna(row.get(f"pick{i}")) and str(row.get(f"pick{i}")).strip()
        ]
        if any(p.casefold() == champ_cf for p in picks):
            tk = row["total_kills"]
            if pd.isna(tk):
                continue
            champ_kills.append(float(tk))

    n = len(champ_kills)
    if n < min_games:
        return None, n
    champ_avg = sum(champ_kills) / n
    return float(champ_avg - league_avg), n


def load_draft_champion_name_list() -> list[str]:
    """
    Nomes de campeão para UI (Draft Live, etc.): picks do CSV bruto / oracle_prepared
    mais champion_impacts.csv.
    """
    names: set[str] = set()
    df = get_draft_oracle_dataframe()
    if df is not None and not df.empty:
        for i in range(1, 6):
            col = f"pick{i}"
            if col not in df.columns:
                continue
            for v in df[col].dropna().unique():
                s = str(v).strip()
                if s:
                    names.add(s)

    from core.shared.paths import path_in_data

    path_csv = path_in_data("champion_impacts.csv")
    if path_csv and os.path.isfile(path_csv):
        try:
            cdf = pd.read_csv(path_csv, low_memory=False)
            cdf.columns = cdf.columns.str.strip().str.lower()
            if "champion" in cdf.columns:
                for c in cdf["champion"].dropna().unique():
                    s = str(c).strip()
                    if s:
                        names.add(s)
        except Exception:
            pass

    return sorted(names, key=str.casefold)
