# manual_draft_predict.py
import math
import pandas as pd

IMPACTS_PATH = "data/champion_impacts.csv"

THRESHOLDS = [25.5, 26.5, 27.5, 28.5, 29.5, 30.5, 31.5, 32.5]

def z_to_cdf(z: float) -> float:
    # CDF normal padrão via erf
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def confidence_from_prob(p_under: float) -> str:
    if p_under > 0.70 or p_under < 0.30:
        return "High"
    elif 0.30 <= p_under <= 0.70:
        return "Medium"
    # (não deve cair aqui, mas só por segurança)
    return "Low"

def load_impacts() -> pd.DataFrame:
    df = pd.read_csv(IMPACTS_PATH)
    # Esperado: ['league','champion','avg_kills_with_champ','league_avg_kills','league_std_kills','games_played','impact']
    missing = {"league","champion","league_avg_kills","league_std_kills","impact"} - set(df.columns)
    if missing:
        raise ValueError(f"Arquivo {IMPACTS_PATH} sem colunas: {sorted(missing)}")
    # normaliza nomes
    df["league"] = df["league"].astype(str).str.upper().str.strip()
    df["champion_norm"] = df["champion"].astype(str).str.strip()
    return df

def get_ch_impact(df_imp: pd.DataFrame, league: str, champion: str):
    # retorna (impacto, jogos, media_liga, std_liga, motivo)
    sub = df_imp[(df_imp["league"] == league) & (df_imp["champion_norm"].str.casefold() == champion.casefold())]
    if sub.empty:
        # não achou na liga: impacto 0 e explica motivo
        liga_rows = df_imp[df_imp["league"] == league]
        if liga_rows.empty:
            return 0.0, 0, None, None, f"Sem dados da liga {league} no arquivo."
        return 0.0, 0, float(liga_rows["league_avg_kills"].iloc[0]), float(liga_rows["league_std_kills"].iloc[0]), "Campeão não encontrado nesta liga (impacto=0)."
    row = sub.iloc[0]
    return float(row["impact"]), int(row.get("games_played", 0)), float(row["league_avg_kills"]), float(row["league_std_kills"]), "OK"

def predict_for_lines(predicted_kills: float, league_std: float, threshold: float):
    results = []
    for line in THRESHOLDS:
        # P(UNDER) = P(Total <= line) ~ Phi((line - mu)/sigma)
        z = (line - predicted_kills) / (league_std if league_std and league_std > 1e-6 else 8.0)
        p_under = z_to_cdf(z)
        conf = confidence_from_prob(p_under)
        bet_under = p_under >= threshold
        results.append({
            "line": line,
            "prob_under": p_under,
            "bet": "UNDER" if bet_under else "OVER",
            "confidence": conf
        })
    return results

def fmt_pct(x: float) -> str:
    # mostra em porcentagem com 1 casa
    return f"{x*100:5.1f}%"

def main():
    df_imp = load_impacts()

    print("📂 Carregando impactos por liga e campeão...")
    leagues = sorted(df_imp["league"].unique())
    print(f"✅ {len(df_imp)} campeões carregados de {len(leagues)} ligas.\n")

    print("🎮 PREDIÇÃO MANUAL DE DRAFT (modelo original Evaristo)")
    league_in = input("Digite a liga (ex: LPL, LCK, LEC): ").strip().upper() or "LPL"
    try:
        threshold = float(input("Digite o threshold (padrão = 0.55): ").strip() or "0.55")
    except:
        threshold = 0.55

    # Entrada dos times
    print("\nDigite os campeões do Time 1:")
    t1 = {
        "top": input("  TOP: ").strip(),
        "jung": input("  JUNG: ").strip(),
        "mid": input("  MID: ").strip(),
        "adc": input("  ADC: ").strip(),
        "sup": input("  SUP: ").strip(),
    }
    print("\nDigite os campeões do Time 2:")
    t2 = {
        "top": input("  TOP: ").strip(),
        "jung": input("  JUNG: ").strip(),
        "mid": input("  MID: ").strip(),
        "adc": input("  ADC: ").strip(),
        "sup": input("  SUP: ").strip(),
    }

    # Coleta impactos e estatísticas da liga
    impacts_t1, notes_t1 = [], []
    impacts_t2, notes_t2 = [], []

    league_avg, league_std = None, None

    for role in ["top","jung","mid","adc","sup"]:
        imp, gp, l_avg, l_std, msg = get_ch_impact(df_imp, league_in, t1[role])
        impacts_t1.append((role, t1[role], imp, gp, msg))
        if l_avg is not None: league_avg = l_avg
        if l_std is not None: league_std = l_std

    for role in ["top","jung","mid","adc","sup"]:
        imp, gp, l_avg, l_std, msg = get_ch_impact(df_imp, league_in, t2[role])
        impacts_t2.append((role, t2[role], imp, gp, msg))
        if l_avg is not None: league_avg = l_avg
        if l_std is not None: league_std = l_std

    if league_avg is None or league_std is None:
        # fallback de segurança
        league_avg = float(df_imp[df_imp["league"] == league_in]["league_avg_kills"].iloc[0]) if not df_imp[df_imp["league"] == league_in].empty else 28.0
        league_std = float(df_imp[df_imp["league"] == league_in]["league_std_kills"].iloc[0]) if not df_imp[df_imp["league"] == league_in].empty else 8.0

    total_impact_t1 = sum(x[2] for x in impacts_t1)
    total_impact_t2 = sum(x[2] for x in impacts_t2)

    predicted_kills = league_avg + (total_impact_t1 + total_impact_t2)/2.0

    # Impressão dos impactos por campeão (lado a lado)
    print("\n--- IMPACTO DOS CAMPEÕES ---")
    labels = {"top":"TOP ","jung":"JUNG","mid":"MID ","adc":"ADC ","sup":"SUP "}
    for i in range(5):
        r1, ch1, imp1, gp1, msg1 = impacts_t1[i]
        r2, ch2, imp2, gp2, msg2 = impacts_t2[i]
        print(f"{labels[r1]} {ch1:<12}: {imp1:+.2f}   |   {ch2:<12}: {imp2:+.2f}")
    print(f"\n⚖️ Impacto total: Time 1 = {total_impact_t1:+.2f} | Time 2 = {total_impact_t2:+.2f}")
    print(f"📊 Média base da liga {league_in}: {league_avg:.2f}")
    print(f"🎯 Kills estimados: {predicted_kills:.2f}")

    # Resultados por linha
    results = predict_for_lines(predicted_kills, league_std, threshold)

    print("\n--- RESULTADOS COMPLETOS ---")
    for r in results:
        line = r["line"]
        p = r["prob_under"]
        bet = r["bet"]
        conf = r["confidence"]
        print(f"Linha {line:5.1f}: {bet:<5} | Prob(UNDER): {fmt_pct(p):>6} | Confiança: {conf}")

    # Observações de dados ausentes
    missing_msgs = [n for _,_,_,_,n in impacts_t1+impacts_t2 if n and n != "OK"]
    if missing_msgs:
        print("\nℹ️ Notas sobre dados:")
        for note in sorted(set(missing_msgs)):
            print(f"  - {note}")

if __name__ == "__main__":
    main()
