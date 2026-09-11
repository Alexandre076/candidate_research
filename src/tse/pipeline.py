"""Extração em lote retomável e cruzamento cadastral. Sem análise semântica automática."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from analyze_pdfs import analyze_pdf, DATA_DIR

VERSION = '1'
FILENAME = re.compile(r'^(\d{4})([A-Z]{2})(\d+)_(\d+)')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def extract(job):
    path, root, output = map(Path, job)
    relative = path.relative_to(root)
    target = output / 'documents' / (str(relative) + '.json')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if target.exists():
        cached = json.loads(target.read_text())
        if cached.get('sha256') == digest and cached.get('pipeline_version') == VERSION:
            return cached
    meta, text = analyze_pdf(path)
    match = FILENAME.match(path.name)
    meta.update(document=str(relative), pipeline_version=VERSION,
                election_year=match[1], uf=match[2], candidate_id=match[3],
                document_id=match[4], semantic_status='pending',
                ocr_status='not_executed')
    # Imagem grande é um sinal auxiliar; não solicita OCR isoladamente.
    meta['ocr_pending_pages'] = [p['page'] for p in meta['pages']
        if p.get('non_whitespace_chars', 0) < 80 or p.get('replacement_ratio', 0) > .01]
    text_path = output / 'texts' / (str(relative) + '.txt')
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding='utf-8')
    meta['text_path'] = str(text_path.relative_to(output))
    write_json(target, meta)
    return meta


def registry(archive):
    records = {}
    with zipfile.ZipFile(archive) as z:
        # Usa só os arquivos por UF: BRASIL duplicaria os mesmos registros.
        for name in z.namelist():
            if not re.search(r'_[A-Z]{2}\.csv$', name, re.I):
                continue
            with z.open(name) as stream:
                for row in csv.DictReader(io.TextIOWrapper(stream, encoding='latin-1'), delimiter=';'):
                    key = (row['ANO_ELEICAO'], row['SG_UF'], row['SQ_CANDIDATO'])
                    value = {k: row[k] for k in ['NM_CANDIDATO', 'DS_CARGO', 'SG_PARTIDO']}
                    if key not in records: records[key] = []
                    if value not in records[key]: records[key].append(value)
    return records


def run(args):
    lookup = registry(args.registry)
    files, excluded = [], []
    for path in sorted(args.input.rglob('*')):
        if path.is_file() and path.suffix.lower() == '.pdf':
            if FILENAME.match(path.name): files.append(path)
            else: excluded.append(str(path.relative_to(args.input)))
    if not files: raise ValueError('Nenhuma certidão encontrada')
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / 'excluded.json', excluded)
    groups = {}
    failures = ocr_docs = pages = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool, (args.output / 'manifest.jsonl').open('w') as manifest:
        jobs = ((str(p), str(args.input), str(args.output)) for p in files)
        for i, meta in enumerate(pool.map(extract, jobs), 1):
            key = (meta['election_year'], meta['uf'], meta['candidate_id'])
            candidates = lookup.get(key, [])
            meta['registry_status'] = 'matched' if len(candidates) == 1 else 'missing_or_ambiguous'
            manifest.write(json.dumps(meta, ensure_ascii=False) + '\n')
            group = groups.setdefault(key, {'ano':key[0], 'uf':key[1], 'sq_candidato':key[2],
                'nome':candidates[0]['NM_CANDIDATO'] if len(candidates)==1 else '',
                'cargo':candidates[0]['DS_CARGO'] if len(candidates)==1 else '',
                'partido':candidates[0]['SG_PARTIDO'] if len(candidates)==1 else '',
                'vinculo_cadastral':meta['registry_status'], 'documentos':0,
                'documentos_com_ocr_pendente':0,'documentos_com_erro':0,
                'processos_confirmados':'', 'analise_semantica':'pendente'})
            group['documentos'] += 1
            group['documentos_com_ocr_pendente'] += bool(meta['ocr_pending_pages'])
            group['documentos_com_erro'] += meta['status'] != 'ok'
            failures += meta['status'] != 'ok'
            ocr_docs += bool(meta['ocr_pending_pages'])
            pages += len(meta['pages'])
            if i % 100 == 0 or i == len(files): print(f'{i}/{len(files)} PDFs', flush=True)
    with (args.output / 'candidates.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(next(iter(groups.values()))))
        writer.writeheader(); writer.writerows(groups.values())
    summary = {'documents':len(files), 'excluded_pdfs':len(excluded), 'pages':pages,
        'candidate_keys':len(groups), 'documents_with_errors':failures,
        'documents_with_ocr_pending':ocr_docs, 'semantic_status':'pending_provider_configuration',
        'candidate_count_with_criminal_processes':None,
        'registry_sha256':hashlib.sha256(args.registry.read_bytes()).hexdigest()}
    write_json(args.output / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATA_DIR / 'extracted')
    parser.add_argument('--output', type=Path, default=DATA_DIR / 'pipeline')
    parser.add_argument('--registry', type=Path, default=DATA_DIR / 'raw/consulta_cand_2026.zip')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1: parser.error('--workers deve ser positivo')
    run(args)
