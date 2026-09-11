"""Diagnóstico e extração nativa de PDFs; não executa OCR nem chama uma LLM."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

import pymupdf


DATA_DIR = Path(__file__).resolve().parent / "data"


def analyze_pdf(path: Path) -> tuple[dict, str]:
    """Retorna diagnóstico por página e texto nativo, preservando sua origem.

    Os limites são heurísticos: a indicação de OCR precisa ser calibrada.
    Texto extraível não garante que todo o conteúdo visual foi recuperado.
    """
    metadata = {"status": "ok", "pages": [], "ocr_executed": False}
    sections = []
    try:
        with path.open("rb") as source:
            metadata["sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError("PDF protegido por senha")
            metadata["page_count"] = len(document)
            for number, page in enumerate(document, 1):
                try:
                    text = page.get_text("text", sort=True)
                    chars = len("".join(text.split()))
                    replacement_ratio = text.count("\ufffd") / max(len(text), 1)
                    page_area = max(abs(page.rect), 1)
                    # Maior imagem evita contar sobreposições duas vezes.
                    # Scans compostos por mosaicos podem exigir revisão adicional.
                    image_coverage = max(
                        (abs(pymupdf.Rect(info["bbox"]) & page.rect) / page_area
                         for info in page.get_image_info()),
                        default=0,
                    )
                    reasons = []
                    if chars < 80:
                        reasons.append("little_or_no_text")
                    if replacement_ratio > 0.01:
                        reasons.append("replacement_characters")
                    if image_coverage >= 0.6:
                        reasons.append("large_image_check_text_completeness")
                    diagnosis = {
                        "page": number,
                        "status": "review" if reasons else "native_text",
                        "method": "native",
                        "non_whitespace_chars": chars,
                        "replacement_ratio": round(replacement_ratio, 4),
                        "largest_image_coverage": round(image_coverage, 4),
                        "ocr_candidate": bool(reasons),
                        "reasons": reasons,
                    }
                    sections.append(f"=== Página {number} | texto nativo ===\n{text}")
                except Exception as exc:
                    metadata["status"] = "partial"
                    diagnosis = {"page": number, "status": "error", "error": str(exc)}
                    sections.append(f"=== Página {number} | falha de extração ===\n")
                metadata["pages"].append(diagnosis)
    except Exception as exc:
        metadata.update(status="error", error=str(exc))
    return metadata, "\n\n".join(sections)


def process_corpus(input_dir: Path, output_dir: Path, sample_per_uf: int, seed: int) -> dict:
    groups = defaultdict(list)
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".pdf":
            relative = path.relative_to(input_dir)
            groups[relative.parts[0] if len(relative.parts) > 1 else "unknown"].append(path)
    if not groups:
        raise ValueError(f"Nenhum PDF encontrado em {input_dir}")

    rng = random.Random(seed)
    selected = []
    for uf, paths in sorted(groups.items()):
        chosen = rng.sample(paths, min(sample_per_uf, len(paths))) if sample_per_uf else paths
        selected.extend((uf, path) for path in sorted(chosen))

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "input_dir": str(input_dir.resolve()),
        "available_pdfs": sum(map(len, groups.values())),
        "available_by_uf": {uf: len(paths) for uf, paths in sorted(groups.items())},
        "selected_pdfs": len(selected),
        "sample_per_uf": sample_per_uf,
        "seed": seed,
        "pymupdf_version": pymupdf.VersionBind,
        "ocr_executed": False,
        "document_statuses": Counter(),
        "page_statuses": Counter(),
        "ocr_candidate_pages": 0,
    }
    with (output_dir / "manifest.jsonl").open("w", encoding="utf-8") as manifest:
        for index, (uf, path) in enumerate(selected, 1):
            relative = path.relative_to(input_dir)
            metadata, text = analyze_pdf(path)
            # Mantém o nome completo para evitar colisões de nomes/extensões.
            target = output_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            text_path = Path(str(target) + ".txt")
            metadata_path = Path(str(target) + ".metadata.json")
            metadata.update(source=str(relative), uf=uf, text_path=str(text_path.relative_to(output_dir)))
            text_path.write_text(text, encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            summary["document_statuses"][metadata["status"]] += 1
            for page in metadata["pages"]:
                summary["page_statuses"][page["status"]] += 1
                summary["ocr_candidate_pages"] += int(page.get("ocr_candidate", False))
            if index % 25 == 0 or index == len(selected):
                print(f"Processados {index}/{len(selected)} PDFs", flush=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DATA_DIR / "extracted")
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR / "processed_sample")
    parser.add_argument("--sample-per-uf", type=int, default=5, help="PDFs por UF; 0 processa todos")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.sample_per_uf < 0:
        parser.error("--sample-per-uf deve ser >= 0")
    if not args.input_dir.is_dir():
        parser.error(f"Pasta de entrada inexistente: {args.input_dir}")
    # Cada execução tem relatórios próprios, sem sobrescrever uma amostra anterior.
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("A pasta de saída deve estar vazia; escolha outra --output-dir")
    summary = process_corpus(args.input_dir, args.output_dir, args.sample_per_uf, args.seed)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
