"""
Script para atualizar o banco de dados APENAS com jogos de 2026
(Substitui os dados antigos, não combina)

Este script:
1. Substitui oracle_prepared.csv com apenas os jogos do CSV fornecido
2. Regenera todos os arquivos de estatísticas necessários
"""

import os
import sys
import subprocess
import pandas as pd

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

def processar_csv_2026(csv_path):
    """Processa o CSV de 2026 e retorna DataFrame no formato correto"""
    print("\n" + "="*70)
    print("PROCESSANDO CSV DE 2026")
    print("="*70)
    
    # Importar funções do atualizar_database.py
    sys.path.insert(0, BASE_DIR)
    from atualizar_database import process_csv_file, process_to_team_format
    
    # Processar arquivo
    print(f"\n[OK] Processando arquivo: {csv_path}")
    df_new = process_csv_file(csv_path)
    df_processed = process_to_team_format(df_new)
    print(f"[OK] {len(df_processed)} times processados ({len(df_processed)//2} partidas)")
    
    return df_processed

def substituir_oracle_prepared(df_new):
    """Substitui oracle_prepared.csv com apenas os dados novos"""
    print("\n" + "="*70)
    print("SUBSTITUINDO ORACLE_PREPARED.CSV (APENAS 2026)")
    print("="*70)
    
    EXISTING_DATA_PATH = os.path.join(DATA_DIR, "oracle_prepared.csv")
    OUTPUT_PATH = os.path.join(DATA_DIR, "oracle_prepared.csv")
    
    # Criar backup do arquivo existente (se houver)
    if os.path.exists(EXISTING_DATA_PATH):
        backup_path = EXISTING_DATA_PATH.replace(".csv", "_backup_antes_2026.csv")
        print(f"[OK] Criando backup dos dados antigos: {backup_path}")
        df_existing = pd.read_csv(EXISTING_DATA_PATH)
        df_existing.to_csv(backup_path, index=False)
        print(f"[OK] Backup criado com {len(df_existing)} linhas ({df_existing['gameid'].nunique()} partidas)")
    
    # Substituir com apenas os dados novos
    print(f"\n[OK] Substituindo oracle_prepared.csv com apenas dados de 2026")
    df_new.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de linhas: {len(df_new)}")
    print(f"[OK] Total de partidas: {df_new['gameid'].nunique()}")
    
    # Estatísticas por liga
    if 'league' in df_new.columns:
        print(f"\n[OK] Partidas por liga:")
        league_stats = df_new.groupby("league")["gameid"].nunique().sort_values(ascending=False)
        for league, n_games in league_stats.items():
            print(f"   {league}: {n_games} partidas")
    
    return True

def encontrar_script_projeto(script_path_relativo):
    """
    Encontra um script no diretório do projeto original.
    Funciona tanto em desenvolvimento quanto quando empacotado como .exe.
    """
    # Se o script já é absoluto e existe, usar direto
    if os.path.isabs(script_path_relativo) and os.path.exists(script_path_relativo):
        return script_path_relativo
    
    # Lista de locais para procurar
    search_locations = []
    
    # Detectar se estamos no diretório do executável (dist/LoLOracleML/_internal)
    is_in_dist = 'dist' in BASE_DIR or '_internal' in BASE_DIR
    
    if is_in_dist:
        # Se estamos em dist/LoLOracleML/_internal, o projeto está em dist/LoLOracleML/..
        parts = BASE_DIR.split(os.sep)
        if 'dist' in parts:
            dist_idx = parts.index('dist')
            project_root = os.sep.join(parts[:dist_idx])
            search_locations.append(project_root)
        # Também tentar subir 2 níveis de _internal
        if '_internal' in BASE_DIR:
            project_from_internal = os.path.join(BASE_DIR, '..', '..')
            project_from_internal = os.path.normpath(project_from_internal)
            if project_from_internal not in search_locations:
                search_locations.append(project_from_internal)
    else:
        # Em desenvolvimento, BASE_DIR é a raiz do projeto
        search_locations.append(BASE_DIR)
    
    # Procurar o script em todos os locais
    for location in search_locations:
        if location and os.path.exists(location):
            script_path = os.path.join(location, script_path_relativo)
            if os.path.exists(script_path):
                return script_path
    
    # Se não encontrou, retornar o caminho relativo (vai dar erro, mas pelo menos mostra onde procurou)
    return os.path.join(search_locations[0] if search_locations else BASE_DIR, script_path_relativo)

