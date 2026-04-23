"""
Mostra a análise de draft do testezudo (hero_impacts_bayesian_v2_5.pkl) para um draft fixo.
Draft: Radiant = Puck, Jakiro, Windranger, Hoodwink, Bristleback
       Dire = Viper, Slardar, Shadow Shaman, Kez, Techies

Execute a partir da raiz do projeto:
  python scripts/compare_draft_v2_vs_bayesian.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from core.dota.draft_testezudo import DotaDraftTestezudoAnalyzer

# Mesmo draft da imagem (aba TESTE)
RADIANT = ["Puck", "Jakiro", "Windranger", "Hoodwink", "Bristleback"]
DIRE = ["Viper", "Slardar", "Shadow Shaman", "Kez", "Techies"]


def _format_result(r: dict) -> str:
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("ANALISE DE DRAFT (testezudo - hero_impacts_bayesian_v2_5.pkl)")
    lines.append("=" * 70)
    if "error" in r:
        lines.append(f"  ERRO: {r['error']}")
        return "\n".join(lines)
    lines.append("RADIANT (impacto por heroi):")
    for x in r.get("radiant_impacts", []):
        lines.append(f"  {x['hero']:<20} -> {x['impact']:+.2f}  | {x['games']} jogos")
    lines.append("DIRE (impacto por heroi):")
    for x in r.get("dire_impacts", []):
        lines.append(f"  {x['hero']:<20} -> {x['impact']:+.2f}  | {x['games']} jogos")
    lines.append("")
    lines.append("IMPACTO TOTAL DO DRAFT:")
    lines.append(f"  Radiant total: {r.get('radiant_total', 0):+.2f}")
    lines.append(f"  Dire total:    {r.get('dire_total', 0):+.2f}")
    lines.append(f"  Total geral:   {r.get('total_geral', 0):+.2f}")
    lines.append(f"  Kills estimadas (global_mean + draft_total): {r.get('kills_estimadas', 0):.2f}")
    lines.append("")
    lines.append("PREVISOES POR LINHA (amostra):")
    preds = r.get("predictions", {})
    for line in [39.5, 44.5, 45.5, 49.5, 54.5, 59.5]:
        if line in preds:
            p = preds[line]
            fav = p["favorite"]
            prob = (p["prob_over"] * 100) if fav == "OVER" else (p["prob_under"] * 100)
            lines.append(f"  Linha {line:>4.1f}: {fav:>4} | Prob({fav}): {prob:>5.1f}% | {p['confidence']}")
    lines.append("")
    return "\n".join(lines)


def main():
    analyzer = DotaDraftTestezudoAnalyzer()
    if not analyzer.load_models():
        print("Falha ao carregar modelos. Verifique o diretório testezudo e os .pkl.")
        print(analyzer.last_error or "")
        return 1

    print("Draft: Radiant = " + ", ".join(RADIANT))
    print("       Dire    = " + ", ".join(DIRE))

    result = analyzer.analyze_draft(RADIANT, DIRE)
    print(_format_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
