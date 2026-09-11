# Extração orientada à contagem de processos

## Pipeline completo

Execute ou retome todas as etapas a partir da raiz do projeto:

```bash
.venv/bin/python src/tse/run_pipeline.py
```

Use `status` para uma consulta somente local e `--no-download` para exigir que os
ZIPs já estejam presentes em `src/tse/data/raw`.

## Execução local em lote

```bash
python -m pip install -r requirements.txt
python src/tse/pipeline.py
python src/tse/ocr_pipeline.py
```

OCR requer `tesseract-ocr` e `tesseract-ocr-por` instalados no sistema.
Execute o OCR após o término do primeiro comando. A saída fica em `data/pipeline`:
texto e diagnóstico por documento, `manifest.jsonl`, `candidates.csv`,
`excluded.json` e `summary.json`. O OCR grava resultados separados em `ocr/`,
sem substituir o texto nativo. Seus resultados ainda exigem avaliação de qualidade.
Não classifica páginas vazias automaticamente como documentos negativos.

O lote retoma a extração nativa por hash do PDF e versão do pipeline. O cadastro
é cruzado novamente a cada execução; registros ausentes ou ambíguos ficam marcados.
A tabela contém candidaturas com documentos locais, não todas as candidaturas do TSE.
Uma imagem grande, isoladamente, não envia a página para OCR nesta etapa.

**Os dois comandos acima são etapas locais.**
Eles não chamam uma LLM, não geram descrições semânticas e não calculam
o total de candidatos com processos. Células de contagem vazias significam pendência,
nunca zero. O vínculo pelo nome do arquivo identifica quem enviou o documento;
a atribuição de um processo exige comparar também as partes. O piloto de SC é
um resultado separado e não é propagado como classificação dos demais arquivos.

### OpenAI Batch

Após o OCR, execute `python src/tse/semantic_batch.py prepare` para preparar os
arquivos de requisições sem enviar dados. Cada arquivo tem até 1.000 requisições
e 40 MB; o limite de tokens enfileirados depende da conta OpenAI. O modelo padrão
é `gpt-5-nano`, com esforço mínimo e saída JSON estruturada. Páginas longas são
fragmentadas com sobreposição, sem descarte de conteúdo.

Configure `OPENAI_API_KEY` no ambiente de execução ou no `.env` local ignorado
pelo Git. Nunca grave a chave em um arquivo versionado.
`python src/tse/semantic_batch.py submit` envia os arquivos e grava os IDs dos
lotes. `python src/tse/semantic_batch.py collect` consulta os lotes e baixa saídas
e erros disponíveis. Não reenvia arquivos que já tenham recibo. Se a conexão
cair durante a criação do lote, confira os lotes na conta antes de repetir:
o servidor pode ter aceitado uma operação cujo recibo local não foi salvo.

Para monitorar, baixar e reenviar todos os lotes automaticamente a cada minuto,
execute na raiz do projeto:

```bash
.venv/bin/python src/tse/semantic_batch.py watch \
  --output src/tse/data/pipeline/batch_stage1_nano_v2 \
  --interval 60
```

O comando retoma a execução pelos recibos existentes. Ele mantém apenas um lote
reenviado por vez para respeitar o limite de tokens enfileirados, baixa cada
resultado com gravação atômica e gera `validated.jsonl` quando todos terminarem.
Pode ser interrompido com `Ctrl+C` e executado novamente sem perder o progresso.

Depois da triagem com nano, prepare a revisão com mini dos documentos positivos,
inconclusivos, ilegíveis, fragmentados ou com erro/inconsistência:

```bash
.venv/bin/python src/tse/semantic_batch.py prepare \
  --root src/tse/data/pipeline \
  --output src/tse/data/pipeline/batch_stage2_mini_v1 \
  --model gpt-5.4-mini \
  --selection-from src/tse/data/pipeline/batch_stage1_nano_v2/validated.jsonl
```

Em seguida, use `watch` nessa nova pasta. A seleção exclui negativos e documentos
somente cíveis que passaram sem inconsistências na primeira etapa.

Para monitorar, baixar e reenviar todos os lotes automaticamente a cada minuto,
execute na raiz do projeto:

```bash
.venv/bin/python src/tse/semantic_batch.py watch \
  --output src/tse/data/pipeline/batch_stage1_nano_v2 \
  --interval 60
```

O comando retoma a execução pelos recibos existentes. Ele mantém apenas um lote
reenviado por vez para respeitar o limite de tokens enfileirados, baixa cada
resultado com gravação atômica e gera `validated.jsonl` quando todos terminarem.
Pode ser interrompido com `Ctrl+C` e executado novamente sem perder o progresso.

O desconto Batch é 50%, com janela de até 24h. Preços consultados em 07/09/2026:
GPT-5 nano padrão US$ 0,05/M entrada e US$ 0,40/M saída, antes do desconto.
Disponibilidade e limites da conta não foram testados sem credencial.

As respostas são propostas de extração. A validação semântica, conferência das
evidências e consolidação final por candidato ainda precisam ser executadas;
o coletor não transforma respostas brutas em contagens confirmadas.

Escopo: identificar registros criminais, incluindo inquéritos e processos sem
condenação. Preservar menções cíveis e eleitorais separadamente. Não inferir
condenação, situação atual ou crime a partir da simples existência de autos.

