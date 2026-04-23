"""
Script para mapear ligas na database Oracle.

Mapeamentos:
- DCup -> LPL
- KeSPA -> LCK
"""

import pandas as pd
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

# Mapeamento de ligas
LEAGUE_MAPPING = {
    "DCup": "LPL",
    "KeSPA": "LCK"
}

def main():
    print("=== Mapeador de Ligas - LoL Oracle ML v3 ===\n")
    
    # Carregar dados
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return
    
    print(f"[OK] Carregando dados de {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    print(f"[OK] Total de linhas carregadas: {len(df)}")
    
    # Estatísticas antes do mapeamento
    print(f"\n{'='*60}")
    print(f"ESTATISTICAS ANTES DO MAPEAMENTO")
    print(f"{'='*60}")
    stats_before = df.groupby("league")["gameid"].nunique().sort_values(ascending=False)
    for league, n_games in stats_before.items():
        if league in LEAGUE_MAPPING:
            print(f"   {league}: {n_games} partidas [SERA MAPEADO]")
        else:
            print(f"   {league}: {n_games} partidas")
    
    # Aplicar mapeamento
    print(f"\n{'='*60}")
    print(f"APLICANDO MAPEAMENTO")
    print(f"{'='*60}")
    
    total_mapped = 0
    for old_league, new_league in LEAGUE_MAPPING.items():
        count = (df["league"] == old_league).sum()
        if count > 0:
            df.loc[df["league"] == old_league, "league"] = new_league
            n_games = df[df["league"] == new_league]["gameid"].nunique()
            print(f"[OK] {old_league} -> {new_league}: {count} linhas atualizadas ({n_games} partidas)")
            total_mapped += count
        else:
            print(f"[AVISO] {old_league} nao encontrado na database")
    
    if total_mapped == 0:
        print(f"[AVISO] Nenhuma liga foi mapeada. Verifique se as ligas existem na database.")
        return
    
    # Estatísticas depois do mapeamento
    print(f"\n{'='*60}")
    print(f"ESTATISTICAS DEPOIS DO MAPEAMENTO")
    print(f"{'='*60}")
    stats_after = df.groupby("league")["gameid"].nunique().sort_values(ascending=False)
    for league, n_games in stats_after.items():
        if league in ["LPL", "LCK"]:
            print(f"   {league}: {n_games} partidas [ATUALIZADO]")
        else:
            print(f"   {league}: {n_games} partidas")
    
    # Criar backup
    backup_path = DATA_PATH.replace(".csv", "_backup_antes_mapeamento.csv")
    print(f"\n{'='*60}")
    print(f"CRIANDO BACKUP")
    print(f"{'='*60}")
    
    # Carregar arquivo original novamente para backup
    df_original = pd.read_csv(DATA_PATH)
    df_original.to_csv(backup_path, index=False)
    print(f"[OK] Backup criado em: {backup_path}")
    
    # Salvar arquivo atualizado
    print(f"\n{'='*60}")
    print(f"SALVANDO ARQUIVO ATUALIZADO")
    print(f"{'='*60}")
    df.to_csv(DATA_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {DATA_PATH}")
    print(f"[OK] Total de linhas: {len(df)}")
    print(f"[OK] Total de partidas: {df['gameid'].nunique()}")
    
    # Resumo
    print(f"\n{'='*60}")
    print(f"RESUMO")
    print(f"{'='*60}")
    print(f"   Linhas mapeadas: {total_mapped}")
    print(f"   LPL agora tem: {stats_after.get('LPL', 0)} partidas")
    print(f"   LCK agora tem: {stats_after.get('LCK', 0)} partidas")
    print(f"\n[OK] Mapeamento concluido com sucesso!")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
