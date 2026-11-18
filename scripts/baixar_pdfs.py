"""
Protótipo, Passo 1 — Baixa os PDFs das normas e as páginas das leis e decretos.

Como usar (no PowerShell, dentro da pasta do projeto):
    python scripts\\baixar_pdfs.py                          # baixa tudo o que ainda falta
    python scripts\\baixar_pdfs.py --somente npt-022_2015-03 lei-19449   # só esses ids
    python scripts\\baixar_pdfs.py --reverificar            # baixa de novo e avisa o que mudou

O que ele faz:
1. Lê dados/catalogo.csv e escolhe as linhas com baixar = sim e com link.
   (As normas "pendente" não têm link e ficam de fora.)
2. Pula o que já foi baixado (o arquivo existe no computador). Assim dá para
   interromper (Ctrl+C) e rodar de novo, que ele continua de onde parou.
3. PDFs vão para dados/pdfs/<tipo>/<id>.pdf.
   Leis, decretos e resoluções (páginas do legislacao.pr.gov.br) vão para
   dados/paginas/<id>.html, sempre na versão "Compilado" (texto atual).
4. Confere se o PDF é mesmo um PDF (o arquivo começa com "%PDF"). Se o site
   devolver uma página de erro, nada é salvo.
5. Preenche no catálogo: arquivo_local, hash_sha256, tamanho_bytes e data_download.
6. Linhas com revisado = sim: só preenche as colunas de download se estiverem
   vazias, e nunca troca um arquivo já registrado (só avisa).
"""

import argparse
import hashlib
import re
import sys
import time
import urllib.request

from catalogo import PASTA_PROJETO, gravar_catalogo, hoje, ler_catalogo

NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
PAUSA_SEGUNDOS = 1  # espera entre um download e outro, para não sobrecarregar o site
TIPOS_PAGINA = {"lei", "decreto", "resolucao"}  # não são PDF: são páginas do legislacao.pr.gov.br


def caminho_destino(linha):
    """Caminho relativo (a partir da pasta do projeto) onde o arquivo será salvo."""
    if linha["tipo"] in TIPOS_PAGINA:
        return f"dados/paginas/{linha['id']}.html"
    return f"dados/pdfs/{linha['tipo']}/{linha['id']}.pdf"


def endereco_download(linha):
    """Endereço de onde o arquivo é baixado.

    Para leis, decretos e resoluções, o link do site do CBMPR abre a versão "Alterado"
    do legislacao.pr.gov.br (texto antigo e novo misturados). Usamos sempre a versão
    "Compilado" (só o texto atual), montada a partir do código do ato (codAto)."""
    if linha["tipo"] in TIPOS_PAGINA:
        codigo = re.search(r"codAto=(\d+)", linha["link_origem"])
        if codigo:
            return ("https://www.legislacao.pr.gov.br/legislacao/listarAtosAno.do?action=exibir"
                    f"&codAto={codigo.group(1)}&codTipoAto=&tipoVisualizacao=compilado")
    return linha["link_origem"]


def baixar(endereco):
    """Baixa o endereço e devolve o conteúdo em bytes."""
    pedido = urllib.request.Request(endereco, headers={"User-Agent": NAVEGADOR})
    with urllib.request.urlopen(pedido, timeout=120) as resposta:
        return resposta.read()


def limpar_pagina(conteudo):
    """O legislacao.pr.gov.br coloca na página um código de sessão (";jsessionid=...")
    que muda a cada visita. Ele é apagado para que a "impressão digital" (hash) só
    mude quando o texto da lei mudar de verdade."""
    return re.sub(rb";jsessionid=[A-Za-z0-9._-]+", b"", conteudo)


def conteudo_valido(linha, conteudo):
    """Devolve uma mensagem de erro, ou None se o conteúdo parecer certo."""
    if not conteudo:
        return "o arquivo veio vazio"
    if linha["tipo"] in TIPOS_PAGINA:
        if b"<html" not in conteudo[:5000].lower():
            return "não parece uma página HTML"
    elif not conteudo.startswith(b"%PDF"):
        return "não é um PDF (o site pode ter devolvido uma página de erro)"
    return None


