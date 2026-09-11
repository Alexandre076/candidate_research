"""Orquestra o pipeline completo de certidões do TSE com retomada por artefatos."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path

from consolidate_results import consolidate
from crime_subject_report import build as build_subject_report
from download import UFs, download_certificate
from extract_certs import extract_all_raw_zips
from ocr_pipeline import run as run_ocr
from pipeline import run as run_local_pipeline
from process_type_report import build as build_type_report
from semantic_batch import (
    load_openai_key, prepare, run_sync, selected_documents, validate,
    watch_batches,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / 'data'
REGISTRY_URL = (
    'https://cdn.tse.jus.br/estatistica/sead/odsele/'
    'consulta_cand/consulta_cand_2026.zip'
)


def line_count(path):
    return sum(1 for line in path.open() if line.strip()) if path.exists() else 0


def validation_counts(folder):
    path = folder / 'validated.jsonl'
    counts = Counter()
    if path.exists():
        for line in path.open():
            if line.strip():
                counts[json.loads(line).get('status', 'unknown')] += 1
    return counts


def download_file(session, url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    response = session.get(url, stream=True, timeout=120,
                           headers={'Referer': 'https://dadosabertos.tse.jus.br/'})
    response.raise_for_status()
    with temporary.open('wb') as output:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                output.write(chunk)
    temporary.replace(target)


def ensure_downloads(raw, enabled=True):
    expected = [raw / f'certidao_criminal_2026_{uf}.zip' for uf in UFs]
    registry = raw / 'consulta_cand_2026.zip'
    missing = [path for path in expected if not path.exists() or not path.stat().st_size]
    if not enabled and (missing or not registry.exists()):
        raise RuntimeError('Entradas ausentes e download desabilitado por --no-download')
    if not missing and registry.exists() and registry.stat().st_size:
        print('[download] 27 ZIPs de certidões e cadastro já disponíveis.')
        return
    from curl_cffi import requests
    with requests.Session(impersonate='chrome120') as session:
        session.get('https://dadosabertos.tse.jus.br/', timeout=15)
        for path in missing:
            uf = path.stem.rsplit('_', 1)[-1]
            download_certificate(uf, session, raw)
        if not registry.exists() or not registry.stat().st_size:
            print('[download] Baixando cadastro de candidatos...')
            download_file(session, REGISTRY_URL, registry)


def ensure_extraction(raw, extracted):
    ready = all((extracted / uf).is_dir() for uf in UFs)
    if ready and any(extracted.rglob('*.pdf')):
        print('[extract] PDFs por UF já disponíveis.')
        return
    print('[extract] Descompactando certidões...')
    extract_all_raw_zips(raw, extracted)


def ensure_local_pipeline(pipeline_root, extracted, registry, workers):
    summary_path = pipeline_root / 'summary.json'
    manifest = pipeline_root / 'manifest.jsonl'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        if line_count(manifest) == summary.get('documents'):
            print(f'[local] {summary["documents"]} documentos já extraídos e vinculados.')
            return
    args = argparse.Namespace(input=extracted, output=pipeline_root,
                              registry=registry, workers=workers)
    run_local_pipeline(args)


def ensure_ocr(pipeline_root, extracted):
    summary = json.loads((pipeline_root / 'summary.json').read_text())
    expected = summary.get('documents_with_ocr_pending', 0)
    present = sum(1 for path in (pipeline_root / 'ocr').rglob('*.json'))
    if present >= expected:
        print(f'[ocr] {present}/{expected} resultados de OCR já disponíveis.')
        return
    run_ocr(pipeline_root, extracted)


def ensure_semantic(folder, expected, prepare_call, interval):
    counts = validation_counts(folder)
    if sum(counts.values()) == expected and not counts.get('missing_response'):
        print(f'[semantic] {folder.name}: {expected} respostas já validadas {dict(counts)}.')
        return
    if not folder.exists() or not any(folder.iterdir()):
        prepare_call()
    watch_batches(folder, interval)
    counts = validation_counts(folder)
    if sum(counts.values()) != expected or counts.get('missing_response'):
        raise RuntimeError(f'Cobertura incompleta em {folder}: {dict(counts)}')


def ensure_repairs(pipeline_root, stage2):
    overrides = []
    previous = stage2
    for version, limit in ((1, 12000), (2, 30000)):
        errors = validation_counts(previous).get('error', 0)
        if not errors:
            break
        folder = pipeline_root / f'batch_stage2_repair_v{version}'
        if not folder.exists() or not any(folder.iterdir()):
            selection = selected_documents(previous / 'validated.jsonl', errors_only=True)
            prepare(pipeline_root, folder, model='gpt-5.4-mini', documents=selection,
                    max_output_tokens=limit)
        if not (folder / 'validated.jsonl').exists():
            run_sync(folder)
            validate(folder)
        overrides.append(folder)
        previous = folder
    remaining = validation_counts(previous).get('error', 0)
    if remaining:
        raise RuntimeError(f'{remaining} respostas continuam incompletas após os reparos')
    # Inclui reparos existentes em uma retomada cuja etapa principal já não tem erros.
    for folder in sorted(pipeline_root.glob('batch_stage2_repair_v*')):
        if (folder / 'validated.jsonl').exists() and folder not in overrides:
            overrides.append(folder)
    print(f'[repair] {len(overrides)} conjunto(s) de reparo aplicado(s).')
    return sorted(overrides)


def run(args):
    raw = DATA / 'raw'
    extracted = DATA / 'extracted'
    pipeline_root = DATA / 'pipeline'
    stage1 = pipeline_root / 'batch_stage1_nano_v2'
    stage2 = pipeline_root / 'batch_stage2_mini_v1'
    results = pipeline_root / 'preliminary_results'

    load_openai_key(ROOT / '.env')
    ensure_downloads(raw, not args.no_download)
    ensure_extraction(raw, extracted)
    ensure_local_pipeline(pipeline_root, extracted, raw / 'consulta_cand_2026.zip',
                          args.workers)
    ensure_ocr(pipeline_root, extracted)
    document_total = json.loads((pipeline_root / 'summary.json').read_text())['documents']

    ensure_semantic(
        stage1, document_total,
        lambda: prepare(pipeline_root, stage1, model='gpt-5.4-nano'),
        args.interval,
    )
    selection = selected_documents(stage1 / 'validated.jsonl')
    ensure_semantic(
        stage2, len(selection),
        lambda: prepare(pipeline_root, stage2, model='gpt-5.4-mini',
                        documents=selection),
        args.interval,
    )
    overrides = ensure_repairs(pipeline_root, stage2)
    consolidate(pipeline_root, stage1, stage2, results, overrides)
    build_type_report(results / 'processes_preliminary.csv',
                      results / 'process_types_preliminary.csv')
    build_subject_report(results / 'processes_preliminary.csv',
                         results / 'crime_subjects_preliminary.csv')
    print(f'[done] Resultados em {results}')


def status():
    pipeline_root = DATA / 'pipeline'
    for name in ('batch_stage1_nano_v2', 'batch_stage2_mini_v1',
                 'batch_stage2_repair_v1', 'batch_stage2_repair_v2'):
        folder = pipeline_root / name
        if folder.exists():
            print(name, dict(validation_counts(folder)))
    summary = pipeline_root / 'preliminary_results/summary.json'
    if summary.exists():
        print(json.dumps(json.loads(summary.read_text()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'status'], nargs='?', default='run')
    parser.add_argument('--workers', type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--no-download', action='store_true')
    arguments = parser.parse_args()
    if arguments.workers < 1 or arguments.interval < 1:
        parser.error('--workers e --interval devem ser positivos')
    status() if arguments.action == 'status' else run(arguments)
