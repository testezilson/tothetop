"""
Script master para atualizar o banco de dados e regenerar todas as estatísticas
necessárias para analisar_jogos_v4.py e compare_compositions.py

Este script:
1. Atualiza oracle_prepared.csv com novos jogos do CSV fornecido
2. Regenera todos os arquivos de estatísticas necessários
"""

import os
import sys
import subprocess
import pandas as pd

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

def atualizar_oracle_prepared(csv_path):
    """Atualiza oracle_prepared.csv usando a lógica do atualizar_database.py"""
    print("\n" + "="*70)
    print("PASSO 1: ATUALIZANDO ORACLE_PREPARED.CSV")
    print("="*70)
    
    # Importar e executar a lógica do atualizar_database.py
    sys.path.insert(0, BASE_DIR)
    from atualizar_database import process_csv_file, process_to_team_format
    
    EXISTING_DATA_PATH = os.path.join(DATA_DIR, "oracle_prepared.csv")
    OUTPUT_PATH = os.path.join(DATA_DIR, "oracle_prepared.csv")
    
    # Processar arquivo novo
    print(f"\n[OK] Processando arquivo: {csv_path}")
    df_new = process_csv_file(csv_path)
    df_new_processed = process_to_team_format(df_new)
    print(f"[OK] {len(df_new_processed)} times processados ({len(df_new_processed)//2} partidas)")
    
    # Carregar dados existentes
    df_existing = None
    if os.path.exists(EXISTING_DATA_PATH):
        print(f"[OK] Carregando dados existentes: {EXISTING_DATA_PATH}")
        df_existing = pd.read_csv(EXISTING_DATA_PATH)
        print(f"[OK] Total de linhas existentes: {len(df_existing)}")
        print(f"[OK] Total de partidas existentes: {df_existing['gameid'].nunique()}")
    else:
        print(f"[AVISO] Arquivo existente não encontrado. Criando novo arquivo.")
    
    # Combinar dados
    if df_existing is not None:
        df_combined = pd.concat([df_existing, df_new_processed], ignore_index=True)
        print(f"[OK] Total de linhas após combinação: {len(df_combined)}")
        
        # Remover duplicatas
        before = len(df_combined)
        df_combined = df_combined.drop_duplicates(subset=["gameid", "teamname"], keep="last")
        after = len(df_combined)
        duplicates_removed = before - after
        print(f"[OK] Duplicatas removidas: {duplicates_removed} linhas")
        
        unique_games_before = df_existing['gameid'].nunique()
        unique_games_after = df_combined['gameid'].nunique()
        new_games = unique_games_after - unique_games_before
        
        print(f"\n[OK] Estatísticas:")
        print(f"   Partidas antes: {unique_games_before}")
        print(f"   Partidas depois: {unique_games_after}")
        print(f"   Novas partidas adicionadas: {new_games}")
    else:
        df_combined = df_new_processed
        print(f"[OK] Usando apenas dados novos")
    
    # Criar backup
    if os.path.exists(EXISTING_DATA_PATH):
        backup_path = EXISTING_DATA_PATH.replace(".csv", "_backup.csv")
        print(f"[OK] Criando backup: {backup_path}")
        df_existing.to_csv(backup_path, index=False)
    
    # Salvar arquivo atualizado
    df_combined.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de linhas finais: {len(df_combined)}")
    print(f"[OK] Total de partidas finais: {df_combined['gameid'].nunique()}")
    
    return True

