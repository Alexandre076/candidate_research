# TSE certificate pipeline architecture

The pipeline starts from public TSE files, extracts native text and selective OCR,
matches each document against the candidate registry, and runs two stages of
semantic analysis. Its output links candidates, documents, and court cases. A
case record does not imply guilt or conviction.

## Unified execution

From the project root, start or resume the complete pipeline with:

```bash
.venv/bin/python src/tse/run_pipeline.py
```

The orchestrator checks the artifacts from each stage and skips completed work.
It downloads missing inputs, extracts PDFs, runs local processing and OCR,
monitors batches, repairs truncated responses, and regenerates the tables.
`Ctrl+C` can interrupt monitoring; another execution resumes from existing files.

To inspect progress without accessing the API or modifying files:

```bash
.venv/bin/python src/tse/run_pipeline.py status
```

When raw files are already available and external downloads are not wanted:

```bash
.venv/bin/python src/tse/run_pipeline.py --no-download
```

## Main execution flow

```mermaid
flowchart TD
    ORCH["run_pipeline.py<br/>orchestrates, checks, and resumes every stage"]
    TSE_CERT["TSE Open Data<br/>27 certificate ZIP files by state"]
    TSE_CAND["TSE Open Data<br/>consulta_cand_2026.zip"]
    DL["download.py<br/>downloads ZIP files by state"]
    RAW_CERT["src/tse/data/raw<br/>raw certificate ZIP files"]
    RAW_CAND["src/tse/data/raw/consulta_cand_2026.zip<br/>raw candidate registry"]
    UNZIP["extract_certs.py<br/>extracts PDFs and groups them by state"]
    PDFS["src/tse/data/extracted/UF/*.pdf<br/>12,338 PDFs"]
    FILTER{"Does the name follow the pattern<br/>year + state + SQ_CANDIDATO<br/>+ SQ_DOCUMENTO?"}
    EXCLUDED["27 leiame.pdf files excluded"]
    NATIVE["pipeline.py + PyMuPDF<br/>native text, pages, hash, and diagnostics"]
    REGISTRY["Registry reader<br/>key: year + state + SQ_CANDIDATO"]
    JOIN["Document–candidate link<br/>name, office, and party"]
    LOCAL["src/tse/data/pipeline<br/>12,311 documents<br/>20,615 pages<br/>5,757 candidates"]
    OCRQ{"Page with little text<br/>or invalid characters?"}
    OCR["ocr_pipeline.py<br/>Tesseract por, 200 dpi<br/>1,367 documents"]
    TEXT["Effective text by page<br/>OCR replaces flagged native pages"]
    PREP1["semantic_batch.py prepare<br/>JSON Schema + candidate + pages"]
    NANO["Stage 1 — GPT-5.4 nano<br/>12,311 requests / 25 batches"]
    VALID1["Local validation<br/>schema, response, and literal citations"]
    SELECT{"Positive, inconclusive,<br/>unreadable, fragment,<br/>error, or inconsistency?"}
    SCREENED["Negative or civil only<br/>does not require the second review"]
    PREP2["Selection of 4,532 documents"]
    MINI["Stage 2 — GPT-5.4 mini<br/>4,532 requests / 11 batches"]
    VALID2["Local evidence validation<br/>4,520 responses initially complete"]
    REPAIR["Synchronous repair<br/>12 truncated responses;<br/>1 required 30,000 tokens"]
    OVERRIDE["Repair results<br/>replace incomplete responses"]
    CONSOLIDATE["consolidate_results.py<br/>filters explicit criminal links<br/>and deduplicates by candidate + case"]
    DOCS["documents_preliminary.csv<br/>one row per document"]
    PROCESSES["processes_preliminary.csv<br/>one row per candidate–case pair"]
    CANDIDATES["candidates_preliminary.csv<br/>counts by candidate"]
    SUMMARY["summary.json<br/>coverage and totals"]
    TYPES["process_type_report.py<br/>normalized procedural classes"]
    SUBJECTS["crime_subject_report.py<br/>normalized criminal subjects"]
    CONCLUSION["CONCLUSAO.md<br/>automated summary"]

    TSE_CERT --> DL --> RAW_CERT --> UNZIP --> PDFS --> FILTER
    TSE_CAND --> RAW_CAND --> REGISTRY
    FILTER -- "no" --> EXCLUDED
    FILTER -- "yes" --> NATIVE
    NATIVE --> JOIN
    REGISTRY --> JOIN --> LOCAL
    LOCAL --> OCRQ
    OCRQ -- "yes" --> OCR --> TEXT
    OCRQ -- "no" --> TEXT
    TEXT --> PREP1 --> NANO --> VALID1 --> SELECT
    SELECT -- "no" --> SCREENED --> CONSOLIDATE
    SELECT -- "yes" --> PREP2 --> MINI --> VALID2
    VALID2 --> REPAIR --> OVERRIDE --> CONSOLIDATE
    VALID2 --> CONSOLIDATE
    CONSOLIDATE --> DOCS
    CONSOLIDATE --> PROCESSES
    CONSOLIDATE --> CANDIDATES
    CONSOLIDATE --> SUMMARY
    PROCESSES --> TYPES
    PROCESSES --> SUBJECTS
    SUMMARY --> CONCLUSION
    SUBJECTS --> CONCLUSION
    ORCH -. controls .-> DL
    ORCH -. controls .-> NATIVE
    ORCH -. controls .-> OCR
    ORCH -. controls .-> PREP1
    ORCH -. controls .-> PREP2
    ORCH -. controls .-> REPAIR
    ORCH -. controls .-> CONSOLIDATE
```

