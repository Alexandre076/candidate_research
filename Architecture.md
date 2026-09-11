# Arquitetura do pipeline de certidões do TSE

O pipeline parte dos arquivos públicos do TSE, extrai texto nativo e OCR seletivo,
cruza cada documento com o cadastro de candidaturas e usa duas etapas de análise
semântica. A saída relaciona candidatos, documentos e processos. Um registro
processual não implica culpa ou condenação.

## Execução unificada

Na raiz do projeto, o pipeline completo pode ser iniciado ou retomado com:

```bash
.venv/bin/python src/tse/run_pipeline.py
```

O orquestrador verifica os artefatos de cada etapa e pula o que já estiver
concluído. Ele baixa entradas ausentes, extrai os PDFs, executa o processamento
local e o OCR, acompanha os batches, repara respostas truncadas e regenera as
tabelas. `Ctrl+C` pode interromper o monitoramento; uma nova execução retoma pelos
arquivos existentes.

Para inspecionar o progresso sem acessar a API ou alterar arquivos:

```bash
.venv/bin/python src/tse/run_pipeline.py status
```

Quando os arquivos brutos já estiverem disponíveis e downloads externos não forem
desejados:

```bash
.venv/bin/python src/tse/run_pipeline.py --no-download
```

## Fluxo principal executado

```mermaid
flowchart TD
    ORCH["run_pipeline.py<br/>orquestra, verifica e retoma todas as etapas"]
    TSE_CERT["TSE Dados Abertos<br/>27 ZIPs de certidões por UF"]
    TSE_CAND["TSE Dados Abertos<br/>consulta_cand_2026.zip"]
    DL["download.py<br/>baixa os ZIPs por UF"]
    RAW_CERT["src/tse/data/raw<br/>ZIPs brutos de certidões"]
    RAW_CAND["src/tse/data/raw/consulta_cand_2026.zip<br/>Cadastro bruto de candidatos"]
    UNZIP["extract_certs.py<br/>extrai PDFs e organiza por UF"]
    PDFS["src/tse/data/extracted/UF/*.pdf<br/>12.338 PDFs"]
    FILTER{"Nome segue o padrão<br/>ano + UF + SQ_CANDIDATO<br/>+ SQ_DOCUMENTO?"}
    EXCLUDED["27 leiame.pdf excluídos"]
    NATIVE["pipeline.py + PyMuPDF<br/>texto nativo, páginas, hash e diagnóstico"]
    REGISTRY["Leitura do cadastro<br/>chave: ano + UF + SQ_CANDIDATO"]
    JOIN["Vínculo documento–candidato<br/>nome, cargo e partido"]
    LOCAL["src/tse/data/pipeline<br/>12.311 documentos<br/>20.615 páginas<br/>5.757 candidatos"]
    OCRQ{"Página com pouco texto<br/>ou caracteres inválidos?"}
    OCR["ocr_pipeline.py<br/>Tesseract por, 200 dpi<br/>1.367 documentos"]
    TEXT["Texto efetivo por página<br/>OCR substitui página nativa sinalizada"]
    PREP1["semantic_batch.py prepare<br/>JSON Schema + candidato + páginas"]
    NANO["Etapa 1 — GPT-5.4 nano<br/>12.311 requisições / 25 batches"]
    VALID1["Validação local<br/>schema, resposta e citações literais"]
    SELECT{"Positivo, inconclusivo,<br/>ilegível, fragmento,<br/>erro ou inconsistência?"}
    SCREENED["Negativo ou somente cível<br/>dispensado da segunda leitura"]
    PREP2["Seleção de 4.532 documentos"]
    MINI["Etapa 2 — GPT-5.4 mini<br/>4.532 requisições / 11 batches"]
    VALID2["Validação local das evidências<br/>4.520 respostas completas inicialmente"]
    REPAIR["Reparo síncrono<br/>12 respostas truncadas;<br/>1 exigiu 30 mil tokens"]
    OVERRIDE["Resultados de reparo<br/>substituem respostas incompletas"]
    CONSOLIDATE["consolidate_results.py<br/>filtra vínculo criminal explícito<br/>e deduplica por candidato + processo"]
    DOCS["documents_preliminary.csv<br/>uma linha por documento"]
    PROCESSES["processes_preliminary.csv<br/>uma linha por candidato–processo"]
    CANDIDATES["candidates_preliminary.csv<br/>contagens por candidato"]
    SUMMARY["summary.json<br/>cobertura e totais"]
    TYPES["process_type_report.py<br/>classes processuais normalizadas"]
    SUBJECTS["crime_subject_report.py<br/>temas criminais normalizados"]
    CONCLUSION["CONCLUSAO.md<br/>síntese automática"]

    TSE_CERT --> DL --> RAW_CERT --> UNZIP --> PDFS --> FILTER
    TSE_CAND --> RAW_CAND --> REGISTRY
    FILTER -- "não" --> EXCLUDED
    FILTER -- "sim" --> NATIVE
    NATIVE --> JOIN
    REGISTRY --> JOIN --> LOCAL
    LOCAL --> OCRQ
    OCRQ -- "sim" --> OCR --> TEXT
    OCRQ -- "não" --> TEXT
    TEXT --> PREP1 --> NANO --> VALID1 --> SELECT
    SELECT -- "não" --> SCREENED --> CONSOLIDATE
    SELECT -- "sim" --> PREP2 --> MINI --> VALID2
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
    ORCH -. controla .-> DL
    ORCH -. controla .-> NATIVE
    ORCH -. controla .-> OCR
    ORCH -. controla .-> PREP1
    ORCH -. controla .-> PREP2
    ORCH -. controla .-> REPAIR
    ORCH -. controla .-> CONSOLIDATE
```