def processar(linha, reverificar):
    """Baixa uma linha do catálogo. Devolve 'baixado', 'igual', 'mudou', 'pulado' ou 'erro'."""
    revisado = linha["revisado"] == "sim"
    relativo = linha["arquivo_local"] or caminho_destino(linha)
    arquivo = PASTA_PROJETO / relativo

    if arquivo.exists() and linha["hash_sha256"] and not reverificar:
        return "pulado"

    print(f"  {linha['id']} ... ", end="", flush=True)
    try:
        conteudo = baixar(endereco_download(linha))
    except Exception as erro:
        print(f"ERRO ao baixar: {erro}")
        return "erro"
    if linha["tipo"] in TIPOS_PAGINA:
        conteudo = limpar_pagina(conteudo)

    problema = conteudo_valido(linha, conteudo)
    if problema:
        print(f"ERRO: {problema}")
        return "erro"

    impressao = hashlib.sha256(conteudo).hexdigest()
    situacao = "baixado"
    if linha["hash_sha256"] and arquivo.exists():
        if impressao == linha["hash_sha256"]:
            print("sem mudança")
            return "igual"
        if revisado:
            print("MUDOU no site, mas a linha está revisada: nada foi trocado. Confira à mão.")
            return "mudou"
        situacao = "mudou"

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(conteudo)

    novos = {
        "arquivo_local": relativo,
        "hash_sha256": impressao,
        "tamanho_bytes": str(len(conteudo)),
        "data_download": hoje(),
    }
    for coluna, valor in novos.items():
        if not revisado or not linha[coluna]:
            linha[coluna] = valor

    tamanho_kb = len(conteudo) / 1024
    if situacao == "mudou":
        print(f"MUDOU no site: arquivo novo salvo ({tamanho_kb:.0f} KB)")
    else:
        print(f"ok ({tamanho_kb:.0f} KB)")
    return situacao


def main():
    parser = argparse.ArgumentParser(description="Baixa os PDFs e as páginas das normas do catálogo.")
    parser.add_argument("--somente", nargs="+", metavar="ID",
                        help="baixa só os ids indicados (ex.: npt-022_2015-03 lei-19449)")
    parser.add_argument("--reverificar", action="store_true",
                        help="baixa de novo o que já foi baixado e avisa se o arquivo mudou")
    args = parser.parse_args()

    linhas = ler_catalogo()
    if not linhas:
        sys.exit("ERRO: o catálogo dados/catalogo.csv não existe ou está vazio.")

    escolhidas = [l for l in linhas if l["baixar"] == "sim" and l["link_origem"]]
    if args.somente:
        ids_existentes = {l["id"] for l in linhas}
        desconhecidos = [i for i in args.somente if i not in ids_existentes]
        if desconhecidos:
            sys.exit(f"ERRO: ids que não estão no catálogo: {', '.join(desconhecidos)}")
        escolhidas = [l for l in escolhidas if l["id"] in args.somente]

    print(f"{len(escolhidas)} documento(s) a verificar.")
    contagem = {"baixado": 0, "igual": 0, "mudou": 0, "pulado": 0, "erro": 0}
    try:
        for linha in escolhidas:
            resultado = processar(linha, args.reverificar)
            contagem[resultado] += 1
            if resultado != "pulado":
                gravar_catalogo(linhas)  # grava a cada arquivo: nada se perde se for interrompido
                time.sleep(PAUSA_SEGUNDOS)
    except KeyboardInterrupt:
        print("\nInterrompido. O que já foi baixado ficou registrado no catálogo.")
        gravar_catalogo(linhas)

    print()
    print("Resumo:")
    print(f"  baixados agora:        {contagem['baixado']}")
    print(f"  já estavam baixados:   {contagem['pulado']}")
    if args.reverificar:
        print(f"  sem mudança:           {contagem['igual']}")
        print(f"  mudaram no site:       {contagem['mudou']}")
    print(f"  erros:                 {contagem['erro']}")
    if contagem["erro"]:
        print("Rode o programa de novo para tentar outra vez os que deram erro.")


if __name__ == "__main__":
    main()
