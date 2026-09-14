"""Generate charts and an HTML report from consolidated pipeline results."""
import argparse
import base64
import csv
from collections import Counter
import os
from pathlib import Path
import re
import tempfile
import unicodedata

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) /
                                          'candidate-research-matplotlib'))
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from wordcloud import WordCloud


DATA = Path(__file__).resolve().parent / 'data/pipeline/preliminary_results'
REGIONS = {
    'North': {'AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO'},
    'Northeast': {'AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE'},
    'Central-West': {'DF', 'GO', 'MT', 'MS'},
    'Southeast': {'ES', 'MG', 'RJ', 'SP'},
    'South': {'PR', 'RS', 'SC'},
}
COLORS = {
    'blue': '#22577A', 'teal': '#38A3A5', 'green': '#57CC99',
    'yellow': '#F4B942', 'red': '#D1495B', 'gray': '#64748B',
}
LANGUAGE = 'en'
REGION_PT = {'North': 'Norte', 'Northeast': 'Nordeste',
             'Central-West': 'Centro-Oeste', 'Southeast': 'Sudeste', 'South': 'Sul'}


def tr(english, portuguese):
    return portuguese if LANGUAGE == 'pt' else english


def chart_path(output, stem):
    suffix = '' if LANGUAGE == 'pt' else '.en'
    return output / f'{stem}{suffix}.png'
SUBJECT_LABELS = {
    'Crimes contra a honra': 'Crimes against honor',
    'Violência doméstica e familiar': 'Domestic and family violence',
    'Crimes de responsabilidade': 'Crimes of official responsibility',
    'Ameaça': 'Threats', 'Lesão corporal': 'Bodily injury',
    'Crimes em licitações ou contratos públicos': 'Public procurement or contract crimes',
    'Crimes patrimoniais': 'Property crimes',
    'Estelionato ou outras fraudes': 'Fraud and similar offenses',
    'Corrupção': 'Corruption',
    'Crimes contra a administração pública': 'Crimes against public administration',
    'Organização ou associação criminosa': 'Criminal organization or association',
    'Peculato ou desvio de recursos públicos': 'Embezzlement or diversion of public funds',
    'Lavagem ou ocultação de bens': 'Money laundering or concealment of assets',
    'Desobediência, desacato ou resistência': 'Disobedience, contempt, or resistance',
    'Homicídio': 'Homicide',
}
TYPE_LABELS = {
    'Ação penal — procedimento ordinário': 'Criminal action — ordinary procedure',
    'Inquérito ou procedimento investigatório': 'Police inquiry or investigation',
    'Outros procedimentos criminais': 'Other criminal procedures',
    'Ação penal — procedimento sumaríssimo': 'Criminal action — petty-offense procedure',
    'Queixa-crime / crimes contra a honra': 'Private complaint / crimes against honor',
    'Recurso criminal': 'Criminal appeal',
    'Carta precatória ou de ordem criminal': 'Criminal letter rogatory or order',
    'Ação penal — classe genérica ou especial': 'Criminal action — generic or special class',
    'Ação penal — procedimento sumário': 'Criminal action — summary procedure',
    'Termo circunstanciado / Juizado Especial Criminal': 'Incident report / Special Criminal Court',
    'Representação criminal ou notícia-crime': 'Criminal representation or crime report',
    'Petição criminal': 'Criminal petition',
    'Medida protetiva de urgência': 'Emergency protective measure',
    'Execução penal ou da pena': 'Sentence enforcement',
}

