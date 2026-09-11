"""Produz uma fila de evidências para revisão; não conta acusações ou candidatos."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re


CNJ = re.compile(r"\b(\d{7})\s*[-–.]\s*(\d{2})\s*\.\s*(\d{4})\s*\.\s*(\d)\s*\.\s*(\d{2})\s*\.\s*(\d{4})\b")
PAGE = re.compile(r"^=== Página (\d+) \| .*? ===\n", re.M)
FIELDS = re.compile(r"^\s*(Classe(?: Processual)?|Assunto(?:\(s\)|s)?|Natureza|Ação|Situação)\s*:\s*(.*)$", re.I | re.M)


def extract_mentions(text):
    """Agrupa menções pelo número, sem inferir titularidade ou natureza criminal."""
    parts = PAGE.split(text)
    if parts[0].strip() or len(parts) == 1:
        raise ValueError("Texto sem separadores de página reconhecidos")
    mentions = {}
    signals = []
    for index in range(1, len(parts), 2):
        page, body = int(parts[index]), parts[index + 1]
        for match in CNJ.finditer(body):
            groups = match.groups()
            number = f"{groups[0]}-{groups[1]}.{groups[2]}.{groups[3]}.{groups[4]}.{groups[5]}"
            item = mentions.setdefault(number, {
                "number": number,
                "review_status": "pending",
                "nature": "unknown",
                "candidate_relationship": "unverified",
                "subject": None,
                "procedural_status": None,
                "include_in_count": None,
                "evidence": [],
            })
            item["evidence"].append({
                "page": page,
                "quote": body[max(0, match.start() - 200):match.end() + 400].strip(),
                "page_char_start": match.start(),
                "page_char_end": match.end(),
            })
        # Os campos pertencem à página; associá-los a um processo exige revisão.
        for match in FIELDS.finditer(body):
            signals.append({"page": page, "label": match[1], "quote": match[0].strip()})
        for match in re.finditer(r"certid[aã]o\s+positiva[^\n]*", body, re.I):
            signals.append({"page": page, "label": "positive_heading", "quote": match[0]})
    return list(mentions.values()), signals


def run(sample_dir, output_dir):
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Escolha uma pasta de saída vazia")
    records = []
    for line in (sample_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        meta = json.loads(line)
        text = (sample_dir / meta["text_path"]).read_text(encoding="utf-8")
        mentions, signals = extract_mentions(text) if text.strip() else ([], [])
        match = re.match(r"(\d{4})([A-Z]{2})(\d+)_", Path(meta["source"]).name)
        review_pages = [p["page"] for p in meta["pages"] if p["status"] != "native_text"]
        records.append({
            "document": meta["source"],
            "sha256": meta.get("sha256"),
            "uf": meta["uf"],
            "filename_candidate_key_unverified": "".join(match.groups()) if match else None,
            "candidate_id": None,
            "candidate_name": None,
            "classification": "pending_review",
            "triage": "number_mentions" if mentions else "positive_heading" if any(s["label"] == "positive_heading" for s in signals) else "no_number_detected",
            "reading_status": meta["status"],
            "pages_to_review": review_pages,
            "distinct_number_mentions": len(mentions),
            "process_count": None,
            "mentions": mentions,
            "page_signals": signals,
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "documents.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    summary = {
        "documents": len(records),
        "triage": dict(Counter(r["triage"] for r in records)),
        "documents_with_reading_alerts": sum(bool(r["pages_to_review"]) or r["reading_status"] != "ok" for r in records),
        "distinct_number_mentions_across_sample": len({m["number"] for r in records for m in r["mentions"]}),
        "candidate_count_with_criminal_processes": None,
        "criminal_process_count": None,
        "limitation": "Menções não são processos confirmados do candidato. Revisar natureza, titularidade, referências, numeração antiga e leitura antes de contar.",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-dir", type=Path, default=Path(__file__).resolve().parent / "data/processed_sample")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "data/process_triage_sample")
    args = parser.parse_args()
    print(json.dumps(run(args.sample_dir, args.output_dir), ensure_ascii=False, indent=2))
