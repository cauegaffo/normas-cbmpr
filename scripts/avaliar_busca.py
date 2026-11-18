"""
Avalia a qualidade da busca usando o gabarito dados/gabarito.csv.

Como usar (no PowerShell, dentro da pasta do projeto):
    python scripts\\avaliar_busca.py                          # mostra a avaliação
    python scripts\\avaliar_busca.py --sem-sinonimos          # idem, com os sinônimos desligados
    python scripts\\avaliar_busca.py --salvar antes.json      # guarda o resultado para comparar depois
    python scripts\\avaliar_busca.py --comparar antes.json    # tabela "antes x agora"

O gabarito tem as colunas busca;normas_esperadas (normas separadas por "|").
O nome da norma é igual ao da tela (ex.: "NPT 022"); para OTs, use o ano: "OT 001 (2017)".
Os 3 primeiros casos são os "de ajuste" (usados para escolher a regra de ordenação);
os demais são "novos" (servem para ver se a regra funciona fora dos casos de ajuste).

Para cada norma esperada, mostra duas posições:
- "lista de normas": posição da norma no resumo "Normas encontradas". Se a busca ainda não
  tiver o resumo (versão antiga), usa a ordem em que a norma aparece pela 1ª vez nos trechos.
- "1º trecho": posição do primeiro trecho daquela norma entre os 50 trechos mostrados.
"""

import argparse
import csv
import inspect
import json
import sys

import busca
from catalogo import PASTA_PROJETO

ARQUIVO_GABARITO = PASTA_PROJETO / "dados" / "gabarito.csv"
CASOS_DE_AJUSTE = 3   # os 3 primeiros casos do gabarito
LIMITE = 50           # trechos mostrados na tela


def ler_gabarito():
    with open(ARQUIVO_GABARITO, encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo, delimiter=";"))
    return [(l["busca"].strip(), [n.strip() for n in l["normas_esperadas"].split("|") if n.strip()])
            for l in linhas if l["busca"].strip()]


def eh_a_norma(esperada, nome, versao):
    """'NPT 022' casa com NPT 022 de qualquer versão; 'OT 001 (2017)' só com a de 2017."""
    return esperada in (nome, f"{nome} ({versao})")


def avaliar_caso(conexao, texto, esperadas, usar_sinonimos):
    parametros = {"limite": LIMITE}
    if "usar_sinonimos" in inspect.signature(busca.buscar).parameters:
        parametros["usar_sinonimos"] = usar_sinonimos
    resultado = busca.buscar(conexao, texto, **parametros)

    if isinstance(resultado, dict):   # versão nova: tem o resumo por norma
        trechos = resultado["trechos"]
        normas = [(n["norma"], n["versao"]) for n in resultado["normas"]]
        medida = "resumo"
    else:                             # versão antiga: só a lista de trechos
        trechos = resultado
        normas = []
        for t in trechos:
            if (t["norma"], t["versao"]) not in normas:
                normas.append((t["norma"], t["versao"]))
        medida = "1ª aparição"

    posicoes = {}
    for esperada in esperadas:
        na_lista = next((i for i, (n, v) in enumerate(normas, 1) if eh_a_norma(esperada, n, v)), None)
        trecho = next((i for i, t in enumerate(trechos, 1)
                       if eh_a_norma(esperada, t["norma"], t["versao"])), None)
        posicoes[esperada] = {"lista": na_lista, "trecho": trecho}
    primeiras = [f"{n} ({v})" if v else n for n, v in normas[:3]]
    return {"posicoes": posicoes, "medida": medida, "primeiras": primeiras}


def texto_posicao(p):
    return "—" if p is None else f"{p}º"


def resumo_do_grupo(casos):
    """Conta, para as normas esperadas do grupo: em 1º, no top 3, não encontradas, e média do 1º trecho."""
    lista = [p["lista"] for c in casos for p in c["posicoes"].values()]
    trechos = [p["trecho"] for c in casos for p in c["posicoes"].values()]
    achados = [t for t in trechos if t is not None]
    media = sum(achados) / len(achados) if achados else None
    return {
        "normas": len(lista),
        "lista_1o": sum(1 for p in lista if p == 1),
        "lista_top3": sum(1 for p in lista if p is not None and p <= 3),
        "lista_ausentes": sum(1 for p in lista if p is None),
        "trecho_top3": sum(1 for p in trechos if p is not None and p <= 3),
        "trecho_ausentes": sum(1 for p in trechos if p is None),
        "trecho_media": media,
    }