## Lifecycle of each batch set

```mermaid
stateDiagram-v2
    [*] --> Prepared: prepare
    Prepared --> Submitted: upload JSONL
    Submitted --> Processing: validating / in_progress
    Processing --> Completed: completed
    Processing --> Resubmission: token limit / expired
    Resubmission --> Submitted: queue available
    Completed --> Download: output_file_id
    Download --> Validation: validate
    Validation --> Repair: incomplete / max_output_tokens
    Repair --> Validation: replacement response
    Validation --> [*]: all responses present
```

The `watch` mode polls the API every minute, downloads results atomically, keeps
one resubmitted batch at a time to respect the organization's queued-token limit,
and resumes from local receipts. A credit limit pauses the monitor without
deleting progress.

## Script responsibilities

| Script | Role | Main outputs |
|---|---|---|
| `run_pipeline.py` | Orchestrate and resume the complete flow | All outputs below |
| `download.py` | Download certificate ZIP files for the 27 states | `certidao_criminal_2026_UF.zip` |
| `extract_certs.py` | Extract PDFs and organize them by state | `data/extracted/UF/*.pdf` |
| `analyze_pdfs.py` | Extract and diagnose samples during calibration | `processed_sample/` |
| `triage_processes.py` | Detect CNJ mentions without assigning cases | `process_triage_sample/` |
| `pipeline.py` | Run native extraction and match the registry | `manifest.jsonl`, `texts/`, `documents/`, `candidates.csv`, `summary.json` |
| `ocr_pipeline.py` | Apply OCR only to flagged pages | `ocr/` |
| `semantic_batch.py` | Prepare, submit, monitor, download, and validate LLM work | `batch_*` directories, `validated.jsonl` |
| `consolidate_results.py` | Apply repairs, filter records, and deduplicate | Three CSVs and `summary.json` |
| `process_type_report.py` | Normalize procedural classes | `process_types_preliminary.csv` |
| `crime_subject_report.py` | Normalize criminal causes and subjects | `crime_subjects_preliminary.csv` |
| `generate_insights.py` | Generate charts and the HTML dashboard | `insights/` |

`analyze_pdfs.py` and `triage_processes.py` belong to the exploratory phase. They
helped define reading alerts, the schema, and the rules, but their counts do not
feed the consolidated result directly.

## Structured data extracted by the LLM

Each document receives one classification: positive criminal, negative criminal,
civil only, unreadable, inconclusive, or fragment. Each proposed record contains:

- case number;
- candidate's role;
- nature and procedural class;
- mention type, either primary or reference;
- subjects and their scope;
- procedural status and outcome, when explicit;
- short description;
- literal evidence with a page number.

Local validation requires evidence for the case, evidence for the relationship
when marked explicit, and evidence for subjects when populated. It checks whether
every citation appears in the text sent to the model. This confirms structural
and textual consistency; it does not replace legal or human review.

## Final state of this run

| Metric | Value |
|---|---:|
| PDFs found | 12,338 |
| Informational PDFs excluded | 27 |
| Documents processed | 12,311 |
| Pages | 20,615 |
| Candidate keys | 5,757 |
| Documents sent to mini | 4,532 |
| Documents pending after repairs | 0 |
| Candidates with an automated record | 588 |
| Numbered cases by candidate | 1,482 |
| Records without a number | 12 |

Candidate and case totals represent automated results. A case may be an
investigation, an action without judgment, an appeal, or an enforcement action;
its presence does not prove a conviction.

## Technical points to standardize

- `download.py` and `extract_certs.py` use `data/...` relative to the execution
  directory; the remaining scripts use `src/tse/data/...` derived from the script
  path.
- The `consulta_cand_2026.zip` ZIP is an additional registry input and is not
  downloaded by `download.py`.
- Stage 2 repairs must be supplied through `--override` when consolidation runs.
- The `preliminary` names were retained because the analysis did not undergo
  human review, although technical document coverage is complete.
