# Case-count-oriented extraction

## Complete pipeline

Run or resume every stage from the project root:

```bash
.venv/bin/python src/tse/run_pipeline.py
```

Use `status` for a local-only query and `--no-download` to require the ZIP files
to be present in `src/tse/data/raw` already.

## Local batch execution

```bash
python -m pip install -r requirements.txt
python src/tse/pipeline.py
python src/tse/ocr_pipeline.py
```

OCR requires `tesseract-ocr` and `tesseract-ocr-por` to be installed on the
system. Run OCR after the first command finishes. Output is written under
`data/pipeline`: text and diagnostics per document, `manifest.jsonl`,
`candidates.csv`, `excluded.json`, and `summary.json`. OCR writes separate results
under `ocr/` without replacing native text. Its results still require quality
assessment. It does not automatically classify empty pages as negative documents.

The batch resumes native extraction based on the PDF hash and pipeline version.
The registry is matched again on every run; missing or ambiguous records are
flagged. The table contains candidates with local documents, not every TSE
candidate. A large image alone does not send a page to OCR at this stage.

**The two commands above are local stages.** They do not call an LLM, generate
semantic descriptions, or calculate the total number of candidates with cases.
Empty count cells mean pending work, never zero. The file-name link identifies
who submitted the document; assigning a case also requires comparing the parties.
The Santa Catarina pilot is a separate result and is not propagated as a
classification for other files.

### OpenAI Batch

After OCR, run `python src/tse/semantic_batch.py prepare` to prepare request files
without sending data. Each file contains at most 1,000 requests and 40 MB; the
queued-token limit depends on the OpenAI account. The default model is
`gpt-5-nano`, with minimal reasoning effort and structured JSON output. Long pages
are split into overlapping chunks without discarding content.

Set `OPENAI_API_KEY` in the execution environment or in the local `.env` ignored
by Git. Never store the key in a versioned file.
`python src/tse/semantic_batch.py submit` uploads the files and saves batch IDs.
`python src/tse/semantic_batch.py collect` checks batches and downloads available
outputs and errors. It does not resubmit files that already have a receipt. If
the connection fails while creating a batch, check the batches in the account
before retrying: the server may have accepted an operation whose local receipt
was not saved.

To monitor, download, and resubmit every batch automatically once per minute, run:

```bash
.venv/bin/python src/tse/semantic_batch.py watch \
  --output src/tse/data/pipeline/batch_stage1_nano_v2 \
  --interval 60
```

The command resumes from existing receipts. It keeps only one resubmitted batch
at a time to respect the queued-token limit, downloads each result atomically,
and generates `validated.jsonl` after everything finishes. You can stop it with
`Ctrl+C` and run it again without losing progress.

After nano triage, prepare a mini review for positive, inconclusive, unreadable,
fragmented, or erroneous/inconsistent documents:

```bash
.venv/bin/python src/tse/semantic_batch.py prepare \
  --root src/tse/data/pipeline \
  --output src/tse/data/pipeline/batch_stage2_mini_v1 \
  --model gpt-5.4-mini \
  --selection-from src/tse/data/pipeline/batch_stage1_nano_v2/validated.jsonl
```

Then use `watch` on this new directory. Selection excludes negative and civil-only
documents that passed the first stage without inconsistencies.

Batch processing has a completion window of up to 24 hours. Pricing, model
availability, and account limits can change; consult the current OpenAI pricing
and API documentation before running a large job.

Responses are extraction proposals. Semantic validation, evidence checking, and
final consolidation by candidate must still run; the collector does not convert
raw responses into confirmed counts.

Scope: identify criminal records, including inquiries and cases without a
conviction. Preserve civil and electoral mentions separately. Do not infer a
conviction, current status, or offense from the mere existence of a case.

## First executable triage

```bash
python src/tse/triage_processes.py
```

Reads the sample manifest and text. Produces `documents.jsonl` and `summary.json`
under `src/tse/data/process_triage_sample`. Use `--output-dir` for another run.
It requires no additional libraries and makes no LLM calls.