def imprimir_resumo(nome, r):
    media = "—" if r["trecho_media"] is None else f"{r['trecho_media']:.1f}"
    print(f"  {nome}: {r['normas']} normas esperadas | lista de normas: {r['lista_1o']} em 1º, "
          f"{r['lista_top3']} no top 3, {r['lista_ausentes']} ausentes | 1º trecho: "
          f"{r['trecho_top3']} no top 3, {r['trecho_ausentes']} fora dos {LIMITE}, média {media}")


def avaliar(usar_sinonimos):
    conexao = busca.conectar()
    casos = []
    for numero, (texto, esperadas) in enumerate(ler_gabarito(), start=1):
        caso = avaliar_caso(conexao, texto, esperadas, usar_sinonimos)
        caso.update(numero=numero, busca=texto, grupo="ajuste" if numero <= CASOS_DE_AJUSTE else "novo")
        casos.append(caso)
    return casos


def mostrar(casos):
    medida = casos[0]["medida"] if casos else ""
    print(f"Posição na lista de normas medida por: {medida}\n")
    for c in casos:
        print(f"{c['numero']:>2}. [{c['grupo']}] {c['busca']}")
        for esperada, p in c["posicoes"].items():
            print(f"      {esperada:<16} lista de normas: {texto_posicao(p['lista']):>4} | "
                  f"1º trecho: {texto_posicao(p['trecho']):>4}")
        print(f"      (3 primeiras normas: {', '.join(c['primeiras'])})")
    print("\nResumo:")
    imprimir_resumo("Casos de ajuste", resumo_do_grupo([c for c in casos if c["grupo"] == "ajuste"]))
    imprimir_resumo("Casos novos    ", resumo_do_grupo([c for c in casos if c["grupo"] == "novo"]))


def comparar(antes, agora):
    print("Comparação antes x agora")
    print(f"  Lista de normas: ANTES = {antes[0]['medida']}; AGORA = {agora[0]['medida']} "
          "(medidas diferentes).")
    print(f"  1º trecho: posição entre os {LIMITE} trechos (mesma medida nos dois).\n")
    print(f"{'#':>2} {'grupo':<6} {'busca':<28} {'norma':<16} {'lista antes':>11} {'lista agora':>11} "
          f"{'trecho antes':>12} {'trecho agora':>12}")
    por_busca = {c["busca"]: c for c in antes}
    for c in agora:
        anterior = por_busca.get(c["busca"], {"posicoes": {}})
        for esperada, p in c["posicoes"].items():
            a = anterior["posicoes"].get(esperada, {"lista": None, "trecho": None})
            print(f"{c['numero']:>2} {c['grupo']:<6} {c['busca'][:28]:<28} {esperada:<16} "
                  f"{texto_posicao(a['lista']):>11} {texto_posicao(p['lista']):>11} "
                  f"{texto_posicao(a['trecho']):>12} {texto_posicao(p['trecho']):>12}")
    for grupo, nome in (("ajuste", "Casos de ajuste"), ("novo", "Casos novos")):
        print(f"\n{nome}:")
        imprimir_resumo("ANTES", resumo_do_grupo([c for c in antes if c["grupo"] == grupo]))
        imprimir_resumo("AGORA", resumo_do_grupo([c for c in agora if c["grupo"] == grupo]))


def main():
    parser = argparse.ArgumentParser(description="Avalia a busca com o gabarito.")
    parser.add_argument("--sem-sinonimos", action="store_true", help="desliga os sinônimos")
    parser.add_argument("--salvar", metavar="ARQUIVO", help="grava o resultado em JSON")
    parser.add_argument("--comparar", metavar="ARQUIVO", help="compara com um resultado salvo")
    args = parser.parse_args()

    try:
        casos = avaliar(usar_sinonimos=not args.sem_sinonimos)
    except FileNotFoundError as erro:
        sys.exit(f"ERRO: {erro}")

    if args.comparar:
        with open(args.comparar, encoding="utf-8") as arquivo:
            comparar(json.load(arquivo), casos)
    else:
        mostrar(casos)
    if args.salvar:
        with open(args.salvar, "w", encoding="utf-8") as arquivo:
            json.dump(casos, arquivo, ensure_ascii=False, indent=1)
        print(f"\nResultado salvo em {args.salvar}")


if __name__ == "__main__":
    main()