DESCRIPTION_STOPWORDS = {
    'acao', 'acoes', 'acusado', 'assunto', 'assuntos', 'autos', 'candidato',
    'candidata', 'classe', 'criminal', 'criminais', 'crime', 'crimes', 'descricao',
    'informada', 'informado', 'informados', 'judicial', 'numero', 'penal', 'polo',
    'passivo', 'procedimento', 'processo', 'processos', 'reu', 'situacao',
    'sobre', 'contra', 'consta', 'constam', 'conforme', 'trata', 'grau', 'instancia',
    'artigo', 'inciso', 'caput', 'termos', 'parte', 'partes', 'relacao', 'registro',
    'sem', 'com', 'dos', 'das', 'uma', 'para', 'pela', 'pelo', 'que', 'nao', 'nos',
    'nas', 'por', 'seu', 'sua', 'aos', 'ainda', 'atualmente', 'encontra', 'foram',
    'apelacao', 'apelado', 'apelante', 'arquivada', 'arquivado', 'arquivados',
    'arquivamento', 'autor', 'baixa', 'baixado', 'carta', 'certidao', 'como',
    'competencia', 'decisao', 'definitiva', 'definitivamente', 'denunciado',
    'declarado', 'declarante', 'distribuicao', 'distribuido', 'execucao', 'executado',
    'extincao', 'extinta', 'extinto', 'fase', 'fato', 'figura', 'geral', 'gerais',
    'indiciado', 'indicado', 'investigado', 'inquerito', 'julgado', 'julgamento',
    'medidas', 'ordinario', 'papel',
    'peticao', 'policial', 'precatoria', 'prazo', 'procedimental', 'processual',
    'querelado', 'recebida', 'recurso', 'registrada', 'remessa', 'requerido',
    'resultado', 'status', 'sentenca', 'sumario', 'sumarissimo', 'termo', 'transito',
    'tramitacao', 'vinculacao', 'vinculado',
}


def read_csv(path):
    with path.open(encoding='utf-8-sig') as source:
        return list(csv.DictReader(source))


def integer(value):
    return int(value or 0)


def style():
    plt.rcParams.update({
        'figure.facecolor': 'white', 'axes.facecolor': '#F8FAFC',
        'axes.edgecolor': '#CBD5E1', 'axes.titleweight': 'bold',
        'axes.titlesize': 14, 'font.size': 10, 'grid.color': '#E2E8F0',
        'grid.linewidth': .8,
    })


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def horizontal_bars(labels, values, title, xlabel, path, color):
    fig, ax = plt.subplots(figsize=(10, max(5, len(labels) * .43)))
    positions = range(len(labels))
    ax.barh(positions, values, color=color)
    ax.set_yticks(list(positions), labels)
    ax.invert_yaxis()
    ax.set_title(title, loc='left')
    ax.set_xlabel(xlabel)
    ax.grid(axis='x'); ax.set_axisbelow(True)
    maximum = max(values, default=1)
    for y, value in enumerate(values):
        ax.text(value + maximum * .012, y, f'{value:,}', va='center', fontsize=9)
    ax.set_xlim(0, maximum * 1.14)
    save(fig, path)


def lollipop_chart(labels, values, title, xlabel, path, color):
    fig, ax = plt.subplots(figsize=(10, max(5, len(labels) * .43)))
    positions = list(range(len(labels)))
    ax.hlines(positions, 0, values, color='#CBD5E1', linewidth=2.2)
    ax.scatter(values, positions, color=color, s=75, zorder=3,
               edgecolor='white', linewidth=1)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_title(title, loc='left')
    ax.set_xlabel(xlabel)
    ax.grid(axis='x'); ax.set_axisbelow(True)
    maximum = max(values, default=1)
    for y, value in enumerate(values):
        ax.text(value + maximum * .015, y, f'{value:,}', va='center', fontsize=9)
    ax.set_xlim(0, maximum * 1.15)
    save(fig, path)


def document_classification_chart(documents, output):
    labels_en = {
        'negative_criminal': 'Negative criminal certificate',
        'positive_criminal': 'Positive criminal indication',
        'civil_only': 'Civil only', 'inconclusive': 'Inconclusive',
        'unreadable': 'Unreadable', 'fragment': 'Fragment',
    }
    labels_pt = {
        'negative_criminal': 'Certidão criminal negativa',
        'positive_criminal': 'Indicação criminal positiva',
        'civil_only': 'Somente cível', 'inconclusive': 'Inconclusivo',
        'unreadable': 'Ilegível', 'fragment': 'Fragmento',
    }
    labels = labels_pt if LANGUAGE == 'pt' else labels_en
    counts = Counter(row['classificacao'] for row in documents)
    ordered = sorted(counts, key=counts.get, reverse=True)
    names = [labels.get(key, key) for key in ordered]
    values = [counts[key] for key in ordered]
    palette = [COLORS['blue'], COLORS['red'], COLORS['teal'], COLORS['yellow'],
               COLORS['gray'], COLORS['green']][:len(values)]
    fig, ax = plt.subplots(figsize=(10, 6.2))
    wedges, _, autotexts = ax.pie(
        values, startangle=90, counterclock=False, colors=palette,
        wedgeprops={'width': .38, 'edgecolor': 'white', 'linewidth': 2},
        autopct=lambda pct: f'{pct:.1f}%' if pct >= 2 else '', pctdistance=.8)
    for text in autotexts:
        text.set_fontsize(9); text.set_color('#172033')
    ax.text(0, .08, f'{sum(values):,}', ha='center', va='center', fontsize=24,
            fontweight='bold', color=COLORS['blue'])
    ax.text(0, -.10, tr('documents', 'documentos'), ha='center', va='center',
            color=COLORS['gray'])
    legend_labels = [f'{name} — {value:,}' for name, value in zip(names, values)]
    ax.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(.92, .5),
              frameon=False)
    ax.set_title(tr('Document classification', 'Classificação dos documentos'),
                 loc='left', pad=18)
    save(fig, chart_path(output, '01_document_classification'))


