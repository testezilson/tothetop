"""
Script para criar um arquivo ZIP do projeto (ou de pastas que você indicar).
Uso: python create_zip.py
      python create_zip.py pasta_para_compactar
"""
import zipfile
import sys
from pathlib import Path
from datetime import datetime

# Pastas/arquivos que não entram no ZIP
EXCLUIR = {".git", "__pycache__", ".venv", "venv", "node_modules", ".cursor", ".zip"}

def criar_zip(origem: Path, destino: Path) -> None:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for arq in origem.rglob("*"):
            if not arq.is_file():
                continue
            if any(parte in arq.parts for parte in EXCLUIR):
                continue
            zf.write(arq, arq.relative_to(origem.parent))
    print(f"ZIP criado: {destino.resolve()}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pasta = Path(sys.argv[1])
        if not pasta.exists():
            print(f"Pasta não encontrada: {pasta}")
            sys.exit(1)
    else:
        pasta = Path(__file__).resolve().parent

    nome = pasta.name + "_" + datetime.now().strftime("%Y%m%d_%H%M") + ".zip"
    destino = pasta.parent / nome
    criar_zip(pasta, destino)
