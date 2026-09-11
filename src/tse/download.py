from pathlib import Path
import time

BASE_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "certidao_criminal/certidao_criminal_2026_{}.zip"
)

UFs = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO"
]

def download_certificate(uf: str, session,
                         output_dir: Path = Path("data/raw")):
    url = BASE_URL.format(uf)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"certidao_criminal_2026_{uf}.zip"

    print(f"Downloading {uf}...")
    print(f"URL: {url}")

    try:
        # impersonate="chrome120" emula a assinatura TLS exata do navegador
        response = session.get(
            url,
            stream=True,
            timeout=120,
            headers={
                "Referer": "https://dadosabertos.tse.jus.br/"
            }
        )

        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")

        if response.status_code == 403 or "text/html" in response.headers.get("Content-Type", ""):
            print(f"[ERRO] Acesso negado para {uf}.\n")
            return

        response.raise_for_status()

        temporary = output_file.with_suffix(output_file.suffix + ".tmp")
        with open(temporary, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)
        temporary.replace(output_file)

        print(f"Saved: {output_file}\n")

    except Exception as e:
        print(f"[ERRO] Falha ao baixar {uf}: {e}\n")


if __name__ == "__main__":
    from curl_cffi import requests
    # Inicializa sessão com impersonate nativo
    with requests.Session(impersonate="chrome120") as session:
        # Faz uma chamada inicial na raiz para estabelecer contexto de navegação
        session.get("https://dadosabertos.tse.jus.br/", timeout=15)

        # Teste com um único estado
        #download_certificate("AP", session)

        # Para baixar todos em lote:
        for uf in UFs:
            download_certificate(uf, session)
            time.sleep(2)
