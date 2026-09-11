"""Consolida resultados semânticos por documento, processo e candidato."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import re


DATA = Path(__file__).resolve().parent / 'data/pipeline'


def load_jsonl(path):
    rows = {}
    for line in path.open():
        if line.strip():
            row = json.loads(line)
            rows[row['document']] = row
    return rows


def normalize_process(number):
    return re.sub(r'\D', '', number or '') or None


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def consolidate(root, stage1, stage2, output, overrides=()):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        row['document']: row
        for line in (root / 'manifest.jsonl').open()
        if (row := json.loads(line))
    }
    with (root / 'candidates.csv').open(encoding='utf-8-sig') as source:
        candidates = {
            (row['ano'], row['uf'], row['sq_candidato']): row
            for row in csv.DictReader(source)
        }
    first = load_jsonl(stage1 / 'validated.jsonl')
    second = load_jsonl(stage2 / 'validated.jsonl')
    for override in overrides:
        second.update(load_jsonl(override / 'validated.jsonl'))

    document_rows = []
    process_rows = []
    process_keys = set()
    candidate_stats = defaultdict(lambda: {
        'reviewed_documents': 0, 'pending_documents': 0,
        'positive_documents': 0, 'numbered_processes': 0,
        'records_without_number': 0, 'provisional_processes': 0,
    })

    for document, meta in metadata.items():
        key = (meta['election_year'], meta['uf'], meta['candidate_id'])
        candidate = candidates[key]
        stage1_row = first.get(document, {})
        stage2_row = second.get(document, {})
        stage2_status = stage2_row.get('status', 'not_selected')
        stage2_usable = stage2_status in {
            'evidence_checked_semantic_review_pending', 'semantic_inconsistent'
        }
        selected_for_stage2 = document in second
        if stage2_usable:
            chosen = stage2_row
            source_name = 'stage2_mini'
            confidence = 'review_pending'
            candidate_stats[key]['reviewed_documents'] += 1
        elif selected_for_stage2:
            chosen = stage1_row
            source_name = 'stage1_nano_provisional'
            confidence = 'provisional_pending_stage2'
            candidate_stats[key]['pending_documents'] += 1
        else:
            chosen = stage1_row
            source_name = 'stage1_nano_screening'
            confidence = 'screened'

        proposal = chosen.get('proposal') or {}
        classification = proposal.get('document_classification')
        accepted = [
            record for record in proposal.get('records', [])
            if record.get('nature') == 'criminal'
            and record.get('candidate_link') == 'explicit'
        ]
        if classification == 'positive_criminal' and accepted:
            candidate_stats[key]['positive_documents'] += 1
        document_rows.append({
            'ano': key[0], 'uf': key[1], 'sq_candidato': key[2],
            'nome': candidate['nome'], 'documento': document,
            'fonte_analise': source_name, 'confianca': confidence,
            'status_etapa2': stage2_status,
            'classificacao': classification or '',
            'registros_criminais_explicitos': len(accepted),
        })

        for index, record in enumerate(accepted, 1):
            normalized = normalize_process(record.get('number'))
            dedupe = (key, normalized) if normalized else (key, document, index)
            if dedupe in process_keys:
                continue
            process_keys.add(dedupe)
            if source_name == 'stage1_nano_provisional':
                candidate_stats[key]['provisional_processes'] += 1
            elif normalized:
                candidate_stats[key]['numbered_processes'] += 1
            else:
                candidate_stats[key]['records_without_number'] += 1
            process_rows.append({
                'ano': key[0], 'uf': key[1], 'sq_candidato': key[2],
                'nome': candidate['nome'], 'cargo': candidate['cargo'],
                'partido': candidate['partido'],
                'numero_processo': record.get('number') or '',
                'papel_candidato': record.get('candidate_role') or '',
                'classe': record.get('case_class') or '',
                'assuntos': ' | '.join(record.get('subjects') or []),
                'situacao': record.get('procedural_status') or '',
                'resultado': record.get('outcome') or '',
                'descricao': record.get('brief_description') or '',
                'documento': document, 'fonte_analise': source_name,
                'confianca': confidence,
            })

    candidate_rows = []
    for key, candidate in candidates.items():
        stats = candidate_stats[key]
        candidate_rows.append({
            'ano': key[0], 'uf': key[1], 'sq_candidato': key[2],
            'nome': candidate['nome'], 'cargo': candidate['cargo'],
            'partido': candidate['partido'], 'documentos': candidate['documentos'],
            **stats,
            'has_reviewed_record_preliminary': bool(
                stats['numbered_processes'] or stats['records_without_number']
            ),
        })

    write_csv(output / 'documents_preliminary.csv', document_rows,
              list(document_rows[0]))
    write_csv(output / 'processes_preliminary.csv', process_rows,
              list(process_rows[0]) if process_rows else [
                  'ano', 'uf', 'sq_candidato', 'nome', 'numero_processo'
              ])
    write_csv(output / 'candidates_preliminary.csv', candidate_rows,
              list(candidate_rows[0]))
    summary = {
        'documents_total': len(document_rows),
        'stage2_reviewed_documents': sum(
            row['reviewed_documents'] for row in candidate_rows),
        'stage2_pending_documents': sum(
            row['pending_documents'] for row in candidate_rows),
        'candidates_total': len(candidate_rows),
        'candidates_with_reviewed_record_preliminary': sum(
            bool(row['has_reviewed_record_preliminary']) for row in candidate_rows),
        'distinct_numbered_processes_preliminary': sum(
            row['numbered_processes'] for row in candidate_rows),
        'records_without_number_preliminary': sum(
            row['records_without_number'] for row in candidate_rows),
        'provisional_stage1_processes_pending_stage2': sum(
            row['provisional_processes'] for row in candidate_rows),
        'warning': 'Prévia automática; evidências ainda requerem revisão semântica/humana.',
    }
    (output / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DATA)
    parser.add_argument('--stage1', type=Path,
                        default=DATA / 'batch_stage1_nano_v2')
    parser.add_argument('--stage2', type=Path,
                        default=DATA / 'batch_stage2_mini_v1')
    parser.add_argument('--output', type=Path,
                        default=DATA / 'preliminary_results')
    parser.add_argument('--override', type=Path, action='append', default=[],
                        help='Pasta validada com reparos que substituem resultados da etapa 2')
    args = parser.parse_args()
    consolidate(args.root, args.stage1, args.stage2, args.output, args.override)