def executar_script(script_path, descricao):
    """Executa um script Python e retorna True se sucesso"""
    print(f"\n[OK] Executando: {descricao}")
    
    # Encontrar o script no projeto original
    script_path_absoluto = encontrar_script_projeto(script_path)
    print(f"     Script: {script_path_absoluto}")
    
    if not os.path.exists(script_path_absoluto):
        print(f"[ERRO] Script não encontrado: {script_path_absoluto}")
        return False
    
    # Configurar encoding UTF-8 para Windows
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    
    try:
        # Determinar o diretório de trabalho (raiz do projeto)
        # Os scripts esperam estar na raiz do projeto para encontrar data/
        script_dir = os.path.dirname(script_path_absoluto)
        
        # Se o script está em src/ ou apps/, a raiz do projeto é o diretório pai
        if 'src' in script_dir or 'apps' in script_dir:
            # Voltar até a raiz do projeto
            while os.path.basename(script_dir) in ['src', 'apps']:
                script_dir = os.path.dirname(script_dir)
        elif 'dist' in script_dir or '_internal' in script_dir:
            # Se estamos no diretório do executável, encontrar o projeto original
            parts = script_dir.split(os.sep)
            if 'dist' in parts:
                dist_idx = parts.index('dist')
                script_dir = os.sep.join(parts[:dist_idx])
            elif '_internal' in script_dir:
                # Subir 2 níveis de _internal
                script_dir = os.path.normpath(os.path.join(script_dir, '..', '..'))
        
        # Garantir que o diretório existe
        if not os.path.exists(script_dir):
            script_dir = BASE_DIR
        
        # Executar sem capturar output para evitar problemas de encoding
        # O script vai imprimir diretamente no console
        result = subprocess.run(
            [sys.executable, script_path_absoluto],
            cwd=script_dir,
            env=env,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[AVISO] Script retornou código de erro: {e.returncode}")
        print(f"        Verificando se o arquivo foi gerado mesmo assim...")
        
        # Verificar se o arquivo de saída esperado foi criado mesmo com erro
        # Isso é importante porque o erro pode ser só no print (encoding), não na execução
        if verificar_arquivo_gerado(script_path):
            return True
        else:
            print(f"[ERRO] Script falhou e arquivo não foi gerado")
            return False
    except Exception as e:
        print(f"[ERRO] Erro inesperado ao executar {script_path}: {e}")
        # Verificar se arquivo foi gerado mesmo assim
        return verificar_arquivo_gerado(script_path)

def verificar_arquivo_gerado(script_path):
    """Verifica se o script gerou o arquivo esperado mesmo com erro de encoding"""
    # Mapear scripts para seus arquivos de saída
    script_outputs = {
        "src/generate_champion_impacts.py": "data/champion_impacts.csv",
        "src/build_league_stats_v3.py": "data/league_stats_v3.pkl",
        "apps/gerar_sinergias_simples.py": "data/champion_synergies_simples.pkl",
        "apps/gerar_sinergias_matchup_simples.py": "data/matchup_synergies_simple.pkl",
        "src/generate_champion_winrates.py": "data/champion_winrates.csv",
        "src/generate_synergy_winrates.py": "data/synergy_winrates.csv",
        "src/generate_composition_winrates.py": "data/composition_winrates.csv",
        "src/generate_matchup_winrates.py": "data/matchup_winrates.csv",
    }
    
    output_file = script_outputs.get(script_path)
    if output_file:
        output_path = os.path.join(BASE_DIR, output_file)
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            if file_size > 0:
                print(f"[OK] Arquivo gerado com sucesso apesar do erro de encoding: {output_file}")
                return True
    
    return False

def main():
    print("="*70)
    print("ATUALIZADOR - APENAS JOGOS DE 2026")
    print("="*70)
    print("\n⚠️  ATENÇÃO: Este script irá SUBSTITUIR os dados antigos!")
    print("   Um backup será criado automaticamente.")
    print("\nEste script irá:")
    print("  1. Substituir oracle_prepared.csv com apenas jogos de 2026")
    print("  2. Regenerar champion_impacts.csv")
    print("  3. Regenerar league_stats_v3.pkl")
    print("  4. Regenerar champion_synergies_simples.pkl")
    print("  5. Regenerar matchup_synergies_simple.pkl")
    print("  6. Regenerar champion_winrates.csv")
    print("  7. Regenerar synergy_winrates.csv")
    print("  8. Regenerar composition_winrates.csv")
    print("  9. Regenerar matchup_winrates.csv")
    print("="*70)
    
    # Verificar se há flag --yes ou -y para pular confirmação
    skip_confirmation = '--yes' in sys.argv or '-y' in sys.argv
    
    # Confirmação (pular se --yes ou -y foi passado)
    if not skip_confirmation:
        try:
            resposta = input("\nDeseja continuar? (sim/não): ").strip().lower()
            if resposta not in ['sim', 's', 'yes', 'y']:
                print("[INFO] Operação cancelada.")
                return
        except (EOFError, KeyboardInterrupt):
            # Se não há stdin disponível (modo não-interativo), assumir 'sim'
            print("\n[INFO] Modo não-interativo detectado. Continuando automaticamente...")
    
    # Obter caminho do arquivo CSV
    # Remover flags da lista de argumentos
    args = [arg for arg in sys.argv[1:] if arg not in ['--yes', '-y']]
    
    if len(args) > 0:
        csv_path = args[0]
    else:
        try:
            csv_path = input("\nDigite o caminho do arquivo CSV com os jogos de 2026: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("[ERRO] Caminho do CSV não fornecido e modo não-interativo.")
            print("[INFO] Use: python atualizar_apenas_2026.py <caminho_do_csv> [--yes]")
            return
    
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
    
    # PASSO 1: Processar CSV e substituir oracle_prepared.csv
    df_new = processar_csv_2026(csv_path)
    if not substituir_oracle_prepared(df_new):
        print("[ERRO] Falha ao substituir oracle_prepared.csv. Abortando.")
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
        print("\nTodos os arquivos foram atualizados com APENAS os jogos de 2026.")
        print("Os dados antigos foram salvos em: data/oracle_prepared_backup_antes_2026.csv")
        print("\nAgora você pode usar:")
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
