"""
Avalia as perguntas à IA usando o gabarito dados/gabarito_perguntas.csv.

Como usar (no PowerShell, dentro da pasta do projeto):
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_ia.py --sem-ia      # só a busca dos trechos (sem chave, sem cota)
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_ia.py               # com a IA (gasta cota: 1 chamada por pergunta)
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_ia.py --modelo gemini-3.8-flash --salvar respostas.json
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_ia.py --comparar a.json b.json   # compara duas execuções salvas

Colunas do gabarito: pergunta;normas_esperadas;resposta_esperada;tipo;incluir_revogadas
- normas_esperadas: separadas por "|" (ex.: NPT 022), como na tela;
- resposta_esperada: um valor com unidade (ex.: 15 m), ou vazio;
- tipo: normal, sem_resposta, revogada ou futura;
- incluir_revogadas: sim/não.

O que é conferido na resposta da IA (comparação simples de texto, sem acentos):
- cita alguma norma esperada;
- contém a resposta esperada (o número com a unidade);
- sem_resposta: diz "não encontrei"; revogada: fala em "revogad"; futura: "não vigente"/"ainda não".
"""

import argparse
import csv
import json
import re
import sys
import time

import busca
import ia
import perguntar
from catalogo import PASTA_PROJETO

ARQUIVO_GABARITO = PASTA_PROJETO / "dados" / "gabarito_perguntas.csv"


def ler_gabarito():
    with open(ARQUIVO_GABARITO, encoding="utf-8-sig", newline="") as arquivo:
        linhas = [l for l in csv.DictReader(arquivo, delimiter=";") if (l.get("pergunta") or "").strip()]
    for l in linhas:
        l["normas"] = [n.strip() for n in (l.get("normas_esperadas") or "").split("|") if n.strip()]
        l["incluir"] = busca.sem_acentos(l.get("incluir_revogadas") or "") == "sim"
        l["tipo"] = (l.get("tipo") or "normal").strip()
        l["resposta_esperada"] = (l.get("resposta_esperada") or "").strip()
    return linhas


def eh_a_norma(esperada, nome, versao):
    """'NPT 028' casa com 'NPT 028' e com todas as partes ('NPT 028 Parte 1'...);
    'OT 001 (2017)' só com a versão de 2017."""
    sem_parte = nome.split(" Parte ")[0]
    return esperada in (nome, sem_parte, f"{nome} ({versao})", f"{sem_parte} ({versao})")


def cita_norma(resposta, esperada):
    """'NPT 018' casa com 'NPT 018' ou 'NPT 18' na resposta (sem diferenciar maiúsculas)."""
    partes = esperada.split(" (")[0].split()
    if len(partes) >= 2 and partes[-1].isdigit():
        numero = str(int(partes[-1]))
        padrao = rf"{re.escape(' '.join(partes[:-1]))}\s*0*{numero}\b"
    else:
        padrao = re.escape(esperada)
    return re.search(padrao, resposta, re.IGNORECASE) is not None


def contem_valor(resposta, esperado):
    """'15 m' casa com '15 m', '15 metros', '15,0 m'; '5 m³' casa com '5 m³' e '5 m3'."""
    achado = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*(\S*)", esperado)
    if not achado:
        return None
    numero, unidade = achado.group(1), achado.group(2).replace("³", "3").replace("²", "2")
    texto = resposta.replace("³", "3").replace("²", "2")
    unidade_inicial = re.escape(unidade[:1]) if unidade else ""
    return re.search(rf"(?<![\d.,]){re.escape(numero)}(?:,0+)?\s*{unidade_inicial}", texto) is not None


def conferir(caso, resposta):
    """Devolve {criterio: True/False} para os critérios que se aplicam ao caso."""
    texto = busca.sem_acentos(resposta)
    criterios = {}
    if caso["normas"]:
        criterios["cita norma"] = any(cita_norma(resposta, n) for n in caso["normas"])
    if caso["resposta_esperada"]:
        criterios["valor"] = bool(contem_valor(resposta, caso["resposta_esperada"]))
    if caso["tipo"] == "sem_resposta":
        criterios["não encontrei"] = "nao encontrei" in texto
    if caso["tipo"] == "revogada":
        criterios["avisa revogada"] = "revogad" in texto
    if caso["tipo"] == "futura":
        criterios["avisa não vigente"] = "nao vigente" in texto or "ainda nao" in texto
    return criterios


def posicoes_nos_trechos(caso, trechos):
    """Para cada norma esperada: posição do 1º trecho dela e quantos trechos dela foram enviados."""
    resultado = {}
    for esperada in caso["normas"]:
        posicoes = [i for i, t in enumerate(trechos, 1) if eh_a_norma(esperada, t["norma"], t["versao"])]
        resultado[esperada] = {"primeiro": posicoes[0] if posicoes else None, "quantidade": len(posicoes)}
    return resultado