def candidate_distribution_chart(candidates, output):
    counts = [integer(row['numbered_processes']) + integer(row['records_without_number'])
              for row in candidates if row['has_reviewed_record_preliminary'] == 'True']
    buckets = Counter(str(value) if value < 10 else '10+' for value in counts)
    labels = [str(value) for value in range(1, 10)] + ['10+']
    values = [buckets[label] for label in labels]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    positions = list(range(len(labels)))
    ax.fill_between(positions, values, color=COLORS['teal'], alpha=.22)
    ax.plot(positions, values, color=COLORS['teal'], linewidth=3, marker='o',
            markersize=8, markeredgecolor='white', markeredgewidth=1.3)
    ax.set_xticks(positions, labels)
    ax.set_title(tr('Case records per candidate with a record',
                    'Registros processuais por candidato com registro'), loc='left')
    ax.set_xlabel(tr('Distinct case records', 'Registros processuais distintos'))
    ax.set_ylabel(tr('Candidates', 'Candidatos'))
    ax.grid(axis='y'); ax.set_axisbelow(True)
    for x, value in enumerate(values):
        ax.text(x, value + max(values) * .025, str(value), ha='center')
    ax.set_ylim(0, max(values) * 1.15)
    save(fig, chart_path(output, '02_cases_per_candidate'))


def regional_chart(candidates, processes, output):
    region_rows = []
    for region, states in REGIONS.items():
        total = sum(row['uf'] in states for row in candidates)
        involved = sum(row['uf'] in states and
                       row['has_reviewed_record_preliminary'] == 'True'
                       for row in candidates)
        records = sum(row['uf'] in states for row in processes)
        region_rows.append({
            'region': region, 'candidates_analyzed': total,
            'candidates_with_records': involved,
            'candidate_rate': involved / total if total else 0,
            'candidate_case_records': records,
        })
    region_rows.sort(key=lambda row: row['candidate_rate'], reverse=True)
    with (output / 'regional_summary.csv').open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=list(region_rows[0]))
        writer.writeheader(); writer.writerows(region_rows)

    fig, ax = plt.subplots(figsize=(11, 5.8))
    names = [REGION_PT[row['region']] if LANGUAGE == 'pt' else row['region']
             for row in region_rows]
    raw_values = [[
        row['candidates_analyzed'], row['candidates_with_records'],
        row['candidate_rate'], row['candidate_case_records'],
    ] for row in region_rows]
    column_maxima = [max(row[column] for row in raw_values)
                     for column in range(4)]
    normalized = [[value / column_maxima[column] if column_maxima[column] else 0
                   for column, value in enumerate(row)] for row in raw_values]
    intensity_colors = LinearSegmentedColormap.from_list(
        'regional_intensity', ['#DBEAFE', '#60A5FA', '#FCA5A5', '#B91C1C'])
    image = ax.imshow(normalized, cmap=intensity_colors, vmin=0, vmax=1,
                      aspect='auto')
    columns = [
        tr('Analyzed', 'Analisados'), tr('With records', 'Com registros'),
        tr('Rate', 'Proporção'), tr('Case records', 'Registros processuais'),
    ]
    ax.set_xticks(range(4), columns)
    ax.set_yticks(range(len(names)), names)
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False,
                   length=0, pad=10)
    for row_index, values in enumerate(raw_values):
        for column, value in enumerate(values):
            label = f'{value:.1%}' if column == 2 else f'{value:,}'
            color = 'white' if normalized[row_index][column] > .58 else '#172033'
            ax.text(column, row_index, label, ha='center', va='center',
                    color=color, fontsize=11, fontweight='bold')
    for edge in ax.spines.values():
        edge.set_visible(False)
    ax.set_xticks([x - .5 for x in range(1, 4)], minor=True)
    ax.set_yticks([y - .5 for y in range(1, len(names))], minor=True)
    ax.grid(which='minor', color='white', linewidth=4)
    ax.tick_params(which='minor', bottom=False, left=False)
    ax.set_title(tr('Regional comparison', 'Comparação regional'), loc='left', pad=20)
    colorbar = fig.colorbar(image, ax=ax, fraction=.025, pad=.035)
    colorbar.set_label(tr('Relative intensity within each indicator',
                          'Intensidade relativa em cada indicador'))
    colorbar.set_ticks([0, .5, 1], labels=[tr('Low', 'Baixa'),
                                           tr('Medium', 'Média'),
                                           tr('High', 'Alta')])
    save(fig, chart_path(output, '03_regions'))
    return region_rows


