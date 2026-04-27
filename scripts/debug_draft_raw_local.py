"""
Compara com POST /api/debug/draft-raw (mesmo input no Swagger do Railway).

Projeto mãe (src em PYTHONPATH):
  cd C:\\Users\\Lucas\\Documents\\lol_oracle_ml_v3
  $env:PYTHONPATH = "src"
  python scripts/debug_draft_raw_local.py

Repositório web (allthewaytothetop) — use o script cópia em:
  allthewaytothetop/scripts/debug_draft_raw_local.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

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
    # JSON para copiar e comparar com a API (valores numéricos nativos)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
