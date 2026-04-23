"""
Script de teste para verificar se os paths estão funcionando corretamente.
Execute: python test_paths.py
"""
import sys
import os

# Simular modo frozen
sys.frozen = True
sys.executable = r"C:\Users\Lucas\Documents\lol_oracle_ml_v3\dist\LoLOracleML.exe"
sys._MEIPASS = r"C:\Users\Lucas\AppData\Local\Temp\_MEI93362"

# Adicionar src ao path
sys.path.insert(0, 'src')

from core.shared.paths import get_base_dir, get_data_dir, get_models_dir, path_in_data, path_in_models

print("=== TESTE DE PATHS ===")
print(f"sys.frozen: {getattr(sys, 'frozen', False)}")
print(f"sys.executable: {sys.executable}")
print(f"sys._MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
print()
print(f"BASE_DIR: {get_base_dir()}")
print(f"DATA_DIR: {get_data_dir()}")
print(f"MODELS_DIR: {get_models_dir()}")
print()
print(f"path_in_data('champion_impacts.csv'): {path_in_data('champion_impacts.csv')}")
print(f"  Existe: {os.path.exists(path_in_data('champion_impacts.csv'))}")
print()
print(f"path_in_models('trained_models_v3.pkl'): {path_in_models('trained_models_v3.pkl')}")
print(f"  Existe: {os.path.exists(path_in_models('trained_models_v3.pkl'))}")
print()
print("=== VERIFICANDO DIRETÓRIOS ===")
data_dir = get_data_dir()
models_dir = get_models_dir()
print(f"data_dir existe: {os.path.exists(data_dir)}")
print(f"models_dir existe: {os.path.exists(models_dir)}")
if os.path.exists(data_dir):
    print(f"Arquivos em data_dir: {os.listdir(data_dir)[:5]}")
if os.path.exists(models_dir):
    print(f"Arquivos em models_dir: {os.listdir(models_dir)[:5]}")
