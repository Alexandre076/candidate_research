# Candidate Research — certidões criminais do TSE

**Idioma:** Português | [English](README.en.md)

Este projeto baixa as certidões criminais apresentadas por candidatos nas eleições
brasileiras de 2026, extrai o conteúdo dos PDFs e organiza menções processuais por
candidato. O pipeline combina extração de texto, OCR seletivo e análise semântica
com modelos da OpenAI.

O resultado permite responder perguntas como:

- quantos candidatos aparecem relacionados a registros criminais;
- quantos processos foram encontrados por candidato;
- quais classes processuais aparecem com maior frequência;
- quais assuntos são mencionados, como corrupção ou violência doméstica;
- qual documento e trecho sustentam cada informação extraída.

Um registro criminal pode ser inquérito, investigação ou processo sem julgamento.
A presença de um candidato na base não significa culpa ou condenação.

## Visão geral

```mermaid
flowchart LR
    TSE["Dados abertos do TSE"] --> ZIP["ZIPs por UF"]
    ZIP --> PDF["12 mil+ PDFs"]
    PDF --> TEXT["Texto nativo + OCR"]
    TEXT --> NANO["Triagem com GPT-5.4 nano"]
    NANO --> MINI["Revisão com GPT-5.4 mini"]
    MINI --> VALID["Validação de evidências"]
    VALID --> TABLES["CSV por documento, processo e candidato"]
```

O fluxo detalhado, incluindo arquivos intermediários e decisões, está em
[Architecture.md](Architecture.md).

## Requisitos

- Python 3.11 ou superior;
- Tesseract OCR com o idioma português;
- uma chave da OpenAI API com créditos disponíveis;
- conexão com a internet para baixar os dados e executar a análise semântica;
- aproximadamente 7 GB para a execução atual; recomenda-se pelo menos 10 GB livres.

Os dados públicos são grandes. Na execução usada para desenvolver o projeto:

| Diretório | Espaço aproximado |
|---|---:|
| ZIPs brutos | 2,9 GB |
| PDFs descompactados | 2,9 GB |
| Textos, OCR e resultados | 705 MB |

O uso da OpenAI API é cobrado. O valor varia conforme quantidade e tamanho dos
documentos, preços vigentes, modelo e respostas geradas. Consulte o saldo e os
limites do projeto antes de iniciar.

## Instalação no Ubuntu, Debian ou GitHub Codespaces

Abra um terminal na raiz do repositório e instale o Tesseract:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-por
```

Crie e ative um ambiente virtual Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Confirme que o idioma português está disponível:

```bash
tesseract --list-langs
```

A lista deve conter `por`.

### macOS

Com Homebrew:

```bash
brew install python tesseract tesseract-lang
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

No Windows, recomenda-se usar WSL com uma distribuição Ubuntu e seguir as
instruções para Ubuntu acima.

## Configuração da OpenAI API

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Abra `.env` e preencha:

```dotenv
OPENAI_API_KEY=adicione_sua_chave_aqui
```

Não publique essa chave. O arquivo `.env` está listado no `.gitignore` e não deve
ser enviado ao Git. Também é possível configurar a chave somente no terminal:

```bash
export OPENAI_API_KEY="adicione_sua_chave_aqui"
```

A variável exportada tem prioridade sobre o conteúdo do `.env`.

## Executar todo o pipeline

Com o ambiente virtual ativo, execute na raiz do projeto:

```bash
python src/tse/run_pipeline.py
```

O comando executa ou retoma automaticamente:

1. download dos 27 ZIPs de certidões do TSE;
2. download do cadastro de candidatos de 2026;
3. descompactação dos PDFs por UF;
4. extração de texto e diagnóstico das páginas;
5. associação dos documentos aos candidatos pelo `SQ_CANDIDATO`;
6. OCR das páginas com texto insuficiente;
7. triagem completa com GPT-5.4 nano;
8. revisão dos casos selecionados com GPT-5.4 mini;
9. reparo síncrono de respostas que excederem o limite de saída;
10. validação das citações contra o texto de origem;
11. deduplicação e geração das tabelas.

O processamento com Batch API pode levar várias horas. A janela de processamento
de cada batch pode chegar a 24 horas.

### Retomar depois de uma interrupção

O pipeline registra o progresso em arquivos locais. Se o terminal fechar ou o
comando for interrompido com `Ctrl+C`, execute o mesmo comando novamente:

```bash
python src/tse/run_pipeline.py
```

Etapas concluídas são detectadas e ignoradas. PDFs, OCRs e respostas já obtidas não
são enviados novamente.

### Consultar o estado sem executar etapas

```bash
python src/tse/run_pipeline.py status
```

Esse comando consulta somente os arquivos locais. Ele não chama a OpenAI API.

### Usar arquivos brutos já baixados

Para impedir qualquer download do TSE:

