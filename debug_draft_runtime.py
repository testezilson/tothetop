"""
Runtime do Draft: paths, CSV usado por find_latest_csv, shape do DF e n por campeão (MAJOR).

Uso (na raiz do projeto mãe):

  cd C:\\Users\\Lucas\\Documents\\lol_oracle_ml_v3
  $env:PYTHONPATH = "src"
  python debug_draft_runtime.py

Ou: python debug_draft_runtime.py  (o script adiciona src ao path)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_src = _ROOT / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from core.lol.db_converter import find_latest_csv  # noqa: E402
from core.lol.draft import LoLDraftAnalyzer  # noqa: E402
from core.lol.oracle_team_games import get_draft_oracle_dataframe  # noqa: E402
from core.shared.paths import BASE_DIR, path_in_data, path_in_models  # noqa: E402


def main() -> None:
    print("BASE_DIR:", BASE_DIR)
    print("DATA_DIR:", path_in_data(""))
    print("MODELS_DIR:", path_in_models(""))
    csv_used = find_latest_csv()
    print("find_latest_csv():", csv_used)
    if csv_used and os.path.isfile(csv_used):
        print("  size_bytes:", os.path.getsize(csv_used))

    df = get_draft_oracle_dataframe()
    print("DF shape:", None if df is None else df.shape)
    if df is not None and not df.empty and "league" in df.columns:
        print("Leagues:", sorted(str(x) for x in df["league"].dropna().unique()))

    champs = [
        "Rumble",
        "Nocturne",
        "Ryze",
        "Kalista",
        "Renata Glasc",
        "Ornn",
        "Pantheon",
        "Anivia",
        "Sivir",
        "Neeko",
    ]
    major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]

    a = LoLDraftAnalyzer()
    a.load_models()

    for c in champs:
        n = a._count_games_in_oracle(major, c)
        print(c, "n=", n)


if __name__ == "__main__":
    main()
