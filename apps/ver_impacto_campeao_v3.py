import os
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMPACTS_PATH = os.path.join(BASE_DIR, "data", "champion_impacts.csv")
ORACLE_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

def main():
    print("=== 🔍 Ver Impacto de Campeão - LoL Oracle ML v3 ===\n")

    # === Carregar impactos ===
    try:
        df = pd.read_csv(IMPACTS_PATH)
        df.columns = df.columns.str.strip().str.lower()
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado em {IMPACTS_PATH}")
        return

    print(f"✅ Arquivo de impactos carregado ({len(df)} registros totais)\n")

    league = input("Liga (ex: LCK, LPL, LEC, CBLOL, MSI, WORLDS): ").strip()
    champ = input("Campeão (ex: Mordekaiser, Lee Sin, Orianna): ").strip()

    subset_league = df[df["league"].str.lower() == league.lower()]
    if subset_league.empty:
        print(f"\n⚠️ Nenhuma informação encontrada para a liga {league}.")
        return

    # Impacto médio da liga
    avg_impact_league = subset_league["impact"].mean()
    print(f"\n📈 Impacto médio geral da liga {league}: {avg_impact_league:+.2f}")

    # Buscar campeão
    subset_champ = subset_league[subset_league["champion"].str.lower() == champ.lower()]
    if subset_champ.empty:
        print(f"\n⚠️ Nenhum dado encontrado para {champ} na liga {league}.")
    else:
        row = subset_champ.iloc[0]
        print("\n📊 Dados encontrados:")
        print(f"   🏳️ Liga: {row['league']}")
        print(f"   🧙 Campeão: {row['champion']}")
        print(f"   🎮 Jogos com o campeão: {int(row['games_played'])}")
        print(f"   ⚔️  Média de kills com o campeão: {row['avg_kills_with_champ']:.2f}")
        print(f"   📈 Média geral da liga: {row['league_avg_kills']:.2f}")
        print(f"   📉 Desvio padrão da liga: {row['league_std_kills']:.2f}")
        imp = row["impact"]
        sinal = "🟢" if imp > 0 else ("🔴" if imp < 0 else "⚪")
        print(f"   💥 Impacto médio: {sinal} {imp:+.2f}\n")

        if imp > 1.5:
            print("🗣️ Interpretação: Campeão tende a jogos sangrentos (↑ chance de OVER).")
        elif imp < -1.5:
            print("🗣️ Interpretação: Campeão tende a jogos controlados (↑ chance de UNDER).")
        else:
            print("🗣️ Impacto neutro (não altera muito o padrão da liga).")

    # === Ranking da liga ===
    print("\n────────────────────────────────────────────")
    print(f"🏆 Top 20 campeões com MAIOR impacto na liga {league}:\n")
    top20 = subset_league.sort_values("impact", ascending=False).head(20)
    for _, r in top20.iterrows():
        print(f"   🟢 {r['champion']:<15} → +{r['impact']:.2f} (n={int(r['games_played'])})")

    print(f"\n💤 Top 20 campeões com MENOR impacto na liga {league}:\n")
    bottom20 = subset_league.sort_values("impact", ascending=True).head(20)
    for _, r in bottom20.iterrows():
        print(f"   🔴 {r['champion']:<15} → {r['impact']:.2f} (n={int(r['games_played'])})")

    # === Histórico de jogos do campeão ===
    print("\n────────────────────────────────────────────")
    print(f"📜 Histórico de jogos do campeão {champ} na liga {league}:\n")

    try:
        oracle = pd.read_csv(ORACLE_PATH)
        oracle.columns = oracle.columns.str.strip().str.lower()

        # Filtrar partidas dessa liga onde o campeão aparece
        mask_league = oracle["league"].str.lower() == league.lower()
        mask_champ = oracle[[f"pick{i}" for i in range(1, 6)]].apply(
            lambda row: champ.lower() in row.astype(str).str.lower().values, axis=1
        )
        subset_hist = oracle[mask_league & mask_champ]

        if subset_hist.empty:
            print("⚠️ Nenhum jogo encontrado para esse campeão na base Oracle.")
        else:
            print(f"✅ {len(subset_hist)} partidas encontradas:\n")
            for _, r in subset_hist.head(30).iterrows():  # mostra até 30 jogos
                print(
                    f"   🆚 {r['teamname']} vs {r['opponent']} → {r['total_kills']} kills totais"
                )

    except FileNotFoundError:
        print(f"⚠️ Arquivo {ORACLE_PATH} não encontrado (histórico não exibido).")

    print("\n✅ Finalizado com sucesso!\n")

if __name__ == "__main__":
    main()
