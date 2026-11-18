"""
Busca nas normas, usando o arquivo dados/busca.sqlite (criado pelo indexar.py).

É usado pelo aplicativo (app.py) e também pode ser rodado no terminal:
    python scripts\\busca.py hidrante
    python scripts\\busca.py "saída de emergência" --limite 10
    python scripts\\busca.py "iluminação" --tipo npt --todas    # inclui revogadas e futuras
    python scripts\\busca.py hidrante --sem-sinonimos
    python scripts\\busca.py hidrante --norma npt-022_2015-03   # só os trechos dessa versão

Como a busca funciona:
- ignora acentos e maiúsculas ("iluminacao" acha "Iluminação");
- aceita o começo da palavra ("hidrant" acha "hidrantes");
- todas as palavras precisam aparecer no trecho (palavras como "de", "a", "para" são ignoradas);
- texto entre aspas é procurado como frase exata ("saída de emergência" não acha "saídas");
- usa os sinônimos de dados/sinonimos.csv, com peso menor que o texto digitado;
- os resultados vêm do mais relevante para o menos relevante (ver "PONTUAÇÃO" abaixo).
"""

import argparse
import csv
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_BUSCA = PASTA_PROJETO / "dados" / "busca.sqlite"
ARQUIVO_SINONIMOS = PASTA_PROJETO / "dados" / "sinonimos.csv"

NOMES_TIPOS = {
    "lei": "Lei", "decreto": "Decreto", "resolucao": "Resolução", "portaria": "Portaria",
    "cscip": "CSCIP", "npa": "NPA", "npt": "NPT", "ot": "OT",
}

# Palavras muito comuns que não ajudam a busca.
PALAVRAS_IGNORADAS = {
    "a", "o", "as", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "um", "uma", "para", "por", "com", "ao", "aos", "à", "às", "que", "se",
}

CANDIDATOS = 2000        # máximo de trechos lidos do SQLite (o resumo por norma conta todos eles)
TAMANHO_SIGLA = 3        # siglas de até 3 letras (OT, SHP, SPK) exigem a palavra inteira
RE_PONTILHADO = re.compile(r"\.{5,}|…{2,}")

# ---------------------------------------------------------------------------
# PONTUAÇÃO — tudo é calculado em "pontos": POSITIVO e MAIOR = MELHOR.
#
# O SQLite (FTS5) devolve bm25(), que é NEGATIVO e MENOR = MELHOR.
# Por isso, logo ao ler, fazemos  pontos = -bm25  e TODAS as multiplicações abaixo
# são feitas sobre "pontos". Fator maior que 1 SOBE o trecho; menor que 1 DESCE.
# ---------------------------------------------------------------------------
PESO_SINONIMO = 0.5      # trecho achado SÓ por sinônimo
PESO_TITULO = 2.0        # o título da norma tem todas as palavras digitadas
PESO_TRECHO_CURTO = 0.5  # trecho com menos de 100 caracteres (ex.: só um título)
PESO_PONTILHADO = 0.5    # trecho com pontilhado (sumário ou checklist)
# Resumo por norma: as normas são ordenadas pela SOMA dos pontos dos seus trechos.
# Essa soma NÃO altera a ordem dos trechos (decisão de 18/11/2026, "opção A"): um fator
# "x (1 + soma da norma / maior soma)" nos trechos foi testado e piorou os casos novos
# do gabarito, porque normas com muitos trechos (CSCIP, NPT 012) passavam à frente.