def executar_script(script_path, descricao):
    """Executa um script Python e retorna True se sucesso"""
    print(f"\n[OK] Executando: {descricao}")
    print(f"     Script: {script_path}")
    
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        if result.stderr:
            print(f"[AVISO] Warnings/Errors: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] Falha ao executar {script_path}")
        print(f"       Erro: {e}")
        print(f"       Output: {e.stdout}")
        print(f"       Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"[ERRO] Erro inesperado ao executar {script_path}: {e}")
        return False

def main():
    print("="*70)
    print("ATUALIZADOR COMPLETO - LoL Oracle ML v3")
    print("="*70)
    print("\nEste script irá:")
    print("  1. Atualizar oracle_prepared.csv com novos jogos")
    print("  2. Regenerar champion_impacts.csv")
    print("  3. Regenerar league_stats_v3.pkl")
    print("  4. Regenerar champion_synergies_simples.pkl")
    print("  5. Regenerar matchup_synergies_simple.pkl")
    print("  6. Regenerar champion_winrates.csv")
    print("  7. Regenerar synergy_winrates.csv")
    print("  8. Regenerar composition_winrates.csv")
    print("  9. Regenerar matchup_winrates.csv")
    print("="*70)
    
    # Obter caminho do arquivo CSV
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = input("\nDigite o caminho do arquivo CSV com os jogos de 2024: ").strip()
    
    # Remover aspas se houver
    csv_path = csv_path.strip('"').strip("'")
    
    # Verificar se é um diretório
    if os.path.isdir(csv_path):
        print(f"[INFO] O caminho fornecido é um diretório. Procurando arquivos CSV...")
        csv_files = [f for f in os.listdir(csv_path) if f.endswith('.csv')]
        if csv_files:
            print(f"\n[OK] Arquivos CSV encontrados no diretório:")
            for i, f in enumerate(csv_files, 1):
                full_path = os.path.join(csv_path, f)
                file_size = os.path.getsize(full_path) / (1024 * 1024)  # MB
                print(f"   {i}. {f} ({file_size:.2f} MB)")
            
            if len(csv_files) == 1:
                csv_path = os.path.join(csv_path, csv_files[0])
                print(f"\n[OK] Usando único arquivo encontrado: {csv_files[0]}")
            else:
                try:
                    escolha = input(f"\nEscolha o número do arquivo (1-{len(csv_files)}) ou 'q' para sair: ").strip()
                    if escolha.lower() == 'q':
                        print("[INFO] Operação cancelada.")
                        return
                    escolha_num = int(escolha)
                    if 1 <= escolha_num <= len(csv_files):
                        csv_path = os.path.join(csv_path, csv_files[escolha_num - 1])
                        print(f"[OK] Arquivo selecionado: {csv_files[escolha_num - 1]}")
                    else:
                        print(f"[ERRO] Número inválido. Use um número entre 1 e {len(csv_files)}")
                        return
                except (ValueError, EOFError):
                    print(f"[ERRO] Entrada inválida.")
                    return
        else:
            print(f"[ERRO] Nenhum arquivo CSV encontrado no diretório: {csv_path}")
            return
    
    # Verificar se arquivo existe
    if not os.path.exists(csv_path):
        print(f"[ERRO] Arquivo não encontrado: {csv_path}")
        return
    
    if not os.path.isfile(csv_path):
        print(f"[ERRO] O caminho fornecido não é um arquivo: {csv_path}")
        return
    
    # PASSO 1: Atualizar oracle_prepared.csv
    if not atualizar_oracle_prepared(csv_path):
        print("[ERRO] Falha ao atualizar oracle_prepared.csv. Abortando.")
        return
    
    # PASSO 2: Regenerar arquivos para analisar_jogos_v4.py
    print("\n" + "="*70)
    print("PASSO 2: REGENERANDO ARQUIVOS PARA analisar_jogos_v4.py")
    print("="*70)
    
    scripts_v4 = [
        ("src/generate_champion_impacts.py", "Impactos de Campeões"),
        ("src/build_league_stats_v3.py", "Estatísticas de Ligas"),
        ("apps/gerar_sinergias_simples.py", "Sinergias Simples"),
        ("apps/gerar_sinergias_matchup_simples.py", "Matchups Simples"),
    ]
    
    for script, desc in scripts_v4:
        if not executar_script(script, desc):
            print(f"[AVISO] Falha ao gerar {desc}, mas continuando...")
    
    # PASSO 3: Regenerar arquivos para compare_compositions.py
    print("\n" + "="*70)
    print("PASSO 3: REGENERANDO ARQUIVOS PARA compare_compositions.py")
    print("="*70)
    
    scripts_compare = [
        ("src/generate_champion_winrates.py", "Win Rates de Campeões"),
        ("src/generate_synergy_winrates.py", "Win Rates de Sinergias"),
        ("src/generate_composition_winrates.py", "Win Rates de Composições"),
        ("src/generate_matchup_winrates.py", "Win Rates de Matchups"),
    ]
    
    for script, desc in scripts_compare:
        if not executar_script(script, desc):
            print(f"[AVISO] Falha ao gerar {desc}, mas continuando...")
    
    # Resumo final
    print("\n" + "="*70)
    print("RESUMO FINAL")
    print("="*70)
    
    arquivos_necessarios = {
        "analisar_jogos_v4.py": [
            "data/oracle_prepared.csv",
            "data/champion_impacts.csv",
            "data/league_stats_v3.pkl",
            "data/champion_synergies_simples.pkl",
            "data/matchup_synergies_simple.pkl",
        ],
        "compare_compositions.py": [
            "data/oracle_prepared.csv",
            "data/champion_winrates.csv",
            "data/synergy_winrates.csv",
            "data/composition_winrates.csv",
            "data/matchup_winrates.csv",
        ]
    }
    
    print("\nVerificando arquivos necessários:")
    todos_ok = True
    for script, arquivos in arquivos_necessarios.items():
        print(f"\n  {script}:")
        for arquivo in arquivos:
            caminho = os.path.join(BASE_DIR, arquivo)
            existe = os.path.exists(caminho)
            status = "✅" if existe else "❌"
            print(f"    {status} {arquivo}")
            if not existe:
                todos_ok = False
    
    if todos_ok:
        print("\n" + "="*70)
        print("✅ ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!")
        print("="*70)
        print("\nTodos os arquivos foram atualizados e regenerados.")
        print("Agora você pode usar:")
        print("  - apps/analisar_jogos_v4.py")
        print("  - compare_compositions.py")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("⚠️ ATUALIZAÇÃO CONCLUÍDA COM AVISOS")
        print("="*70)
        print("\nAlguns arquivos podem estar faltando. Verifique os erros acima.")
        print("="*70)

if __name__ == "__main__":
    main()
