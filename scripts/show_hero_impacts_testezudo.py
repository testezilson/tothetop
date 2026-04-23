#!/usr/bin/env python3
"""
Mostra impacto e quantidade de jogos de todos os heróis (aba TESTE).
Fonte: hero_impacts_bayesian_single.pkl — um impacto por herói, sem lado (Radiant/Dire).

Uso (na raiz do projeto):
  python scripts/show_hero_impacts_testezudo.py
"""
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from core.dota.draft_testezudo import TESTEZUDO_DIR

SINGLE_PKL = "hero_impacts_bayesian_single.pkl"


def main():
    d = Path(TESTEZUDO_DIR) if isinstance(TESTEZUDO_DIR, str) else TESTEZUDO_DIR
    pkl_path = d / SINGLE_PKL
    if not pkl_path.exists():
        print(f"Arquivo nao encontrado: {pkl_path}")
        print("Rode no testezudo: python compute_hero_impacts_bayesian_v2_5.py")
        return 1

    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    if not isinstance(data, dict):
        print("Formato inesperado do .pkl")
        return 1

    heroes = {k: v for k, v in data.items() if k != "_meta" and isinstance(v, dict)}
    if not heroes:
        print("Nenhum heroi encontrado no arquivo.")
        return 1

    rows = []
    for name, v in heroes.items():
        impact = v.get("impact", 0.0) or 0.0
        games = v.get("games", 0) or 0
        rows.append((name, impact, games))

    rows.sort(key=lambda r: r[0].lower())

    print()
    print("=" * 60)
    print("IMPACTO E JOGOS DOS HEROIS (aba TESTE - sem lado)")
    print("=" * 60)
    print(f"Fonte: {pkl_path.resolve()}")
    print(f"Total de herois: {len(rows)}")
    print("(Um impacto por heroi: todos os jogos, um shrink bayesiano)")
    print("=" * 60)
    print(f"{'Hero':<22} {'Impacto':>10} {'Jogos':>8}")
    print("-" * 60)

    for name, impact, games in rows:
        print(f"{name:<22} {impact:>+10.2f} {games:>8}")

    print("-" * 60)

    # Top 20 maior impacto e top 20 menor impacto
    by_impact = sorted(rows, key=lambda r: r[1], reverse=True)
    print()
    print("=" * 60)
    print("TOP 20 MAIOR IMPACTO")
    print("=" * 60)
    print(f"{'#':<4} {'Hero':<22} {'Impacto':>10} {'Jogos':>8}")
    print("-" * 60)
    for i, (name, impact, games) in enumerate(by_impact[:20], 1):
        print(f"{i:<4} {name:<22} {impact:>+10.2f} {games:>8}")
    print("-" * 60)

    print()
    print("=" * 60)
    print("TOP 20 MENOR IMPACTO")
    print("=" * 60)
    print(f"{'#':<4} {'Hero':<22} {'Impacto':>10} {'Jogos':>8}")
    print("-" * 60)
    for i, (name, impact, games) in enumerate(by_impact[-20:][::-1], 1):
        print(f"{i:<4} {name:<22} {impact:>+10.2f} {games:>8}")
    print("-" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