## Primeira triagem executável

```bash
python src/tse/triage_processes.py
```

Lê o manifesto e os textos da amostra. Produz `documents.jsonl` e `summary.json`
em `src/tse/data/process_triage_sample`. Use `--output-dir` para outra execução.
Não requer bibliotecas adicionais e não faz chamadas de LLM.

Agrupa menções de números no formato CNJ, inclusive com quebra de linha e
separador ponto, e guarda todas as ocorrências com página e trecho. Não valida
dígitos verificadores, não identifica números antigos e não distingue sozinho
processos principais de referências, recursos ou precedentes. Ausência de número
detectado não significa certidão negativa. Campos rotulados de assunto/classe
são sinais da página, sem atribuição automática a um processo.

## Estrutura a preencher na revisão ou extração semântica

Cada documento mantém nome, hash, UF, alertas de leitura, classificação e menções.
Cada menção contém número normalizado, evidências, natureza, vínculo com a pessoa,
assunto literal, situação processual e decisão de inclusão na contagem.

- `nature`: `criminal`, `civil`, `electoral_noncriminal`, `administrative`, `unknown`.
- `candidate_relationship`: investigado, acusado/réu, condenado, vítima, autor,
  terceiro, mera referência ou vínculo não verificado. Registrar evidência do papel.
- `subject`: assunto/crime conforme o documento; `null` quando não informado.
- `procedural_status`: situação na data do documento; `null` quando não informada.
- `include_in_count`: `true` só após confirmar natureza criminal e vínculo pertinente;
  `false` para exclusões justificadas; `null` enquanto houver dúvida.

O identificador extraído do nome do arquivo é provisório: confirmar contra cadastro
do TSE antes de preencher `candidate_id` e `candidate_name`. A busca inicial no
portal do TSE não confirmou a convenção do nome de arquivo. Não usar o primeiro
nome de pessoa encontrado no texto: pode ser magistrado, advogado ou outra parte.

Para consolidar, deduplicar por candidato confirmado e número normalizado. Manter
relações entre autos de origem, recursos e renumerações para não confundir quantidade
de autos com quantidade de fatos. Sem número, não inventar unicidade. Certidão
positiva sem identificação de autos tem contagem indeterminada. O total final deve
explicitar cobertura, inconclusivos e documentos não lidos.

## Validação inicial no texto da amostra

Estas são verificações de conteúdo textual, não de autenticidade nem de vínculo
com o cadastro eleitoral. Não houve revisão visual ou OCR.

| Documento | Página | Evidência | Interpretação para revisão |
|---|---|---|---|
| AM/2026AM40002531443_40017126892.pdf.pdf | 1 | `Número: 1033757-26.2025.4.01.0000`; `Classe: INQUÉRITO POLICIAL`; `Assuntos: Apropriação indébita Previdenciária, Sonegação de contribuição previdenciária` | Registro criminal com assunto explícito; a página identifica um investigado. Confirmar vínculo cadastral antes de contar por candidato. |
| DF/2026DF70002531335_70016842501.pdf.pdf | 1 | `Cumprimento de sentença, 0715405-49.2026.8.07.0003`; `Família.` | Cabeçalho positivo para ações cíveis e criminais, mas o registro listado é de família. O cabeçalho não basta para incluir no total criminal. |
| RR/2026RR230002548834_230017133625.pdf.pdf | 1 | `0600458-12.2026.6.23.0000`; `Processo de Registro` / `de Candidatura` | Petição em registro de candidatura, não evidência de processo criminal. |

Também foram encontrados números de processos de referência e autos citados no
histórico. Por isso, os totais da triagem são de menções, não de processos atribuídos.
Próximas etapas: revisar semanticamente os 135 documentos (inclusive sem números),
resolver os alertas de leitura e confirmar vínculos antes de calcular candidatos.

## Piloto semântico de SC

Resultado em `data/semantic_pilot/SC_240017134600.json`. É uma análise assistida
nesta sessão, não um extrator semântico automatizado nem uma chamada de API.
Foram inspecionados cabeçalho, encerramento e buscas no histórico. Cada evidência
guarda página, trecho literal e offsets de caracteres no texto daquela página.
Os trechos foram conferidos programaticamente contra o texto fonte.

A abertura identifica uma ação penal principal; a página 41 informa os assuntos.
Números de 20 dígitos sem pontuação ampliam a lista de referências, preservadas
separadamente. Não se presume que referências ou prefixos BNMP sejam processos
independentes da pessoa. Os assuntos são do processo como um todo, não acusações
individualizadas. Vínculo cadastral, situação processual e condenação permanecem
sem conclusão. Os nomes listados como réus não são uma lista de candidatos.

Para automatizar com uma LLM, enviar blocos com páginas e manter a identificação
do documento. Exigir evidências literais para cada campo, distinguir os assuntos
do processo de imputações por pessoa e consolidar por número com referências
separadas. Validar trechos e schema antes de aceitar resultados. A lista de réus
de um bloco não pode ser atribuída a outro processo por proximidade. Blocos sem
informação explícita devolvem campos nulos; ausência em um bloco não apaga
evidência encontrada em outro. Nenhuma contagem por candidato é liberada sem
confirmar o vínculo com o cadastro eleitoral.
