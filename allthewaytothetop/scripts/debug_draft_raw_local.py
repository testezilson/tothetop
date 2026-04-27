"""
Compara com POST /api/debug/draft-raw no Railway (mesmo input no Swagger).

Uso (a partir desta pasta, com o venv do projeto ativado):

  cd C:\\Users\\Lucas\\Documents\\lol_oracle_ml_v3\\allthewaytothetop
  python scripts/debug_draft_raw_local.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Raiz = pasta que contém core/ e main.py (igual ao FastAPI)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.lol.draft import LoLDraftAnalyzer  # noqa: E402


def main() -> None:
    a = LoLDraftAnalyzer()
    r = a.analyze_draft(
        league="MAJOR",
        threshold=0.55,
        team1=["Rumble", "Nocturne", "Ryze", "Kalista", "Renata Glasc"],
        team2=["Ornn", "Pantheon", "Anivia", "Sivir", "Neeko"],
    )
    if r is None:
        print("analyze_draft retornou None", file=sys.stderr)
        raise SystemExit(1)
    out = {
        "league": r.get("league"),
        "kills_estimados": r.get("kills_estimados"),
        "resultados": r.get("resultados"),
        "impactos_individuais": r.get("impactos_individuais"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
