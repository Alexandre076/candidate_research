"""Agrupa assuntos literais dos processos em temas criminais preliminares."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
import re
import unicodedata


DATA = Path(__file__).resolve().parent / 'data/pipeline/preliminary_results'


def plain(value):
    value = unicodedata.normalize('NFKD', value or '')
    return ''.join(c for c in value if not unicodedata.combining(c)).lower()


RULES = [
    ('Violência doméstica e familiar', r'violencia domestica|maria da penha|medida protetiva'),
    ('Corrupção', r'corrupcao'),
    ('Peculato ou desvio de recursos públicos', r'peculato|desvio de recurso'),
    ('Crimes em licitações ou contratos públicos', r'licitac|licitatorio'),
    ('Crimes contra a honra', r'calunia|injuria|difamacao|crimes contra a honra'),
    ('Lavagem ou ocultação de bens', r'lavagem|ocultacao de bens'),
    ('Organização ou associação criminosa', r'organizacao criminosa|associacao criminosa|quadrilha|bando'),
    ('Ameaça', r'ameaca'),
    ('Lesão corporal', r'lesao corporal'),
    ('Homicídio', r'homicidio'),
    ('Drogas', r'trafico|antitoxico|entorpecente|lei 11\.343'),
    ('Estelionato ou outras fraudes', r'estelionato|outras fraudes'),
    ('Crimes tributários ou previdenciários', r'ordem tributaria|crime tributario|sonegacao|contribuicao previdenciaria'),
    ('Falsidade ou uso de documento falso', r'falsidade|documento falso|falsa identidade|dados falsos'),
    ('Crimes de responsabilidade', r'crime[s]? de responsabilidade|decreto.?lei.*201|dl 201'),
    ('Crimes contra a administração pública', r'concussao|prevaricacao|trafico de influencia|advocacia administrativa|contra a administracao'),
    ('Crimes patrimoniais', r'roubo|furto|receptacao|apropriacao indebita'),
    ('Crimes sexuais', r'estupro|sexual|atentado violento ao pudor|ultraje publico ao pudor'),
    ('Armas', r'sistema nacional de armas|porte de arma|posse de arma'),
    ('Abuso de autoridade', r'abuso de autoridade|lei n?.?13\.869'),
    ('Crimes ambientais', r'crime[s]? ambientais|contra a flora|lei n?.?9\.605'),
    ('Discriminação ou intolerância', r'injuria racial|intolerancia|preconceituosa|racismo'),
    ('Desobediência, desacato ou resistência', r'desobediencia|desacato|resistencia'),
    ('Contrabando ou descaminho', r'contrabando|descaminho'),
    ('Improbidade administrativa — revisar natureza', r'improbidade administrativa'),
]
GENERIC = re.compile(
    r'^direito penal$|ato[s]? processua|citacao|intimacao|notificacao|'
    r'investigacao penal|procedimento investigatorio|prisao em flagrante|'
    r'carta precatoria|representacao criminal|noticia de crime|execucoes penais', re.I
)


def themes(subjects):
    found=set(); meaningful=False
    for subject in subjects:
        text=plain(subject).strip()
        matched=False
        for label, pattern in RULES:
            if re.search(pattern, text):
                found.add(label); matched=True
        if matched or not GENERIC.search(text):
            meaningful=True
    if found:
        return found
    return {'Outros assuntos não normalizados' if meaningful else 'Causa criminal não informada'}


def build(input_file, output_file):
    with input_file.open(encoding='utf-8-sig') as source:
        rows=list(csv.DictReader(source))
    groups=defaultdict(lambda: {'links':0, 'numbers':set(), 'candidates':set(), 'documents':set()})
    for row in rows:
        source=('revisado_mini' if row['fonte_analise']=='stage2_mini' else 'provisorio_nano')
        subjects=[s.strip() for s in row['assuntos'].split(' | ') if s.strip()]
        for theme in themes(subjects):
            group=groups[(source,theme)]; group['links']+=1
            number=re.sub(r'\D','',row['numero_processo'])
            if number: group['numbers'].add(number)
            group['candidates'].add((row['ano'],row['uf'],row['sq_candidato']))
            group['documents'].add(row['documento'])
    output=[]
    for (source,theme),group in groups.items():
        output.append({
            'fonte':source, 'tema_criminal_normalizado':theme,
            'relacoes_candidato_processo':group['links'],
            'processos_numerados_unicos':len(group['numbers']),
            'candidatos_distintos':len(group['candidates']),
            'documentos_distintos':len(group['documents']),
        })
    output.sort(key=lambda row:(row['fonte'],-row['relacoes_candidato_processo'],row['tema_criminal_normalizado']))
    with output_file.open('w',encoding='utf-8-sig',newline='') as target:
        writer=csv.DictWriter(target,fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)
    for row in output:
        if row['fonte']=='revisado_mini':
            print(row['tema_criminal_normalizado'],row['relacoes_candidato_processo'],row['processos_numerados_unicos'],row['candidatos_distintos'],sep=' | ')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=DATA/'processes_preliminary.csv')
    parser.add_argument('--output',type=Path,default=DATA/'crime_subjects_preliminary.csv')
    args=parser.parse_args(); build(args.input,args.output)
