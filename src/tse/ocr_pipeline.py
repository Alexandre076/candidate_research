"""OCR seletivo dos resultados do pipeline, preservando a extração nativa."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import subprocess
import tempfile
import pymupdf
from analyze_pdfs import DATA_DIR
from pipeline import write_json


def run(root, source):
    # Falha antes de iniciar se o idioma não estiver instalado.
    languages = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, check=True)
    if 'por' not in languages.stdout.split():
        raise RuntimeError('Instale o idioma português do Tesseract')
    jobs = []
    for line in (root / 'manifest.jsonl').read_text().splitlines():
        meta = json.loads(line)
        if meta['ocr_pending_pages']: jobs.append((root, source, meta))
    count = errors = 0
    with ProcessPoolExecutor(max_workers=4) as pool:
        for status in pool.map(process_document, jobs):
            count += 1
            errors += status not in ('ok', 'cached')
            if count % 10 == 0: print(f'OCR: {count}/{len(jobs)} documentos; {errors} com erros', flush=True)
    print(f'OCR concluído: {count} documentos; {errors} com erros')


def process_document(job):
    root, source, meta = job
    target = root / 'ocr' / (meta['document'] + '.json')
    if target.exists():
        old = json.loads(target.read_text())
        if old.get('sha256') == meta.get('sha256') and old.get('status') == 'ok': return 'cached'
    result = {'sha256':meta.get('sha256'), 'document':meta['document'], 'status':'ok', 'pages':[]}
    try:
        with pymupdf.open(source / meta['document']) as doc:
            for number in meta['ocr_pending_pages']:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        image = Path(tmp) / 'page.png'
                        doc[number-1].get_pixmap(dpi=200).save(image)
                        response = subprocess.run(['tesseract', str(image), 'stdout', '-l', 'por'],
                            capture_output=True, text=True, check=True, timeout=120)
                    result['pages'].append({'page':number,'method':'tesseract_por_200dpi',
                        'text':response.stdout,'review_required':True})
                except Exception as exc:
                    result['status']='partial'
                    result['pages'].append({'page':number,'error':str(exc)})
    except Exception as exc:
        result.update(status='error', error=str(exc))
    write_json(target,result)
    return result['status']


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=DATA_DIR/'pipeline')
    parser.add_argument('--source',type=Path,default=DATA_DIR/'extracted')
    args=parser.parse_args();run(args.root,args.source)