def subject_chart(subjects, output):
    excluded = {'Causa criminal não informada', 'Outros assuntos não normalizados',
                'Improbidade administrativa — revisar natureza'}
    rows = [row for row in subjects
            if row['fonte'] == 'revisado_mini'
            and row['tema_criminal_normalizado'] not in excluded]
    rows.sort(key=lambda row: integer(row['processos_numerados_unicos']), reverse=True)
    rows = rows[:15]
    horizontal_bars([(row['tema_criminal_normalizado'] if LANGUAGE == 'pt' else
                      SUBJECT_LABELS.get(row['tema_criminal_normalizado'],
                                         row['tema_criminal_normalizado'])) for row in rows],
                    [integer(row['processos_numerados_unicos']) for row in rows],
                    tr('Most frequent identifiable criminal subjects',
                       'Assuntos criminais identificáveis mais frequentes'),
                    tr('Unique numbered cases', 'Processos numerados únicos'),
                    chart_path(output, '04_criminal_subjects'),
                    COLORS['red'])


def process_type_chart(types, output):
    rows = [row for row in types if row['fonte'] == 'revisado_mini']
    rows.sort(key=lambda row: integer(row['relacoes_candidato_processo']), reverse=True)
    rows = rows[:14]
    labels = [(row['tipo_normalizado'] if LANGUAGE == 'pt' else
               TYPE_LABELS.get(row['tipo_normalizado'], row['tipo_normalizado']))
              for row in rows]
    values = [integer(row['relacoes_candidato_processo']) for row in rows]
    display_labels = [f'{rank}. {label}'
                      for rank, label in enumerate(labels, 1)]
    positions = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(11, max(7, len(rows) * .55)))
    ax.barh(positions, values, color=COLORS['blue'], height=.68, alpha=.92)
    ax.set_yticks(positions, display_labels)
    ax.invert_yaxis()
    ax.set_title(tr('Most frequent procedural classes',
                    'Classes processuais mais frequentes'), loc='left')
    ax.set_xlabel(tr('Candidate–case records', 'Relações candidato–processo'))
    ax.grid(axis='x'); ax.set_axisbelow(True)
    maximum = max(values, default=1)
    for y, value in enumerate(values):
        ax.text(value + maximum * .012, y, f'{value:,}', va='center',
                fontweight='bold')
    ax.set_xlim(0, maximum * 1.14)
    save(fig, chart_path(output, '05_process_types'))


def candidate_names_chart(candidates, output):
    rows = []
    for row in candidates:
        count = integer(row['numbered_processes']) + integer(row['records_without_number'])
        if count:
            rows.append((count, f'{row["nome"].title()} ({row["uf"]})'))
    rows.sort(key=lambda item: (-item[0], item[1]))
    rows = rows[:20]
    values = [count for count, _ in rows]
    labels = [f'{rank}. {label}' for rank, (_, label) in enumerate(rows, 1)]
    positions = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(11, max(7, len(rows) * .43)))
    ax.barh(positions, values, color=COLORS['teal'], height=.68, alpha=.92)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_title(tr('Candidates with the most associated case records',
                    'Candidatos com mais registros processuais associados'), loc='left')
    ax.set_xlabel(tr('Distinct case records from automated extraction',
                     'Registros distintos da extração automática'))
    ax.grid(axis='x'); ax.set_axisbelow(True)
    maximum = max(values, default=1)
    for y, value in enumerate(values):
        ax.text(value + maximum * .015, y, f'{value:,}', va='center',
                fontweight='bold')
    ax.set_xlim(0, maximum * 1.14)
    save(fig, chart_path(output, '06_candidates_by_case_records'))


