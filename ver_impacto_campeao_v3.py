import os
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.path.join(BASE_DIR, "data", "champion_impacts.csv")

def main():
    print("=== 🔍 Ver Impacto de Campeão - LoL Oracle ML v3 ===\n")

    # Carregar dataset e normalizar nomes das colunas
    try:
        df = pd.read_csv(CSV_PATH)
        df.columns = df.columns.str.strip().str.lower()  # remove espaços e padroniza
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado em {CSV_PATH}")
        return

    print(f"✅ Arquivo carregado ({len(df)} registros totais)\n")

    # Checar colunas obrigatórias
    required_cols = ["league", "champion", "impact", "games_played"]
    for col in required_cols:
        if col not in df.columns:
            print(f"⚠️ Coluna '{col}' não encontrada no CSV. Colunas detectadas: {list(df.columns)}")
            return

    league = input("Liga (ex: LCK, LPL, LEC, CBLOL, MSI, WORLDS): ").strip()
    champ = input("Campeão (ex: Mordekaiser, Lee Sin, Orianna): ").strip()

    # Filtrar liga
    subset_league = df[df["league"].str.lower() == league.lower()]
    if subset_league.empty:
        print(f"\n⚠️ Nenhuma informação encontrada para a liga {league}.")
        return

    # Calcular impacto médio da liga
    avg_impact_league = subset_league["impact"].mean()
    print(f"\n📈 Impacto médio geral da liga {league}: {avg_impact_league:+.2f}")

    # Buscar campeão específico
    subset_champ = subset_league[subset_league["champion"].str.lower() == champ.lower()]
    if subset_champ.empty:
        print(f"\n⚠️ Nenhum dado encontrado para {champ} na liga {league}.")
    else:
        row = subset_champ.iloc[0]
        print("\n📊 Dados encontrados:")
        print(f"   🏳️ Liga: {row['league']}")
        print(f"   🧙 Campeão: {row['champion']}")
        print(f"   🎮 Jogos com o campeão: {int(row['games_played'])}")
        print(f"   💥 Impacto médio: {row['impact']:+.2f}")
        if row['impact'] > 1.5:
            print("🗣️ Interpretação: Campeão tende a jogos sangrentos (↑ chance de OVER).")
        elif row['impact'] < -1.5:
            print("🗣️ Interpretação: Campeão tende a jogos controlados (↑ chance de UNDER).")
        else:
            print("🗣️ Impacto neutro (não altera muito o padrão da liga).")

    # ===== TOP e BOTTOM 20 =====
    print("\n────────────────────────────────────────────")
    print(f"🏆 Top 20 campeões com MAIOR impacto na liga {league}:\n")
    top20 = subset_league.sort_values("impact", ascending=False).head(20)
    for _, r in top20.iterrows():
        print(f"   🟢 {r['champion']:<15} → +{r['impact']:.2f} (n={int(r['games_played'])})")

    print(f"\n💤 Top 20 campeões com MENOR impacto na liga {league}:\n")
    bottom20 = subset_league.sort_values("impact", ascending=True).head(20)
    for _, r in bottom20.iterrows():
        print(f"   🔴 {r['champion']:<15} → {r['impact']:.2f} (n={int(r['games_played'])})")

    print("\n✅ Ranking gerado com sucesso!\n")

if __name__ == "__main__":
    main()
