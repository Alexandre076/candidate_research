import zipfile
from pathlib import Path


def extract_all_raw_zips(
    raw_dir: Path = Path("data/raw"),
    extracted_dir: Path = Path("data/extracted")
):
    """
    Lê todos os arquivos .zip em 'raw_dir' e extrai apenas os PDFs
    diretamente na pasta correspondente à UF em 'extracted_dir/{UF}/'.
    """
    # 1. Garante que os diretórios existem
    if not raw_dir.exists():
        print(f"[ERRO] Diretório de origem '{raw_dir}' não existe.")
        return

    extracted_dir.mkdir(parents=True, exist_ok=True)

    # 2. Busca todos os arquivos .zip no diretório bruto
    zip_files = sorted(list(raw_dir.glob("certidao_criminal_*.zip")))

    if not zip_files:
        print(f"Nenhum arquivo .zip encontrado em '{raw_dir}'.")
        return

    print(f"Encontrados {len(zip_files)} arquivos .zip para processar.\n")

    total_geral_pdfs = 0

    for zip_path in zip_files:
        # Extrai a UF do nome do arquivo (ex: certidao_criminal_2026_ES.zip -> 'ES')
        # Pega a última parte separada por underline antes da extensão
        uf = zip_path.stem.split("_")[-1].upper()
        
        # Pasta de destino: data/extracted/ES/
        uf_dir = extracted_dir / uf
        uf_dir.mkdir(parents=True, exist_ok=True)

        print(f"[{uf}] Processando '{zip_path.name}'...")

        try:
            pdfs_extraidos = 0
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    # Ignora se for pasta interna
                    if member.is_dir():
                        continue

                    filename = Path(member.filename).name

                    # Filtra apenas os arquivos PDF
                    if filename.lower().endswith(".pdf"):
                        caminho_final = uf_dir / filename

                        # Escreve o PDF diretamente na pasta da UF
                        with zip_ref.open(member) as source, open(caminho_final, "wb") as target:
                            target.write(source.read())
                        
                        pdfs_extraidos += 1

            total_geral_pdfs += pdfs_extraidos
            print(f"[{uf}] Sucesso: {pdfs_extraidos} PDFs extraídos em '{uf_dir}'\n")

        except zipfile.BadZipFile:
            print(f"[{uf}] [ERRO]: O arquivo {zip_path.name} está corrompido ou incompleto.\n")
        except Exception as e:
            print(f"[{uf}] [ERRO] inesperado: {e}\n")

    print("=" * 40)
    print(f"Processamento finalizado!")
    print(f"Total de PDFs extraídos: {total_geral_pdfs}")
    print(f"Local: {extracted_dir.resolve()}")


if __name__ == "__main__":
    extract_all_raw_zips()