# A situação é calculada na hora, pelas datas (igual a catalogo.calcular_situacao).
SITUACAO_SQL = """
    CASE
        WHEN n.link_oficial = '' THEN 'pendente'
        WHEN n.vigencia_inicio != '' AND n.vigencia_inicio > :hoje THEN 'futura'
        WHEN n.vigencia_fim != '' AND n.vigencia_fim < :hoje THEN 'revogada'
        ELSE 'vigente'
    END
"""


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def sem_acentos(texto):
    """'Saída de Emergência' -> 'saida de emergencia'."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def palavras_de(texto):
    """Separa o texto em palavras (letras e números), em minúsculas."""
    return re.findall(r"\w+", texto.lower())


def eh_sigla(palavras):
    """Expressão de uma palavra só, com até 3 letras (ex.: OT, SHP, SPK, GLP)."""
    return len(palavras) == 1 and len(palavras[0]) <= TAMANHO_SIGLA


def termo_fts(palavras, prefixo=True):
    """Monta um termo da linguagem de busca do FTS5.
    Uma palavra: "hidrante"*; várias: a frase "sistema de hidrantes"* (palavras em sequência).
    O * no fim aceita o começo da última palavra. Frases exatas (entre aspas) vão sem *;
    siglas curtas de sinônimos também (quem decide é interpretar())."""
    termo = '"' + " ".join(palavras) + '"'
    return termo + "*" if prefixo else termo


# ---------------------------------------------------------------------------
# Sinônimos
# ---------------------------------------------------------------------------

def carregar_sinonimos(arquivo=ARQUIVO_SINONIMOS):
    """Lê dados/sinonimos.csv. Devolve uma lista de grupos; cada grupo é uma lista de
    expressões equivalentes (o termo e os equivalentes), como texto."""
    if not Path(arquivo).exists():
        return []
    grupos = []
    with open(arquivo, encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            expressoes = [linha.get("termo") or ""] + (linha.get("equivalentes") or "").split("|")
            expressoes = [e.strip() for e in expressoes if e and e.strip()]
            if len(expressoes) > 1:
                grupos.append(expressoes)
    return grupos


def _casa(digitada, da_expressao, sigla):
    """A palavra digitada casa com a palavra da expressão?
    - sigla curta: só se for igual ("otimizar" NÃO casa com "OT");
    - demais: se começar por ela ("hidrantes" casa com "hidrante")."""
    digitada, da_expressao = sem_acentos(digitada), sem_acentos(da_expressao)
    return digitada == da_expressao if sigla else digitada.startswith(da_expressao)


def reconhecer_sinonimos(palavras, grupos):
    """Procura expressões dos grupos de sinônimos nas palavras digitadas.

    - A expressão MAIS LONGA ganha ("sistema de hidrantes" antes de "hidrante").
    - Cada palavra digitada pertence a NO MÁXIMO um trecho reconhecido.
    - Se a expressão estiver em mais de um grupo, os grupos são unidos.

    Devolve uma lista de partes, na ordem do texto. Cada parte é:
      ("palavra", palavra)                         palavra sem sinônimo
      ("grupo", palavras_digitadas, sinonimos)     trecho reconhecido e seus sinônimos
    """
    # Todas as expressões, da mais longa para a mais curta (em número de palavras).
    expressoes = defaultdict(set)   # palavras da expressão (sem acentos) -> grupos onde aparece
    for indice, grupo in enumerate(grupos):
        for expressao in grupo:
            expressoes[tuple(sem_acentos(p) for p in palavras_de(expressao))].add(indice)
    ordenadas = sorted((e for e in expressoes if e), key=len, reverse=True)

    partes, i = [], 0
    while i < len(palavras):
        achou = None
        for expressao in ordenadas:
            pedaco = palavras[i:i + len(expressao)]
            sigla = eh_sigla(list(expressao))
            if len(pedaco) == len(expressao) and all(
                    _casa(d, e, sigla) for d, e in zip(pedaco, expressao)):
                achou = expressao
                break
        if not achou:
            partes.append(("palavra", palavras[i]))
            i += 1
            continue
        digitadas = palavras[i:i + len(achou)]
        # Sinônimos = todas as expressões dos grupos envolvidos, menos a que foi digitada.
        sinonimos = []
        for indice in sorted(expressoes[achou]):
            for expressao in grupos[indice]:
                chave = tuple(sem_acentos(p) for p in palavras_de(expressao))
                if chave != achou and expressao not in sinonimos:
                    sinonimos.append(expressao)
        partes.append(("grupo", digitadas, sinonimos))
        i += len(achou)
    return partes


# ---------------------------------------------------------------------------
# Interpretação do que foi digitado
# ---------------------------------------------------------------------------

def interpretar(texto, usar_sinonimos=True, grupos=None):
    """Transforma o que o usuário digitou em consultas do FTS5.

    Devolve None (nada para buscar) ou um dicionário com:
      consulta             só o texto digitado (busca "B");
      consulta_sinonimos   com os sinônimos (busca "A"), ou None se nenhum sinônimo foi usado;
      sinonimos_usados     {"hidrante": ["sistema de hidrantes", ...]};
      palavras             palavras digitadas importantes (para comparar com o título da norma).
    """
    # 1) Frases entre aspas: busca exata, sem sinônimos.
    frases = [palavras_de(f) for f in re.findall(r'"([^"]*)"', texto)]
    frases = [f for f in frases if f]
    resto = re.sub(r'"[^"]*"', " ", texto).replace('"', " ")  # aspas sem par são ignoradas

    # 2) Palavras soltas (fora das aspas), com ou sem sinônimos.
    soltas = palavras_de(resto)
    if usar_sinonimos:
        partes = reconhecer_sinonimos(soltas, grupos if grupos is not None else carregar_sinonimos())
    else:
        partes = [("palavra", p) for p in soltas]

    # Palavras como "de" e "para" são ignoradas, a não ser que só tenha digitado esse tipo de palavra.
    so_ignoradas = all(p[1] in PALAVRAS_IGNORADAS for p in partes if p[0] == "palavra") \
        and not any(p[0] == "grupo" for p in partes) and not frases

    termos_b, termos_a, usados, importantes = [], [], {}, []
    for frase in frases:
        termos_b.append(termo_fts(frase, prefixo=False))
        termos_a.append(termo_fts(frase, prefixo=False))
        importantes += [p for p in frase if p not in PALAVRAS_IGNORADAS]
    for parte in partes:
        if parte[0] == "palavra":
            palavra = parte[1]
            if palavra in PALAVRAS_IGNORADAS and not so_ignoradas:
                continue
            termos_b.append(termo_fts([palavra]))
            termos_a.append(termo_fts([palavra]))
            importantes.append(palavra)
        else:
            _, digitadas, sinonimos = parte
            uteis = [p for p in digitadas if p not in PALAVRAS_IGNORADAS] or digitadas
            digitado = "(" + " AND ".join(termo_fts([p]) for p in uteis) + ")"
            termos_b.append(digitado)
            # Sinônimos que são siglas curtas (SHP, SPK, OT) vão sem *, para "OT" não achar "otimizar".
            alternativas = [termo_fts(palavras_de(s), prefixo=not eh_sigla(palavras_de(s)))
                            for s in sinonimos if palavras_de(s)]
            termos_a.append("(" + " OR ".join([digitado] + alternativas) + ")")
            usados[" ".join(digitadas)] = sinonimos
            importantes += uteis

    if not termos_b:
        return None
    consulta = " AND ".join(termos_b)
    consulta_sinonimos = " AND ".join(termos_a) if usados else None
    return {"consulta": consulta, "consulta_sinonimos": consulta_sinonimos,
            "sinonimos_usados": usados, "palavras": [sem_acentos(p) for p in importantes]}


def montar_consulta(texto):
    """Compatibilidade: só a consulta do texto digitado, sem sinônimos."""
    interpretado = interpretar(texto, usar_sinonimos=False)
    return interpretado["consulta"] if interpretado else None


# ---------------------------------------------------------------------------
# Pontuação
# ---------------------------------------------------------------------------

def pontos_base(bm25_digitado, bm25_com_sinonimos):
    """Pontos iniciais de um trecho (POSITIVO, MAIOR = MELHOR).

    - O trecho contém o texto digitado (achado na busca B): usa a pontuação da busca B,
      sem penalidade.
    - O trecho foi achado SÓ por sinônimo (busca A): pontuação da busca A x PESO_SINONIMO.
      O 0,5 é uma APROXIMAÇÃO: pontuações de buscas diferentes não se comparam exatamente.
    """
    if bm25_digitado is not None:
        return -bm25_digitado
    return -bm25_com_sinonimos * PESO_SINONIMO


def pontuar_trecho(r, palavras):
    """Aplica as regras de texto sobre r["pontos"] (já positivos). Devolve os pontos ajustados."""
    pontos = r["pontos"]
    titulo = sem_acentos(r["titulo"])
    if palavras and all(re.search(rf"\b{re.escape(p)}", titulo) for p in palavras):
        pontos *= PESO_TITULO
    if len(r["texto"]) < 100:
        pontos *= PESO_TRECHO_CURTO
    if RE_PONTILHADO.search(r["texto"]):
        pontos *= PESO_PONTILHADO
    return pontos


def resumir_normas(resultados):
    """Agrupa os trechos por versão de norma: quantidade e soma dos pontos, do maior para o menor."""
    normas = {}
    for r in resultados:
        n = normas.setdefault(r["id"], {
            "id": r["id"], "norma": r["norma"], "versao": r["versao"],
            "situacao": r["situacao"], "quantidade": 0, "pontos": 0.0,
        })
        n["quantidade"] += 1
        n["pontos"] += r["pontos_trecho"]
    return sorted(normas.values(), key=lambda n: n["pontos"], reverse=True)


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------

def nome_norma(linha):
    """Nome curto da norma, ex.: 'NPT 015 Parte 1', 'Lei 19.449', 'CSCIP'."""
    nome = NOMES_TIPOS.get(linha["tipo"], linha["tipo"].upper())
    if linha["numero"]:
        nome += f" {linha['numero']}"
    if linha["parte"]:
        nome += f" Parte {linha['parte']}"
    return nome


def conectar():
    if not ARQUIVO_BUSCA.exists():
        raise FileNotFoundError(
            "O arquivo dados/busca.sqlite não existe. Rode antes: python scripts\\indexar.py")
    conexao = sqlite3.connect(ARQUIVO_BUSCA)
    conexao.row_factory = sqlite3.Row
    return conexao


def ler_info(conexao):
    """Informações gerais gravadas pelo indexar.py (data da indexação, última verificação...)."""
    return {chave: valor for chave, valor in conexao.execute("SELECT chave, valor FROM info")}


def _filtros(tipos, incluir_todas, parametros):
    filtros = ["trechos MATCH :consulta"]
    for i, tipo in enumerate(tipos or []):
        parametros[f"tipo{i}"] = tipo
    if tipos:
        filtros.append(f"n.tipo IN ({', '.join(f':tipo{i}' for i in range(len(tipos)))})")
    if not incluir_todas:
        filtros.append(f"({SITUACAO_SQL}) = 'vigente'")
    return " AND ".join(filtros)


def buscar(conexao, texto, tipos=None, incluir_todas=False, limite=50,
           marca_inicio="[", marca_fim="]", data_referencia=None,
           usar_sinonimos=True, versao_id=None):
    """Busca e devolve um dicionário:
      trechos          lista de trechos (dicionários), do mais relevante para o menos, até o limite;
      normas           resumo "Normas encontradas" (id, norma, versao, situacao, quantidade, pontos);
      sinonimos_usados {"hidrante": [...]} ;
      total_trechos    quantos trechos foram encontrados (antes do filtro por norma);
      limitado         True se bateu no máximo de CANDIDATOS (as contagens ficam parciais).

    tipos:          lista de tipos (ex.: ["npt", "npa"]); vazio = todos.
    incluir_todas:  False = só normas vigentes; True = inclui revogadas e futuras.
    versao_id:      mostra só os trechos dessa versão (o resumo continua com todas as normas).
    """
    vazio = {"trechos": [], "normas": [], "sinonimos_usados": {}, "total_trechos": 0, "limitado": False}
    interpretado = interpretar(texto, usar_sinonimos)
    if not interpretado:
        return vazio

    parametros = {"hoje": data_referencia or date.today().isoformat(),
                  "limite": CANDIDATOS, "ini": marca_inicio, "fim": marca_fim}
    where = _filtros(tipos, incluir_todas, parametros)

    # Busca A: candidatos e trecho destacado (com sinônimos, se houver).
    consulta_a = interpretado["consulta_sinonimos"] or interpretado["consulta"]
    sql = f"""
        SELECT n.*, {SITUACAO_SQL} AS situacao, t.rowid AS trecho_id,
               t.item, t.pagina, t.texto,
               snippet(trechos, 0, :ini, :fim, ' … ', 40) AS trecho,
               bm25(trechos) AS bm25
        FROM trechos AS t JOIN normas AS n ON n.id = t.versao_id
        WHERE {where}
        ORDER BY bm25
        LIMIT :limite
    """
    linhas = conexao.execute(sql, dict(parametros, consulta=consulta_a)).fetchall()

    # Busca B: só o texto digitado (para saber quais trechos o contêm e com que pontuação).
    if interpretado["consulta_sinonimos"]:
        sql_b = f"""
            SELECT t.rowid AS trecho_id, bm25(trechos) AS bm25
            FROM trechos AS t JOIN normas AS n ON n.id = t.versao_id
            WHERE {where}
        """
        bm25_digitado = {l["trecho_id"]: l["bm25"]
                         for l in conexao.execute(sql_b, dict(parametros, consulta=interpretado["consulta"]))}
    else:
        bm25_digitado = {l["trecho_id"]: l["bm25"] for l in linhas}

    resultados = []
    for linha in linhas:
        r = dict(linha)
        r["norma"] = nome_norma(r)
        r["link"] = r["link_oficial"]
        if r["pagina"] and r["link"]:
            r["link"] += f"#page={r['pagina']}"
        r["so_sinonimo"] = r["trecho_id"] not in bm25_digitado
        r["pontos"] = pontos_base(bm25_digitado.get(r["trecho_id"]), r["bm25"])
        r["pontos_trecho"] = pontuar_trecho(r, interpretado["palavras"])
        resultados.append(r)

    normas = resumir_normas(resultados)
    for r in resultados:
        r["relevancia"] = r["pontos_trecho"]   # a soma por norma só ordena o resumo
    resultados.sort(key=lambda r: r["relevancia"], reverse=True)

    if versao_id:
        resultados = [r for r in resultados if r["id"] == versao_id]
    return {
        "trechos": resultados[:limite],
        "normas": normas,
        "sinonimos_usados": interpretado["sinonimos_usados"],
        "total_trechos": len(linhas),
        "limitado": len(linhas) >= CANDIDATOS,
    }


def main():
    parser = argparse.ArgumentParser(description="Busca nas normas (dados/busca.sqlite).")
    parser.add_argument("texto", help='o que procurar, ex.: "saída de emergência"')
    parser.add_argument("--limite", type=int, default=5, help="quantos trechos mostrar (padrão: 5)")
    parser.add_argument("--tipo", nargs="+", choices=list(NOMES_TIPOS), help="só estes tipos")
    parser.add_argument("--todas", action="store_true", help="inclui revogadas e futuras")
    parser.add_argument("--sem-sinonimos", action="store_true", help="não usa o sinonimos.csv")
    parser.add_argument("--norma", metavar="ID", help="só os trechos desta versão (ex.: npt-022_2015-03)")
    args = parser.parse_args()

    try:
        conexao = conectar()
    except FileNotFoundError as erro:
        sys.exit(f"ERRO: {erro}")

    res = buscar(conexao, args.texto, args.tipo, args.todas, args.limite,
                 usar_sinonimos=not args.sem_sinonimos, versao_id=args.norma)
    print(f'Busca: "{args.texto}"  ->  {res["total_trechos"]} trecho(s) encontrados')
    for digitado, sinonimos in res["sinonimos_usados"].items():
        print(f"Sinônimos usados: {digitado} -> {', '.join(sinonimos)}")
    print("\nNormas encontradas:")
    for n in res["normas"][:8]:
        versao = f" ({n['versao']})" if n["versao"] else ""
        print(f"  {n['norma']}{versao}: {n['quantidade']} trecho(s)  [{n['id']}]")
    print()
    for numero, r in enumerate(res["trechos"], start=1):
        pagina = f", pág. {r['pagina']}" if r["pagina"] else ""
        versao = f" ({r['versao']})" if r["versao"] else ""
        sinonimo = " (por sinônimo)" if r["so_sinonimo"] else ""
        print(f"{numero}. {r['norma']}{versao} [{r['situacao']}] — item {r['item']}{pagina}{sinonimo}")
        print(f"   {r['titulo']}")
        print(f"   {' '.join(r['trecho'].split())}")
        print()


if __name__ == "__main__":
    main()
