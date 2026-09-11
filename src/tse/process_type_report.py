"""Agrupa classes processuais da tabela preliminar em tipos comparáveis."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
import re
import unicodedata


DATA = Path(__file__).resolve().parent / 'data/pipeline/preliminary_results'


def plain(value):
    value = unicodedata.normalize('NFKD', value or '')
    return re.sub(r'\s+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip().lower()


def process_type(value):
    text = plain(value)
    if not text or text in {'0 - nao definida', 'nao informada'}:
        return 'Classe não informada'
    if 'inquerito' in text or 'investigatorio' in text or 'investigacao' in text:
        return 'Inquérito ou procedimento investigatório'
    if 'termo circunstanciado' in text or text == 'juizado especial criminal':
        return 'Termo circunstanciado / Juizado Especial Criminal'
    if 'acao penal' in text:
        if 'juri' in text:
            return 'Ação penal do Tribunal do Júri'
        if 'sumarissimo' in text:
            return 'Ação penal — procedimento sumaríssimo'
        if 'sumario' in text:
            return 'Ação penal — procedimento sumário'
        if 'ordinario' in text:
            return 'Ação penal — procedimento ordinário'
        return 'Ação penal — classe genérica ou especial'
    if 'execucao' in text and ('pena' in text or 'criminal' in text):
        return 'Execução penal ou da pena'
    if any(term in text for term in ('apelacao', 'recurso', 'agravo', 'embargos')):
        return 'Recurso criminal'
    if 'carta precatoria' in text or 'carta de ordem' in text:
        return 'Carta precatória ou de ordem criminal'
    if 'queixa' in text or all(term in text for term in ('calunia', 'injuria', 'difamacao')):
        return 'Queixa-crime / crimes contra a honra'
    if 'representacao criminal' in text or 'noticia de crime' in text:
        return 'Representação criminal ou notícia-crime'
    if 'medida protetiva' in text or 'maria da penha' in text:
        return 'Medida protetiva de urgência'
    if 'habeas corpus' in text:
        return 'Habeas corpus criminal'
    if any(term in text for term in ('cautelar', 'busca e apreensao', 'prisao')):
        return 'Medida cautelar criminal'
    if 'peticao' in text:
        return 'Petição criminal'
    if any(term in text for term in ('civil', 'improbidade')):
        return 'Possível registro cível ou classificação indevida'
    return 'Outros procedimentos criminais'


def build(input_file, output_file):
    with input_file.open(encoding='utf-8-sig') as source:
        rows = list(csv.DictReader(source))
    groups = defaultdict(lambda: {'links': 0, 'numbers': set(), 'candidates': set(),
                                  'without_number': 0, 'raw_classes': set()})
    for row in rows:
        source = ('revisado_mini' if row['fonte_analise'] == 'stage2_mini'
                  else 'provisorio_nano')
        key = (source, process_type(row['classe']))
        group = groups[key]
        group['links'] += 1
        number = re.sub(r'\D', '', row['numero_processo'])
        if number:
            group['numbers'].add(number)
        else:
            group['without_number'] += 1
        group['candidates'].add((row['ano'], row['uf'], row['sq_candidato']))
        if row['classe'].strip():
            group['raw_classes'].add(row['classe'].strip())
    output=[]
    for (source, kind), group in groups.items():
        output.append({
            'fonte': source, 'tipo_normalizado': kind,
            'relacoes_candidato_processo': group['links'],
            'processos_numerados_unicos': len(group['numbers']),
            'registros_sem_numero': group['without_number'],
            'candidatos_distintos': len(group['candidates']),
            'classes_originais_distintas': len(group['raw_classes']),
        })
    output.sort(key=lambda row: (row['fonte'], -row['relacoes_candidato_processo'],
                                 row['tipo_normalizado']))
    with output_file.open('w', encoding='utf-8-sig', newline='') as target:
        writer=csv.DictWriter(target, fieldnames=list(output[0]))
        writer.writeheader(); writer.writerows(output)
    for row in output:
        if row['fonte']=='revisado_mini':
            print(row['tipo_normalizado'], row['relacoes_candidato_processo'],
                  row['processos_numerados_unicos'], sep=' | ')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATA/'processes_preliminary.csv')
    parser.add_argument('--output', type=Path, default=DATA/'process_types_preliminary.csv')
    args=parser.parse_args(); build(args.input,args.output)
