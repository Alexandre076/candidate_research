# Initial PDF diagnostics

Requires Python 3.11+ and the dependencies from `requirements.txt`. From the
project root, inside a virtual environment:

```bash
python -m pip install -r requirements.txt
python src/tse/analyze_pdfs.py
```

By default, the script selects up to five PDFs per state with seed 42 and writes
results to `src/tse/data/processed_sample/`. Default paths do not depend on the
execution directory. For a larger sample, use a new output directory:

```bash
python src/tse/analyze_pdfs.py --sample-per-uf 20 --output-dir src/tse/data/processed_sample_20
```

To analyze the entire dataset, use `--sample-per-uf 0` and another output
directory. The CLI rejects a nonempty output directory to preserve earlier runs.

## Outputs

- `summary.json`: total available PDFs, sample size, and diagnostic counts.
- `manifest.jsonl`: one record per document, including diagnostics for every page.
- `<UF>/<original name>.txt`: native text with page separators.
- `<UF>/<original name>.metadata.json`: SHA-256 hash, source, method, and page indicators.

Document status indicates technical reading success, not content completeness.
Pages with little text, replacement characters, or an image covering at least
60% of the area receive `review` and `ocr_candidate: true`. Pages with errors are
counted separately and require investigation. An empty page may also receive
`review`. An existing OCR layer can produce text and still warrant review because
of a large image. These rules are heuristic; tiled images and incorrectly decoded
text without replacement characters may escape detection. Reading order is not
guaranteed in complex layouts. The script does not perform OCR or send documents
to services.

## Next stage

Visually inspect examples marked `review` and `native_text`, calibrate the rules,
and add selective Portuguese OCR. Then group documents by content patterns and
select examples from each family to propose and validate schemas. A sample by
state is a starting point and does not guarantee coverage of rare templates.
