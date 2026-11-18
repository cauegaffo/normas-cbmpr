"""
Busca nas normas, usando o arquivo dados/busca.sqlite (criado pelo indexar.py).

É usado pelo aplicativo (app.py) e também pode ser rodado no terminal:
    python scripts\\busca.py hidrante
    python scripts\\busca.py "saída de emergência" --limite 10
    python scripts\\busca.py "iluminação" --tipo npt --todas    # inclui revogadas e futuras

Como a busca funciona:
- ignora acentos e maiúsculas ("iluminacao" acha "Iluminação");
- aceita o começo da palavra ("hidrant" acha "hidrantes");
- todas as palavras precisam aparecer no trecho (palavras como "de", "a", "para" são ignoradas);
- os resultados vêm do mais relevante para o menos relevante (ver a função reordenar).
"""

import argparse
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_BUSCA = PASTA_PROJETO / "dados" / "busca.sqlite"

NOMES_TIPOS = {
    "lei": "Lei", "decreto": "Decreto", "resolucao": "Resolução", "portaria": "Portaria",
    "cscip": "CSCIP", "npa": "NPA", "npt": "NPT", "ot": "OT",
}

# Palavras muito comuns que não ajudam a busca.
PALAVRAS_IGNORADAS = {
    "a", "o", "as", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "um", "uma", "para", "por", "com", "ao", "aos", "à", "às", "que", "se",
}

# A situação é calculada na hora, pelas datas (igual a catalogo.calcular_situacao).
SITUACAO_SQL = """
    CASE
        WHEN n.link_oficial = '' THEN 'pendente'
        WHEN n.vigencia_inicio != '' AND n.vigencia_inicio > :hoje THEN 'futura'
        WHEN n.vigencia_fim != '' AND n.vigencia_fim < :hoje THEN 'revogada'
        ELSE 'vigente'
    END
"""


def montar_consulta(texto):
    """Transforma o que o usuário digitou na linguagem de busca do SQLite.
    Ex.: 'saída de emergência' -> '"saída"* "emergência"*'.
    Devolve None se não sobrar nenhuma palavra."""
    palavras = re.findall(r"\w+", texto.lower())
    uteis = [p for p in palavras if p not in PALAVRAS_IGNORADAS] or palavras
    if not uteis:
        return None
    return " ".join(f'"{p}"*' for p in uteis)


def sem_acentos(texto):
    """'Saída de Emergência' -> 'saida de emergencia'."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


RE_PONTILHADO = re.compile(r"\.{5,}|…{2,}")
CANDIDATOS = 300  # quantos resultados pegar do SQLite antes de reordenar


def reordenar(resultados, texto):
    """Ajusta a ordem dada pelo SQLite (BM25), que favorece demais trechos curtos.
    Regras:
    - título da norma contém todas as palavras buscadas: pontuação x 2
      (ex.: "hidrante" favorece a NPT 022 - Sistemas de hidrantes);
    - trecho muito curto (só um título, menos de 100 letras): x 0,5;
    - trecho com pontilhado (sumário ou checklist): x 0,5.
    """
    palavras = [sem_acentos(p) for p in re.findall(r"\w+", texto)
                if p.lower() not in PALAVRAS_IGNORADAS]
    for r in resultados:
        pontos = -r["pontuacao"]  # no SQLite, quanto mais negativo, melhor
        titulo = sem_acentos(r["titulo"])
        if palavras and all(re.search(rf"\b{re.escape(p)}", titulo) for p in palavras):
            pontos *= 2
        if len(r["texto"]) < 100:
            pontos *= 0.5
        if RE_PONTILHADO.search(r["texto"]):
            pontos *= 0.5
        r["relevancia"] = pontos
    return sorted(resultados, key=lambda r: r["relevancia"], reverse=True)


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


def buscar(conexao, texto, tipos=None, incluir_todas=False, limite=50,
           marca_inicio="[", marca_fim="]", data_referencia=None):
    """Devolve uma lista de resultados (dicionários), do mais relevante para o menos relevante.

    tipos:          lista de tipos (ex.: ["npt", "npa"]); vazio = todos.
    incluir_todas:  False = só normas vigentes; True = inclui revogadas e futuras.
    marca_inicio/marca_fim: o que vai em volta das palavras encontradas no trecho.
    """
    consulta = montar_consulta(texto)
    if not consulta:
        return []

    filtros = ["trechos MATCH :consulta"]
    parametros = {
        "consulta": consulta,
        "hoje": data_referencia or date.today().isoformat(),
        "limite": max(limite, CANDIDATOS),
        "ini": marca_inicio,
        "fim": marca_fim,
    }
    if tipos:
        marcadores = []
        for i, tipo in enumerate(tipos):
            parametros[f"tipo{i}"] = tipo
            marcadores.append(f":tipo{i}")
        filtros.append(f"n.tipo IN ({', '.join(marcadores)})")
    if not incluir_todas:
        filtros.append(f"({SITUACAO_SQL}) = 'vigente'")

    sql = f"""
        SELECT n.*, {SITUACAO_SQL} AS situacao,
               t.item, t.pagina, t.texto,
               snippet(trechos, 0, :ini, :fim, ' … ', 40) AS trecho,
               bm25(trechos) AS pontuacao
        FROM trechos AS t
        JOIN normas AS n ON n.id = t.versao_id
        WHERE {' AND '.join(filtros)}
        ORDER BY pontuacao
        LIMIT :limite
    """
    resultados = []
    for linha in conexao.execute(sql, parametros):
        resultado = dict(linha)
        resultado["norma"] = nome_norma(resultado)
        resultado["link"] = resultado["link_oficial"]
        if resultado["pagina"] and resultado["link"]:
            resultado["link"] += f"#page={resultado['pagina']}"
        resultados.append(resultado)
    return reordenar(resultados, texto)[:limite]


def main():
    parser = argparse.ArgumentParser(description="Busca nas normas (dados/busca.sqlite).")
    parser.add_argument("texto", help='o que procurar, ex.: "saída de emergência"')
    parser.add_argument("--limite", type=int, default=5, help="quantos resultados mostrar (padrão: 5)")
    parser.add_argument("--tipo", nargs="+", choices=list(NOMES_TIPOS), help="só estes tipos")
    parser.add_argument("--todas", action="store_true", help="inclui revogadas e futuras")
    args = parser.parse_args()

    try:
        conexao = conectar()
    except FileNotFoundError as erro:
        sys.exit(f"ERRO: {erro}")

    resultados = buscar(conexao, args.texto, args.tipo, args.todas, args.limite)
    print(f'Busca: "{args.texto}"  ->  {len(resultados)} resultado(s) mostrados\n')
    for numero, r in enumerate(resultados, start=1):
        pagina = f", pág. {r['pagina']}" if r["pagina"] else ""
        versao = f" ({r['versao']})" if r["versao"] else ""
        print(f"{numero}. {r['norma']}{versao} [{r['situacao']}] — item {r['item']}{pagina}")
        print(f"   {r['titulo']}")
        print(f"   {' '.join(r['trecho'].split())}")
        print()


if __name__ == "__main__":
    main()