def normalized_token(value):
    return ''.join(character for character in unicodedata.normalize('NFD', value.lower())
                   if unicodedata.category(character) != 'Mn')


def description_wordcloud(processes, candidates, output):
    candidate_words = {
        normalized_token(word)
        for row in candidates for word in re.findall(r"[A-Za-zÀ-ÿ]+", row['nome'])
        if len(word) >= 4
    }
    frequencies = Counter()
    for row in processes:
        for raw_word in re.findall(r"[A-Za-zÀ-ÿ]+", row.get('descricao', '')):
            word = normalized_token(raw_word)
            if (len(word) >= 4 and word not in DESCRIPTION_STOPWORDS
                    and word not in candidate_words):
                frequencies[word] += 1
    cloud = WordCloud(
        width=1600, height=760, background_color='white', colormap='viridis',
        max_words=100, prefer_horizontal=.88, relative_scaling=.45,
        random_state=42, collocations=False, margin=5,
    ).generate_from_frequencies(frequencies)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(cloud, interpolation='bilinear')
    ax.axis('off')
    ax.set_title(tr('Recurring terms in criminal case descriptions (original Portuguese)',
                    'Termos recorrentes nas descrições dos processos criminais'),
                 loc='left', pad=14)
    save(fig, chart_path(output, '07_description_wordcloud'))


def write_html(output, metrics, regions):
    cards = ''.join(
        f'<div class="card"><strong>{value}</strong><span>{label}</span></div>'
        for value, label in metrics
    )
    region_rows = ''.join(
        '<tr>' + ''.join([
            f'<td>{REGION_PT[row["region"]] if LANGUAGE == "pt" else row["region"]}</td>', f'<td>{row["candidates_analyzed"]:,}</td>',
            f'<td>{row["candidates_with_records"]:,}</td>',
            f'<td>{row["candidate_rate"]:.1%}</td>',
            f'<td>{row["candidate_case_records"]:,}</td>',
        ]) + '</tr>' for row in regions
    )
    charts = [
        (tr('Document classification', 'Classificação dos documentos'), chart_path(output, '01_document_classification').name),
        (tr('Records per candidate', 'Registros por candidato'), chart_path(output, '02_cases_per_candidate').name),
        (tr('Regional heat map', 'Mapa de calor regional'), chart_path(output, '03_regions').name),
        (tr('Criminal subjects', 'Assuntos criminais'), chart_path(output, '04_criminal_subjects').name),
        (tr('Procedural classes', 'Classes processuais'), chart_path(output, '05_process_types').name),
        (tr('Candidates by associated case records', 'Candidatos por registros associados'), chart_path(output, '06_candidates_by_case_records').name),
        (tr('Recurring terms in case descriptions', 'Termos recorrentes nas descrições'), chart_path(output, '07_description_wordcloud').name),
    ]
    figures = ''
    for title, filename in charts:
        encoded = base64.b64encode((output / filename).read_bytes()).decode('ascii')
        figures += (f'<section><h2>{title}</h2>'
                    f'<img src="data:image/png;base64,{encoded}" alt="{title}"></section>')
    lang = 'pt-BR' if LANGUAGE == 'pt' else 'en'
    title = tr('TSE certificate analysis — automated insights',
               'Análise das certidões do TSE — insights automáticos')
    html = f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f1f5f9;color:#172033}}