```bash
python src/tse/run_pipeline.py --no-download
```

Nesse caso, os 27 ZIPs de certidões e `consulta_cand_2026.zip` devem estar em
`src/tse/data/raw/`.

### Ajustar paralelismo e intervalo dos batches

```bash
python src/tse/run_pipeline.py --workers 4 --interval 60
```

- `--workers` controla os processos usados na extração local;
- `--interval` controla os segundos entre consultas à Batch API.

## Onde ficam os resultados

Os resultados consolidados são gravados em:

```text
src/tse/data/pipeline/preliminary_results/
```

| Arquivo | Conteúdo |
|---|---|
| `documents_preliminary.csv` | Classificação e quantidade de registros por documento |
| `processes_preliminary.csv` | Candidato, processo, papel, classe, assunto, situação, resultado e documento |
| `candidates_preliminary.csv` | Quantidade de documentos e processos por candidato |
| `process_types_preliminary.csv` | Classes processuais agrupadas e normalizadas |
| `crime_subjects_preliminary.csv` | Assuntos criminais agrupados, como corrupção e violência doméstica |
| `summary.json` | Cobertura e contagens gerais |
| `CONCLUSAO.md` | Síntese da execução analisada durante o desenvolvimento |

Os CSVs usam UTF-8 com BOM para facilitar a abertura no Excel e em ferramentas
compatíveis com o padrão brasileiro de caracteres.

## Estrutura dos dados intermediários

```text
src/tse/data/
├── raw/                         # ZIPs originais
├── extracted/                   # PDFs separados por UF
└── pipeline/
    ├── texts/                   # Texto nativo por PDF
    ├── documents/               # Diagnóstico e metadados por PDF
    ├── ocr/                     # OCR seletivo por página
    ├── manifest.jsonl           # Índice de documentos
    ├── candidates.csv           # Vínculo inicial com cadastro TSE
    ├── batch_stage1_nano_v2/    # Triagem de todos os documentos
    ├── batch_stage2_mini_v1/    # Revisão dos casos selecionados
    ├── batch_stage2_repair_v*/  # Reparos de respostas incompletas
    └── preliminary_results/     # Tabelas consolidadas
```

O diretório `src/tse/data/` é ignorado pelo Git porque contém arquivos grandes e
resultados gerados.

## Como interpretar as tabelas

O pipeline considera um registro para a contagem quando a análise identifica:

- natureza criminal;
- vínculo explícito entre candidato e processo;
- evidência literal do processo;
- evidência literal do vínculo com o candidato.

Os processos numerados são deduplicados pela combinação candidato e número do
processo. Registros sem número são mantidos separadamente.

Os assuntos podem ser gerais dos autos e não necessariamente imputações
individualizadas. Recursos, cartas precatórias e autos derivados também podem
representar desdobramentos do mesmo fato.

As saídas recebem o nome `preliminary` porque são resultado de extração automática
e não passaram por revisão humana individual ou validação jurídica.

## Problemas comuns

### `Configure OPENAI_API_KEY no ambiente antes de enviar`

Confira se `.env` existe na raiz e contém exatamente `OPENAI_API_KEY=...`. Não use
`OPEN_API_KEY`.

### `Billing hard limit has been reached`

A conta ou projeto atingiu o limite de cobrança. Ajuste saldo, forma de pagamento
ou limite do projeto na plataforma OpenAI e execute novamente. O pipeline retomará
os lotes pendentes.

### `Enqueued token limit reached`

A organização atingiu o limite de tokens em fila. O modo automático espera o lote
ativo terminar e envia o próximo lote quando houver capacidade.

### `Instale o idioma português do Tesseract`

No Ubuntu ou Debian:

```bash
sudo apt-get install -y tesseract-ocr-por
```

### Falta de espaço em disco

Libere pelo menos 10 GB antes de uma execução completa. Não apague pastas `batch_*`
durante uma execução, pois elas contêm recibos necessários para retomada.

### Ver os argumentos disponíveis

```bash
python src/tse/run_pipeline.py --help
```

## Execução manual e desenvolvimento

Quem precisar executar etapas isoladas pode consultar:

- [Architecture.md](Architecture.md): desenho completo do sistema;
- [src/tse/PROCESS_EXTRACTION.md](src/tse/PROCESS_EXTRACTION.md): extração e batches;
- [src/tse/PDF_PROCESSING.md](src/tse/PDF_PROCESSING.md): diagnóstico dos PDFs.

Para verificar a sintaxe dos scripts:

```bash
python -m py_compile src/tse/*.py
```

## Escopo atual

O pipeline está configurado para as eleições de **2026**. URLs, nomes de arquivos,
modelos da OpenAI e preços podem mudar. Para outra eleição, será necessário
parametrizar o ano nos downloads, no cadastro e no padrão dos documentos.
