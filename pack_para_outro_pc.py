"""
Empacota o projeto LoL & Dota Oracle ML + todos os arquivos externos (DBs, Dota, testezudo)
para rodar em outro computador. Não altera nenhum path do projeto.

Gera uma pasta "LoL_Dota_Oracle_Pacote_Viagem" e um ZIP.
Para os caminhos do programa funcionarem, extraia o ZIP de forma que a pasta
'Lucas' fique em C:\\Users\\ (resultando em C:\\Users\\Lucas\\Documents\\..., etc.).

Uso: python pack_para_outro_pc.py
"""
import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

# Diretório deste script = raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent

# Pasta de saída (será criada e depois zipada)
OUTPUT_FOLDER_NAME = "LoL_Dota_Oracle_Pacote_Viagem"
# Dentro dela: pasta "Lucas" que deve ser extraída em C:\Users\
LUCAS = "Lucas"
USER_HOME = Path(os.path.expanduser("~"))  # C:\Users\Lucas

# Caminhos externos: (origem absoluta, destino relativo à pasta Lucas)
EXTERNAL_PATHS = [
    (USER_HOME / "Documents" / "db2026", Path("Documents") / "db2026"),
    (USER_HOME / "Documents" / "oracle_2025.db", Path("Documents") / "oracle_2025.db"),
    (USER_HOME / "Documents" / "final", Path("Documents") / "final"),
    (USER_HOME / "Documents" / "testezudo", Path("Documents") / "testezudo"),
    (USER_HOME / "lol" / "data", Path("lol") / "data"),
]

# O que NÃO copiar do projeto
PROJECT_EXCLUDE = {
    ".git",
    "__pycache__",
    ".cursor",
    "venv",
    "node_modules",
    ".zip",
    OUTPUT_FOLDER_NAME,
    "LoL_Dota_Oracle_Pacote_Viagem.zip",
}
# Também não incluir pastas dist se quiser pacote menor (descomente para incluir dist)
# PROJECT_EXCLUDE.add("dist")


def should_skip(path: Path, base: Path) -> bool:
    rel = path.relative_to(base) if path.is_relative_to(base) else path
    parts = rel.parts
    return any(p in PROJECT_EXCLUDE for p in parts)


def copy_tree(src: Path, dst: Path, exclude: set):
    """Copia árvore ignorando pastas em exclude."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in exclude:
            continue
        dest_item = dst / item.name
        if item.is_dir():
            copy_tree(item, dest_item, exclude)
        else:
            shutil.copy2(item, dest_item)


def copy_external(src: Path, dst: Path, base_out: Path):
    """Copia arquivo ou pasta externa para base_out/dst."""
    if not src.exists():
        print(f"  [AVISO] Não encontrado: {src}")
        return
    dest_full = base_out / dst
    if src.is_file():
        dest_full.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_full)
        print(f"  OK: {src.name} -> {dst}")
    else:
        if dest_full.exists():
            shutil.rmtree(dest_full)
        # Ignorar venv para evitar caminhos longos e tamanho desnecessário (no outro PC pode recriar)
        def ignore(d, names):
            return [n for n in names if n in ("__pycache__", ".git", "venv", "node_modules") or n.endswith(".pyc")]
        shutil.copytree(src, dest_full, ignore=ignore)
        print(f"  OK: {src} -> {dst}")


def main():
    out_base = PROJECT_ROOT / OUTPUT_FOLDER_NAME
    lucas_base = out_base / LUCAS

    print("Empacotando projeto + arquivos externos...")
    print(f"Saída: {out_base}\n")

    if out_base.exists():
        shutil.rmtree(out_base)
    out_base.mkdir(parents=True)

    # 1) Projeto completo em Documents\lol_oracle_ml_v3
    project_dest = lucas_base / "Documents" / "lol_oracle_ml_v3"
    print("[1/2] Copiando projeto lol_oracle_ml_v3...")
    copy_tree(PROJECT_ROOT, project_dest, PROJECT_EXCLUDE)
    print("  Projeto copiado.\n")

    # 2) Arquivos externos (mesma estrutura que o código espera)
    print("[2/2] Copiando arquivos externos (db2026, Dota, testezudo, lol/data)...")
    for src_abs, dst_rel in EXTERNAL_PATHS:
        copy_external(src_abs, dst_rel, lucas_base)

    # 3) README na raiz do pacote
    readme = out_base / "LEIA-ME_ANTES_DE_EXTRAIR.txt"
    readme.write_text(
        "LoL & Dota Oracle ML - Pacote para outro PC\n"
        "============================================\n\n"
        "O programa usa caminhos fixos no código. Para funcionar no outro computador:\n\n"
        "1) Extraia este ZIP em algum lugar (ex: Área de Trabalho).\n\n"
        "2) Mova a pasta 'Lucas' que está dentro desta pasta para dentro de C:\\Users\\\n"
        "    Ou seja, o resultado deve ser:\n"
        "    - C:\\Users\\Lucas\\Documents\\db2026\n"
        "    - C:\\Users\\Lucas\\Documents\\final\\dota_oracle_v1\\...\n"
        "    - C:\\Users\\Lucas\\Documents\\testezudo\n"
        "    - C:\\Users\\Lucas\\Documents\\lol_oracle_ml_v3  (projeto)\n"
        "    - C:\\Users\\Lucas\\lol\\data (se existir)\n\n"
        "3) Se no outro PC o usuário do Windows NÃO for 'Lucas':\n"
        "    - Crie a pasta C:\\Users\\Lucas e coloque dentro dela as pastas\n"
        "      'Documents' e 'lol' que estão dentro da pasta 'Lucas' deste pacote.\n"
        "    - Ou renomeie sua pasta de usuário para Lucas (não recomendado).\n\n"
        "4) Rodar o programa:\n"
        "    - Pelo executável: abra C:\\Users\\Lucas\\Documents\\lol_oracle_ml_v3\\dist\\LoLOracleML\n"
        "      e execute o .exe, se tiver sido empacotado.\n"
        "    - Em desenvolvimento: abra a pasta lol_oracle_ml_v3, crie/ative o venv,\n"
        "      pip install -r requirements.txt, e rode python -m app.main.\n\n"
        "5) As pastas 'final' (Dota) e 'testezudo' foram copiadas SEM a pasta venv.\n"
        "    Se for rodar os scripts de atualização de banco (Dota/CyberScore, etc.)\n"
        "    no outro PC, crie um venv em cada projeto e instale as dependências.\n\n"
        "Nenhum path do projeto foi alterado; apenas os arquivos foram reunidos.\n",
        encoding="utf-8"
    )
    print(f"\n  README criado: {readme.name}")

    # 4) ZIP
    zip_name = f"{OUTPUT_FOLDER_NAME}.zip"
    zip_path = PROJECT_ROOT / zip_name
    print(f"\nCriando {zip_name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(out_base):
            for name in dirs:
                if name in ("__pycache__", ".git"):
                    continue
            for name in files:
                full = Path(root) / name
                arcname = full.relative_to(out_base)
                zf.write(full, arcname)
    print(f"ZIP criado: {zip_path}")

    print("\nConcluído. Leia LEIA-ME_ANTES_DE_EXTRAIR.txt no pacote ou no ZIP.")


if __name__ == "__main__":
    main()