It groups mentions of CNJ-format numbers, including line breaks and dot
separators, and stores every occurrence with its page and excerpt. It does not
validate check digits, identify old-format numbers, or distinguish primary cases
from references, appeals, or precedents by itself. The absence of a detected
number does not mean a negative certificate. Labeled subject/class fields are
page-level signals and are not automatically assigned to a case.

## Structure populated during review or semantic extraction

Each document retains its name, hash, state, reading alerts, classification, and
mentions. Each mention contains a normalized number, evidence, nature,
relationship to the person, literal subject, procedural status, and inclusion
decision.

- `nature`: `criminal`, `civil`, `electoral_noncriminal`, `administrative`, `unknown`.
- `candidate_relationship`: investigated, accused/defendant, convicted, victim,
  plaintiff, third party, reference only, or unverified relationship. Record
  evidence for the role.
- `subject`: subject/offense as written in the document; `null` when absent.
- `procedural_status`: status on the document date; `null` when absent.
- `include_in_count`: `true` only after confirming criminal nature and a relevant
  relationship; `false` for justified exclusions; `null` while uncertain.

The identifier extracted from the file name is provisional: confirm it against
the TSE registry before populating `candidate_id` and `candidate_name`. Do not use
the first person's name found in the text; it may belong to a judge, lawyer, or
another party.

For consolidation, deduplicate by confirmed candidate and normalized case number.
Retain relationships among originating cases, appeals, and renumberings so the
number of files is not confused with the number of facts. Without a number, do
not invent uniqueness. A positive certificate without identified cases has an
indeterminate count. The final total must disclose coverage, inconclusive items,
and unread documents.

## Initial validation against sample text

These checks concern textual content, not authenticity or the link to the
electoral registry. No visual review or OCR was performed at this stage. Source
excerpts remain in Portuguese because they are literal document evidence.

| Document | Page | Evidence | Review interpretation |
|---|---|---|---|
| AM/2026AM40002531443_40017126892.pdf.pdf | 1 | `Número: 1033757-26.2025.4.01.0000`; `Classe: INQUÉRITO POLICIAL`; `Assuntos: Apropriação indébita Previdenciária, Sonegação de contribuição previdenciária` | Criminal record with an explicit subject; the page identifies an investigated person. Confirm the registry link before counting it for a candidate. |
| DF/2026DF70002531335_70016842501.pdf.pdf | 1 | `Cumprimento de sentença, 0715405-49.2026.8.07.0003`; `Família.` | Positive header for civil and criminal actions, but the listed record concerns family law. The header alone is insufficient for inclusion in the criminal total. |
| RR/2026RR230002548834_230017133625.pdf.pdf | 1 | `0600458-12.2026.6.23.0000`; `Processo de Registro` / `de Candidatura` | Petition in a candidate-registration case, not evidence of a criminal case. |

Reference case numbers and cases cited in procedural history were also found.
Therefore, triage totals count mentions, not cases assigned to candidates. The
next steps are semantic review of the 135 documents, including those without
numbers, resolution of reading alerts, and confirmation of relationships before
calculating candidate counts.

## Santa Catarina semantic pilot

The result is stored at `data/semantic_pilot/SC_240017134600.json`. It is an
assisted analysis from the exploratory session, not an automated semantic
extractor or API call. The header, ending, and history search results were
inspected. Each item of evidence stores its page, literal excerpt, and character
offsets in that page's text. Excerpts were checked programmatically against the
source text.

The opening identifies a primary criminal action; page 41 provides its subjects.
Unpunctuated 20-digit numbers expand the reference list and remain separate.
References and BNMP prefixes are not presumed to be independent cases involving
the person. Subjects apply to the case as a whole and are not individualized
accusations. The registry relationship, procedural status, and conviction remain
unresolved. Names listed as defendants are not a list of candidates.

For LLM automation, send chunks with page numbers and retain document identity.
Require literal evidence for every field, distinguish case subjects from charges
against a person, and consolidate by number while keeping references separate.
Validate excerpts and schema before accepting results. A defendant list from one
chunk cannot be assigned to another case by proximity. Chunks without explicit
information return null fields; absence in one chunk does not erase evidence from
another. No candidate count is released before confirming the electoral registry
relationship.
