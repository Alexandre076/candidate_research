# Diagnóstico inicial dos PDFs

Requer Python 3.11+ e as dependências de `requirements.txt`.
Na raiz do projeto, em um ambiente virtual:

```bash
python -m pip install -r requirements.txt
python src/tse/analyze_pdfs.py
```

Por padrão, seleciona até cinco PDFs por UF, com semente 42, e grava em
`src/tse/data/processed_sample/`. Os caminhos padrão independem do diretório
de execução. Para uma amostra maior, use uma nova pasta de saída:

```bash
python src/tse/analyze_pdfs.py --sample-per-uf 20 --output-dir src/tse/data/processed_sample_20
```

Para analisar a base toda, use `--sample-per-uf 0` e outra pasta de saída.
A CLI recusa uma pasta de saída não vazia para preservar execuções anteriores.

## Saídas

- `summary.json`: total de PDFs disponíveis, tamanho da amostra e contagens de diagnóstico.
- `manifest.jsonl`: um registro por documento, com diagnóstico de cada página.
- `<UF>/<nome original>.txt`: texto nativo com separadores de página.
- `<UF>/<nome original>.metadata.json`: hash SHA-256, origem, método e indicadores por página.

O status do documento indica sucesso técnico de leitura, não completude do
conteúdo. Páginas com pouco texto, caracteres de substituição ou uma imagem
ocupando pelo menos 60% da área recebem `review` e `ocr_candidate: true`.
Páginas com erro são contadas separadamente e precisam de investigação.
Uma página vazia também pode receber `review`. Uma camada de OCR já existente
pode produzir texto e ainda assim merecer revisão pela presença de imagem grande.
As regras são heurísticas; imagens em mosaico e texto incorretamente decodificado
sem caracteres de substituição podem escapar. Não há garantia de ordem de leitura
em layouts complexos. O script não executa OCR nem envia documentos para serviços.

## Próxima etapa

Inspecionar visualmente exemplos com `review` e `native_text`, calibrar as regras
e adicionar OCR seletivo em português. Só então agrupar documentos por padrões
de conteúdo e selecionar exemplos de cada família para sugerir e validar schemas.
Uma amostra por UF é um ponto de partida, não garante cobertura de modelos raros.