## Ciclo de cada conjunto de batches

```mermaid
stateDiagram-v2
    [*] --> Preparado: prepare
    Preparado --> Submetido: upload JSONL
    Submetido --> EmProcessamento: validating / in_progress
    EmProcessamento --> Concluido: completed
    EmProcessamento --> Reenvio: token limit / expired
    Reenvio --> Submetido: fila disponível
    Concluido --> Download: output_file_id
    Download --> Validacao: validate
    Validacao --> Reparo: incomplete / max_output_tokens
    Reparo --> Validacao: resposta substituta
    Validacao --> [*]: todas as respostas presentes
```

O modo `watch` consulta a API a cada minuto, baixa resultados de forma atômica,
mantém um lote reenviado por vez para respeitar o limite de tokens da organização
e retoma a partir dos recibos locais. Limite de crédito pausa o monitor sem apagar
o progresso.

## Responsabilidade de cada script

| Script | Papel | Principais saídas |
|---|---|---|
| `run_pipeline.py` | Orquestrar e retomar o fluxo completo | Todas as saídas abaixo |
| `download.py` | Baixar ZIPs de certidões das 27 UFs | `certidao_criminal_2026_UF.zip` |
| `extract_certs.py` | Extrair PDFs e organizar por UF | `data/extracted/UF/*.pdf` |
| `analyze_pdfs.py` | Extrair e diagnosticar amostras durante a calibração | `processed_sample/` |
| `triage_processes.py` | Detectar menções CNJ na amostra, sem atribuir processos | `process_triage_sample/` |
| `pipeline.py` | Executar extração nativa completa e cruzar cadastro | `manifest.jsonl`, `texts/`, `documents/`, `candidates.csv`, `summary.json` |
| `ocr_pipeline.py` | Fazer OCR somente nas páginas sinalizadas | `ocr/` |
| `semantic_batch.py` | Preparar, submeter, monitorar, baixar e validar LLM | pastas `batch_*`, `validated.jsonl` |
| `consolidate_results.py` | Aplicar reparos, filtrar registros e deduplicar | três CSVs e `summary.json` |
| `process_type_report.py` | Normalizar classes processuais | `process_types_preliminary.csv` |
| `crime_subject_report.py` | Normalizar causas e assuntos criminais | `crime_subjects_preliminary.csv` |

`analyze_pdfs.py` e `triage_processes.py` pertencem à fase exploratória. Eles
ajudaram a definir os alertas de leitura, o schema e as regras, mas suas contagens
não alimentam diretamente o resultado consolidado.

## Dados estruturados extraídos pela LLM

Cada documento recebe uma classificação: positivo criminal, negativo criminal,
somente cível, ilegível, inconclusivo ou fragmento. Cada registro proposto contém:

- número do processo;
- papel do candidato;
- natureza e classe processual;
- tipo de menção, principal ou referência;
- assuntos e abrangência dos assuntos;
- situação processual e resultado, quando explícitos;
- descrição breve;
- evidências literais com número da página.

A validação local exige evidência do processo, evidência do vínculo quando marcado
como explícito e evidência dos assuntos quando preenchidos. Ela verifica se cada
citação aparece no texto enviado ao modelo. Essa validação confirma consistência
estrutural e textual; não substitui revisão jurídica ou humana.

## Estado final desta execução

| Métrica | Valor |
|---|---:|
| PDFs encontrados | 12.338 |
| PDFs informativos excluídos | 27 |
| Documentos processados | 12.311 |
| Páginas | 20.615 |
| Chaves de candidato | 5.757 |
| Documentos encaminhados ao mini | 4.532 |
| Documentos pendentes após reparos | 0 |
| Candidatos com registro automático | 588 |
| Processos numerados por candidato | 1.482 |
| Registros sem número | 12 |

Os totais de candidatos e processos representam resultados automáticos. Um
processo pode ser investigação, ação sem julgamento, recurso ou execução; sua
presença não comprova condenação.

## Pontos técnicos a uniformizar

- `download.py` e `extract_certs.py` usam `data/...` relativo ao diretório de
  execução; o restante usa `src/tse/data/...` derivado do caminho do script.
- O ZIP `consulta_cand_2026.zip` é uma entrada adicional do cadastro e não é
  baixado por `download.py`.
- Os reparos da etapa 2 precisam ser informados como `--override` ao executar a
  consolidação.
- Os nomes `preliminary` foram preservados porque a análise não passou por revisão
  humana, embora a cobertura técnica dos documentos esteja completa.