main{{max-width:1200px;margin:auto;padding:32px}} h1{{margin-bottom:8px}}
.note{{background:#fff7d6;border-left:5px solid #f4b942;padding:16px;margin:24px 0}}
.source{{background:#eaf4fb;border-left:5px solid #22577a;padding:16px;margin:20px 0}}
.source a{{color:#174d6d;font-weight:bold}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}}
.card,section{{background:white;border-radius:10px;padding:18px;box-shadow:0 2px 8px #0f172a14}}
.card strong{{display:block;font-size:30px;color:#22577a}} .card span{{color:#526175}}
.charts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;margin-top:22px}}
.charts section{{margin:0;min-width:0}} section{{margin-top:22px}} img{{width:100%;height:auto}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:9px;text-align:right;border-bottom:1px solid #e2e8f0}} th:first-child,td:first-child{{text-align:left}}
@media (max-width:800px){{.charts{{grid-template-columns:1fr}} main{{padding:18px}}}}
</style></head><body><main><h1>{tr('TSE certificate analysis', 'Análise das certidões do TSE')}</h1>
<p>{tr('Automated insights from candidate-submitted criminal record certificates.', 'Insights automáticos das certidões criminais apresentadas pelos candidatos.')}</p>
<p><a href="{tr('index.html', 'index.en.html')}">{tr('Ver em português', 'View in English')}</a></p>
<div class="source"><strong>{tr('Original data source:', 'Fonte dos dados originais:')}</strong>
{tr('the candidate registry and criminal record certificate PDFs were obtained from the Brazilian Superior Electoral Court (TSE) Open Data Portal. View the official', 'o cadastro de candidatos e as certidões criminais em PDF foram obtidos no Portal de Dados Abertos do Tribunal Superior Eleitoral (TSE). Consulte o conjunto oficial')}
<a href="https://dadosabertos.tse.jus.br/pt_BR/dataset/candidatos-2026" target="_blank" rel="noopener noreferrer">{tr('Candidates — 2026 dataset', 'Candidatos — 2026')}</a>.
{tr('This dashboard contains derived automated analyses and is not an official TSE classification.', 'Este painel contém análises automáticas derivadas e não constitui uma classificação oficial do TSE.')}</div>
<div class="note"><strong>{tr('Interpretation:', 'Interpretação:')}</strong>
{tr('a case record may be an inquiry, investigation, appeal, or case without judgment. It does not imply guilt or conviction. Subjects may apply to the case as a whole rather than to an individual candidate.', 'um registro pode ser inquérito, investigação, recurso ou processo sem julgamento. Ele não implica culpa ou condenação. Os assuntos podem se aplicar ao processo como um todo, e não individualmente ao candidato.')}</div>
<div class="cards">{cards}</div><div class="charts">{figures}</div>
<section><h2>{tr('Regional summary', 'Resumo regional')}</h2><table><thead><tr><th>{tr('Region', 'Região')}</th><th>{tr('Analyzed', 'Analisados')}</th>
<th>{tr('With records', 'Com registros')}</th><th>{tr('Rate', 'Proporção')}</th><th>{tr('Case records', 'Registros processuais')}</th></tr></thead><tbody>{region_rows}</tbody></table></section>
</main></body></html>'''
    target = output / ('index.html' if LANGUAGE == 'pt' else 'index.en.html')
    target.write_text(html, encoding='utf-8')


def generate(input_dir, output):
    global LANGUAGE
    output.mkdir(parents=True, exist_ok=True); style()
    candidates = read_csv(input_dir / 'candidates_preliminary.csv')
    processes = read_csv(input_dir / 'processes_preliminary.csv')
    documents = read_csv(input_dir / 'documents_preliminary.csv')
    subjects = read_csv(input_dir / 'crime_subjects_preliminary.csv')
    types = read_csv(input_dir / 'process_types_preliminary.csv')
    involved = sum(row['has_reviewed_record_preliminary'] == 'True' for row in candidates)
    for language in ('pt', 'en'):
        LANGUAGE = language
        document_classification_chart(documents, output)
        candidate_distribution_chart(candidates, output)
        regions = regional_chart(candidates, processes, output)
        subject_chart(subjects, output); process_type_chart(types, output)
        candidate_names_chart(candidates, output)
        description_wordcloud(processes, candidates, output)
        metrics = [
            (f'{len(documents):,}', tr('documents analyzed', 'documentos analisados')),
            (f'{len(candidates):,}', tr('candidates analyzed', 'candidatos analisados')),
            (f'{involved:,}', tr('candidates with records', 'candidatos com registros')),
            (f'{involved / len(candidates):.1%}', tr('candidate share', 'proporção de candidatos')),
            (f'{len(processes):,}', tr('candidate–case records', 'relações candidato–processo')),
        ]
        write_html(output, metrics, regions)
    print(f'Generated bilingual charts, {output / "index.html"} and {output / "index.en.html"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATA)
    parser.add_argument('--output', type=Path, default=DATA / 'insights')
    args = parser.parse_args(); generate(args.input, args.output)