def avaliar(sem_ia, modelo, pausa):
    conexao = busca.conectar()
    casos = ler_gabarito()
    saida = []
    if not sem_ia:
        estado = ia.status()
        nome_modelo = modelo or estado["modelo"]
        print(f"IA: {estado['nome']} · modelo {nome_modelo} · chave configurada: "
              f"{'sim' if estado['tem_chave'] else 'NÃO'}\n")
    for numero, caso in enumerate(casos, start=1):
        preparado = perguntar.preparar(conexao, caso["pergunta"], caso["incluir"])
        posicoes = posicoes_nos_trechos(caso, preparado["trechos"])
        item = {"numero": numero, "pergunta": caso["pergunta"], "tipo": caso["tipo"],
                "termos": preparado["termos"], "posicoes": posicoes,
                "trechos": [perguntar.rotulo_trecho(i, t) for i, t in enumerate(preparado["trechos"], 1)],
                "caracteres_enviados": len(preparado["pergunta_pronta"])}
        print(f"{numero}. [{caso['tipo']}] {caso['pergunta']}")
        print(f"   termos: {preparado['termos']}  ·  {len(preparado['trechos'])} trechos  ·  "
              f"{item['caracteres_enviados']} caracteres")
        for esperada, p in posicoes.items():
            primeiro = f"{p['primeiro']}º" if p["primeiro"] else "AUSENTE"
            print(f"   {esperada}: 1º trecho em {primeiro} · {p['quantidade']} de {len(preparado['trechos'])} trechos")
        if preparado["avisos"]:
            print(f"   avisos da tela: {' | '.join(preparado['avisos'])}")

        if not sem_ia:
            if numero > 1:
                time.sleep(pausa)
            inicio = time.time()
            try:
                # Com --modelo, mede só aquele modelo (sem reserva). Sem --modelo, igual à tela.
                resultado = perguntar.responder(preparado, modelo, usar_reserva=modelo is None)
                resposta = resultado["texto"]
                item["modelo_usado"] = resultado["modelo"]
            except ia.ErroLimite as erro:
                print(f"\n   PAREI: {erro}")
                print("   (Pode ser o limite de requisições ou de tokens por minuto. Não mudei nada.)")
                item["erro"] = str(erro)
                saida.append(item)
                break
            except ia.ErroIA as erro:
                print(f"   ERRO: {erro}")
                item["erro"] = str(erro)
                saida.append(item)
                continue
            item["segundos"] = round(time.time() - inicio, 1)
            item["resposta"] = resposta
            item["criterios"] = conferir(caso, resposta)
            marcas = ", ".join(f"{c}: {'ok' if v else 'NÃO'}" for c, v in item["criterios"].items())
            reserva = " (RESERVA)" if resultado["usou_reserva"] else ""
            print(f"   resposta de {resultado['modelo']}{reserva} em {item['segundos']} s · {marcas}")
            print("   " + resposta.replace("\n", "\n   ")[:1500])
        print()
        saida.append(item)

    if not sem_ia:
        respondidas = [s for s in saida if "criterios" in s]
        total = sum(len(s["criterios"]) for s in respondidas)
        ok = sum(sum(s["criterios"].values()) for s in respondidas)
        print(f"Resumo: {len(respondidas)} de {len(casos)} perguntas respondidas · critérios ok: {ok} de {total}")
    return saida


def comparar(arquivo_a, arquivo_b):
    with open(arquivo_a, encoding="utf-8") as f:
        a = json.load(f)
    with open(arquivo_b, encoding="utf-8") as f:
        b = json.load(f)
    nome_a, nome_b = a["modelo"], b["modelo"]
    por_numero = {c["numero"]: c for c in b["casos"]}
    print(f"Comparação: A = {nome_a}  x  B = {nome_b}\n")
    for caso_a in a["casos"]:
        caso_b = por_numero.get(caso_a["numero"], {})
        print(f"{caso_a['numero']}. [{caso_a['tipo']}] {caso_a['pergunta']}")
        for nome, caso in ((f"A {nome_a}", caso_a), (f"B {nome_b}", caso_b)):
            if "criterios" in caso:
                marcas = ", ".join(f"{c}: {'ok' if v else 'NÃO'}" for c, v in caso["criterios"].items())
                print(f"   {nome}: {caso['segundos']} s · {marcas}")
            else:
                print(f"   {nome}: {caso.get('erro', 'sem resposta')}")
        print()
    for nome, dados in (("A", a), ("B", b)):
        respondidas = [c for c in dados["casos"] if "criterios" in c]
        total = sum(len(c["criterios"]) for c in respondidas)
        ok = sum(sum(c["criterios"].values()) for c in respondidas)
        media = sum(c["segundos"] for c in respondidas) / len(respondidas) if respondidas else 0
        print(f"{nome} {dados['modelo']}: {len(respondidas)} respondidas · critérios ok {ok} de {total} · "
              f"tempo médio {media:.1f} s")


def main():
    parser = argparse.ArgumentParser(description="Avalia as perguntas à IA com o gabarito.")
    parser.add_argument("--sem-ia", action="store_true", help="só a busca dos trechos (sem chave, sem cota)")
    parser.add_argument("--modelo", help="modelo só nesta execução (ex.: gemini-3.8-flash)")
    parser.add_argument("--pausa", type=float, default=15, help="segundos entre as chamadas (padrão: 15)")
    parser.add_argument("--salvar", metavar="ARQUIVO", help="grava as respostas em JSON")
    parser.add_argument("--comparar", nargs=2, metavar=("A", "B"), help="compara duas execuções salvas")
    args = parser.parse_args()

    if args.comparar:
        comparar(*args.comparar)
        return
    try:
        casos = avaliar(args.sem_ia, args.modelo, args.pausa)
    except FileNotFoundError as erro:
        sys.exit(f"ERRO: {erro}")
    if args.salvar:
        modelo = "sem IA" if args.sem_ia else (args.modelo or ia.status()["modelo"])
        with open(args.salvar, "w", encoding="utf-8") as arquivo:
            json.dump({"modelo": modelo, "casos": casos}, arquivo, ensure_ascii=False, indent=1)
        print(f"\nRespostas salvas em {args.salvar}")


if __name__ == "__main__":
    main()
