"""
Script para atualizar a database Oracle com novos jogos de um arquivo CSV.

Funcionalidades:
- Combina dados novos com dados existentes
- Remove duplicatas baseado em gameid
- Mapeia ligas: Demacia Cup -> LPL, Kespa Cup -> LCK
- Salva o arquivo atualizado
"""

import pandas as pd
import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
EXISTING_DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

# Mapeamento de ligas
LEAGUE_MAPPING = {
    "Demacia Cup": "LPL",
    "Kespa Cup": "LCK",
    "DCup": "LPL",
    "KeSPA": "LCK"
}

def process_csv_file(input_path):
    """Processa um arquivo CSV e retorna DataFrame processado"""
    print(f"[OK] Carregando arquivo: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"[OK] Total de linhas carregadas: {len(df)}")
    
    # Verificar colunas essenciais
    required_cols = ["league", "gameid", "teamname", "champion", "teamkills"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"[ERRO] Colunas faltando no CSV: {missing}")
    
    # Aplicar mapeamento de ligas
    print(f"\n[OK] Aplicando mapeamento de ligas...")
    for old_league, new_league in LEAGUE_MAPPING.items():
        count = (df["league"] == old_league).sum()
        if count > 0:
            df.loc[df["league"] == old_league, "league"] = new_league
            print(f"   {old_league} -> {new_league}: {count} linhas atualizadas")
    
    # Manter apenas colunas relevantes
    keep_cols = [
        "league", "date", "split", "playoffs", "gameid",
        "teamname", "result", "teamkills", "totalgold", "champion"
    ]
    df = df[[c for c in keep_cols if c in df.columns]].copy()
    
    # Remover linhas sem campeão
    before = len(df)
    df = df[df["champion"].notna()].copy()
    after = len(df)
    if before != after:
        print(f"[OK] Removidas {before - after} linhas sem campeao")
    
    return df

def build_team_picks(group):
    """Reconstrói picks por time (1 linha por time, com pick1–pick5)"""
    picks = list(group["champion"].values)[:5]
    while len(picks) < 5:
        picks.append(None)
    
    return pd.Series({
        "gameid": group["gameid"].iloc[0],
        "league": group["league"].iloc[0],
        "date": group["date"].iloc[0] if "date" in group.columns and pd.notna(group["date"].iloc[0]) else None,
        "split": group["split"].iloc[0] if "split" in group.columns and pd.notna(group["split"].iloc[0]) else None,
        "playoffs": group["playoffs"].iloc[0] if "playoffs" in group.columns and pd.notna(group["playoffs"].iloc[0]) else None,
        "teamname": group["teamname"].iloc[0],
        "teamkills": group["teamkills"].iloc[0],
        "pick1": picks[0],
        "pick2": picks[1],
        "pick3": picks[2],
        "pick4": picks[3],
        "pick5": picks[4]
    })

def process_to_team_format(df):
    """Processa DataFrame para formato de times"""
    print(f"\n[OK] Reconstruindo drafts por time...")
    df_team = (
        df.groupby(["gameid", "teamname"])
        .apply(build_team_picks)
        .reset_index(drop=True)
    )
    
    # Atribuir adversários
    print(f"[OK] Atribuindo adversarios...")
    df_team["opponent"] = None
    for gid, group in df_team.groupby("gameid"):
        if len(group) == 2:
            t1, t2 = group["teamname"].iloc[0], group["teamname"].iloc[1]
            df_team.loc[group.index[0], "opponent"] = t2
            df_team.loc[group.index[1], "opponent"] = t1
    
    # Calcular total_kills
    print(f"[OK] Calculando total de kills por partida...")
    df_total = df_team.groupby("gameid")["teamkills"].sum().reset_index(name="total_kills")
    df_team = df_team.merge(df_total, on="gameid", how="left")
    
    return df_team

def main():
    print("=== Atualizador de Database - LoL Oracle ML v3 ===\n")
    
    # Obter caminho do arquivo novo
    if len(sys.argv) > 1:
        new_file_path = sys.argv[1]
    else:
        try:
            new_file_path = input("Digite o caminho do arquivo CSV com os novos jogos: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("[ERRO] Caminho do CSV não fornecido e modo não-interativo.")
            print("[INFO] Use: python atualizar_database.py <caminho_do_csv>")
            return
    
    # Remover aspas se houver
    new_file_path = new_file_path.strip('"').strip("'")
    
    # Verificar se é um diretório
    if os.path.isdir(new_file_path):
        print(f"[INFO] O caminho fornecido e um diretorio. Procurando arquivos CSV...")
        csv_files = [f for f in os.listdir(new_file_path) if f.endswith('.csv')]
        if csv_files:
            print(f"\n[OK] Arquivos CSV encontrados no diretorio:")
            for i, f in enumerate(csv_files, 1):
                full_path = os.path.join(new_file_path, f)
                file_size = os.path.getsize(full_path) / (1024 * 1024)  # MB
                print(f"   {i}. {f} ({file_size:.2f} MB)")
            
            if len(csv_files) == 1:
                # Se houver apenas um arquivo, usar automaticamente
                new_file_path = os.path.join(new_file_path, csv_files[0])
                print(f"\n[OK] Usando unico arquivo encontrado: {csv_files[0]}")
            else:
                # Se houver múltiplos, pedir para escolher
                try:
                    escolha = input(f"\nEscolha o numero do arquivo (1-{len(csv_files)}) ou 'q' para sair: ").strip()
                    if escolha.lower() == 'q':
                        print("[INFO] Operacao cancelada.")
                        return
                    escolha_num = int(escolha)
                    if 1 <= escolha_num <= len(csv_files):
                        new_file_path = os.path.join(new_file_path, csv_files[escolha_num - 1])
                        print(f"[OK] Arquivo selecionado: {csv_files[escolha_num - 1]}")
                    else:
                        print(f"[ERRO] Numero invalido. Use um numero entre 1 e {len(csv_files)}")
                        return
                except (ValueError, EOFError, KeyboardInterrupt):
                    print(f"[ERRO] Entrada invalida ou modo não-interativo.")
                    print(f"[INFO] Use: python atualizar_database.py <caminho_do_csv>")
                    return
        else:
            print(f"[ERRO] Nenhum arquivo CSV encontrado no diretorio: {new_file_path}")
            return
    
    # Se não tem extensão .csv, tentar adicionar
    if not new_file_path.lower().endswith('.csv'):
        # Verificar se existe sem extensão
        if os.path.exists(new_file_path):
            print(f"[AVISO] Arquivo sem extensao .csv. Tentando adicionar extensao...")
            new_file_path_with_csv = new_file_path + '.csv'
            if os.path.exists(new_file_path_with_csv):
                new_file_path = new_file_path_with_csv
                print(f"[OK] Usando: {new_file_path}")
            else:
                print(f"[ERRO] Arquivo nao encontrado: {new_file_path}")
                print(f"[ERRO] Tambem nao encontrado com .csv: {new_file_path_with_csv}")
                return
        else:
            # Tentar adicionar .csv
            new_file_path_with_csv = new_file_path + '.csv'
            if os.path.exists(new_file_path_with_csv):
                new_file_path = new_file_path_with_csv
                print(f"[OK] Arquivo encontrado com extensao .csv: {new_file_path}")
            else:
                print(f"[ERRO] Arquivo nao encontrado: {new_file_path}")
                print(f"[ERRO] Tambem nao encontrado com .csv: {new_file_path_with_csv}")
                return
    
    if not os.path.exists(new_file_path):
        print(f"[ERRO] Arquivo nao encontrado: {new_file_path}")
        print(f"[INFO] Verifique se o caminho esta correto e se o arquivo existe.")
        return
    
    if not os.path.isfile(new_file_path):
        print(f"[ERRO] O caminho fornecido nao e um arquivo: {new_file_path}")
        return
    
    # Processar arquivo novo
    print(f"\n{'='*60}")
    print(f"PROCESSANDO ARQUIVO NOVO")
    print(f"{'='*60}")
    df_new = process_csv_file(new_file_path)
    df_new_processed = process_to_team_format(df_new)
    print(f"[OK] {len(df_new_processed)} times processados ({len(df_new_processed)//2} partidas)")
    
    # Carregar dados existentes
    df_existing = None
    if os.path.exists(EXISTING_DATA_PATH):
        print(f"\n{'='*60}")
        print(f"CARREGANDO DADOS EXISTENTES")
        print(f"{'='*60}")
        print(f"[OK] Carregando: {EXISTING_DATA_PATH}")
        df_existing = pd.read_csv(EXISTING_DATA_PATH)
        print(f"[OK] Total de linhas existentes: {len(df_existing)}")
        print(f"[OK] Total de partidas existentes: {df_existing['gameid'].nunique()}")
    else:
        print(f"\n[AVISO] Arquivo existente nao encontrado. Criando novo arquivo.")
    
    # Combinar dados
    print(f"\n{'='*60}")
    print(f"COMBINANDO DADOS")
    print(f"{'='*60}")
    
    if df_existing is not None:
        # Combinar e remover duplicatas
        df_combined = pd.concat([df_existing, df_new_processed], ignore_index=True)
        print(f"[OK] Total de linhas apos combinacao: {len(df_combined)}")
        
        # Remover duplicatas baseado em gameid + teamname
        before = len(df_combined)
        df_combined = df_combined.drop_duplicates(subset=["gameid", "teamname"], keep="last")
        after = len(df_combined)
        duplicates_removed = before - after
        print(f"[OK] Duplicatas removidas: {duplicates_removed} linhas")
        
        # Estatísticas
        unique_games_before = df_existing['gameid'].nunique()
        unique_games_after = df_combined['gameid'].nunique()
        new_games = unique_games_after - unique_games_before
        
        print(f"\n[OK] Estatisticas:")
        print(f"   Partidas antes: {unique_games_before}")
        print(f"   Partidas depois: {unique_games_after}")
        print(f"   Novas partidas adicionadas: {new_games}")
    else:
        df_combined = df_new_processed
        print(f"[OK] Usando apenas dados novos")
    
    # Salvar arquivo atualizado
    print(f"\n{'='*60}")
    print(f"SALVANDO ARQUIVO ATUALIZADO")
    print(f"{'='*60}")
    
    # Criar backup do arquivo existente
    if os.path.exists(EXISTING_DATA_PATH):
        backup_path = EXISTING_DATA_PATH.replace(".csv", "_backup.csv")
        print(f"[OK] Criando backup: {backup_path}")
        df_existing.to_csv(backup_path, index=False)
    
    # Salvar arquivo atualizado
    df_combined.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de linhas finais: {len(df_combined)}")
    print(f"[OK] Total de partidas finais: {df_combined['gameid'].nunique()}")
    
    # Estatísticas por liga
    print(f"\n{'='*60}")
    print(f"ESTATISTICAS POR LIGA")
    print(f"{'='*60}")
    stats = df_combined.groupby("league")["gameid"].nunique().sort_values(ascending=False)
    for league, n_games in stats.items():
        print(f"   {league}: {n_games} partidas")
    
    print(f"\n{'='*60}")
    print(f"[OK] Atualizacao concluida com sucesso!")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
