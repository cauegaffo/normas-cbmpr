"""
Protótipo, Passo 3 — Extrai o texto dos PDFs e das páginas das leis, dividido em itens.

Como usar (no PowerShell, dentro da pasta do projeto):
    .\\.venv\\Scripts\\python.exe scripts\\extrair_texto.py                       # todos os documentos baixados
    .\\.venv\\Scripts\\python.exe scripts\\extrair_texto.py --somente npt-022_2015-03 lei-19449

O que ele faz:
1. Para cada documento baixado (coluna arquivo_local do catálogo), lê o texto:
   - PDFs: página por página, com o pdfplumber;
   - leis, decretos e resoluções: o texto da página do legislacao.pr.gov.br (sem número de página).
2. Apaga cabeçalhos e rodapés que se repetem em muitas páginas.
3. Divide o texto em itens:
   - NPTs, NPAs e OTs: numeração decimal (5, 5.1, 5.1.3) e anexos (Anexo A, A.1, F1.2);
   - CSCIP, leis, decretos, resoluções e portarias: por artigo (Art. 12).
   Texto antes do primeiro item (capa, sumário) fica no item "início".
4. Grava dados/texto/<id>.jsonl: uma linha por trecho (um trecho por item e por página),
   com versao_id, item, pagina e texto.
5. Preenche no catálogo as colunas paginas e precisa_ocr
   (em linhas com revisado = sim, só se estiverem vazias).
"""

import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser

import pdfplumber

from catalogo import PASTA_PROJETO, gravar_catalogo, ler_catalogo

PASTA_TEXTO = PASTA_PROJETO / "dados" / "texto"
TIPOS_POR_ARTIGO = {"lei", "decreto", "resolucao", "portaria", "cscip"}
MINIMO_CARACTERES = 30   # página com menos texto que isso é considerada "sem texto"
INICIO = "início"        # item do texto que vem antes do primeiro item numerado

# --- Padrões de reconhecimento (expressões regulares) -----------------------
# "Art. 12", "Art. 1º", "Artigo 3º –"
RE_ARTIGO = re.compile(r"^(?:Art\.|Artigo)\s*(\d{1,3})\s*(?:º|°|o\b)?")
# "5 PROCEDIMENTOS", "2.APLICAÇÃO", "5.1.3 Texto", "4.780 Verga", "12.1. Os parques"
RE_DECIMAL = re.compile(r"^(\d{1,2}(?:\.\d{1,3})*)\.?\s*(?=[^\d\s.,)])(.*)$")
# "ANEXO A", "ANEXO F - Título"
RE_ANEXO = re.compile(r"^ANEXO\s+([A-Z])\b")
# subitens de anexo: "A.1", "A.1.2", "F1.", "F1.1.", "H12.1.11"
RE_ITEM_ANEXO = re.compile(r"^([A-Z])\.?(\d{1,2}(?:\.\d{1,3})*)\.?\s+\S")
# linhas de sumário com pontilhado: "1 OBJETIVO......." ou "…"
RE_PONTILHADO = re.compile(r"(\.{4,}|…{2,}|\.…|…\.)")


# ---------------------------------------------------------------------------
# Leitura dos documentos
# ---------------------------------------------------------------------------

def limpar_linha(linha):
    """Troca marcadores de lista estranhos (caracteres de uso privado) por "•"
    e junta espaços repetidos."""
    linha = re.sub(r"[-]", "•", linha)
    return " ".join(linha.split())


def ler_pdf(arquivo):
    """Devolve uma lista com as linhas de cada página: [[linhas da pág. 1], [pág. 2], ...]."""
    paginas = []
    with pdfplumber.open(arquivo) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            linhas = [limpar_linha(l) for l in texto.split("\n")]
            paginas.append([l for l in linhas if l])
    return paginas


def tirar_cabecalhos_e_rodapes(paginas):
    """Apaga linhas que aparecem no topo ou no pé de pelo menos metade das páginas.
    Os números são trocados por "#" na comparação, para pegar "Página 3", "3" etc."""
    if len(paginas) < 3:
        return paginas

    def forma(linha):
        return re.sub(r"\d+", "#", linha)

    contagem = Counter()
    for linhas in paginas:
        pontas = set(forma(l) for l in linhas[:3] + linhas[-3:])
        contagem.update(pontas)
    repetidas = {f for f, n in contagem.items() if n >= max(3, len(paginas) / 2)}

    limpas = []
    for linhas in paginas:
        meio = linhas[3:-3] if len(linhas) > 6 else []
        topo = [l for l in linhas[:3] if forma(l) not in repetidas]
        pe = [l for l in linhas[-3:] if forma(l) not in repetidas] if len(linhas) > 6 else []
        if len(linhas) <= 6:
            # página curta: confere todas as linhas, mas só remove as repetidas
            limpas.append([l for l in linhas if forma(l) not in repetidas])
        else:
            limpas.append(topo + meio + pe)
    return limpas


class _TextoHtml(HTMLParser):
    """Transforma o HTML em texto simples, uma linha por parágrafo."""

    def __init__(self):
        super().__init__()
        self.partes = []
        self.ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignorar += 1
        if tag in ("p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignorar -= 1

    def handle_data(self, dados):
        if not self.ignorar:
            self.partes.append(dados)


# Marcações que no site aparecem sozinhas na linha: "Art. 1º", "§ 2º", "IV -", "a)", "Parágrafo único."
RE_MARCA_SOZINHA = re.compile(
    r"^(Art\.\s*\d+\s*[º°.]?|§\s*\d+\s*º?|[IVXLC]+\s*[-–]|[a-z]\)|Parágrafo único\.?)$")


def ler_pagina_html(arquivo):
    """Devolve as linhas do texto da lei (uma "página" só, sem número)."""
    leitor = _TextoHtml()
    leitor.feed(arquivo.read_text(encoding="utf-8", errors="replace"))
    linhas = [limpar_linha(l) for l in "".join(leitor.partes).split("\n")]
    linhas = [l for l in linhas if l]

    # O texto da norma vai do título ("Lei 19449 - 05 de Abril de 2018") até o aviso final.
    inicio = next((i for i, l in enumerate(linhas)
                   if re.match(r"^(Lei|Decreto|Resolução|Portaria)\b.*\d", l)), 0)
    fim = next((i for i, l in enumerate(linhas) if l.startswith("Este texto não substitui")),
               len(linhas))
    linhas = linhas[inicio:fim]

    # Junta as marcações soltas com a linha seguinte: "§ 1º" + "Esta Lei..." -> "§ 1º Esta Lei..."
    juntas = []
    for linha in linhas:
        if juntas and RE_MARCA_SOZINHA.match(juntas[-1]):
            juntas[-1] = f"{juntas[-1]} {linha}"
        else:
            juntas.append(linha)
    return [juntas]


# ---------------------------------------------------------------------------
# Divisão em itens
# ---------------------------------------------------------------------------

def rotulo_artigo(numero):
    numero = int(numero)
    return f"Art. {numero}º" if numero < 10 else f"Art. {numero}"


def eh_titulo_maiusculo(texto):
    """True se o texto parece um título em MAIÚSCULAS (ex.: "PROCEDIMENTOS")."""
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 3:
        return False
    return sum(c.isupper() for c in letras) / len(letras) >= 0.8


class Divisor:
    """Lê as linhas em ordem e decide quando começa um item novo."""

    def __init__(self, por_artigo):
        self.por_artigo = por_artigo
        self.item = INICIO
        self.ultimo_artigo = 0
        self.secao = 0            # número do título principal atual (5 em "5.1.3")
        self.viu_decimal = False  # já apareceu o primeiro item decimal?
        self.anexo = None         # letra do anexo atual
        self.no_sumario = False
        self.numeros_sumario = []
        self.recomecou = False    # a numeração de artigos já recomeçou no 1?

    def novo_item(self, linha):
        """Devolve o rótulo do item que começa nesta linha, ou None se a linha
        continua o item atual."""
        if self.por_artigo:
            return self._artigo(linha)

        # Artigos da portaria de aprovação, antes do texto da norma.
        if not self.viu_decimal:
            artigo = self._artigo(linha)
            if artigo:
                return f"Portaria, {artigo}"

        if linha.upper().startswith(("SUMÁRIO", "SUMARIO")):
            self.no_sumario = True
            self.numeros_sumario = []
            return None
        if RE_PONTILHADO.search(linha):
            # Linha de sumário com pontilhado ("1 OBJETIVO.......").
            # Anota o número para saber quando o sumário acaba.
            if self.no_sumario:
                numero = re.match(r"^(\d{1,2})\.?\s", linha)
                if numero:
                    self.numeros_sumario.append(int(numero.group(1)))
            return None

        anexo = RE_ANEXO.match(linha)
        if anexo and self.viu_decimal and not self.no_sumario:
            letra = anexo.group(1)
            if letra != self.anexo:
                self.anexo = letra
                self.secao = 0
                return f"Anexo {letra}"
            return None  # "ANEXO A (continuação)"

        if self.anexo:
            sub = RE_ITEM_ANEXO.match(linha)
            if sub and sub.group(1) == self.anexo:
                return f"{sub.group(1)}{'.' if '.' in linha[:2] else ''}{sub.group(2)}"

        decimal = RE_DECIMAL.match(linha)
        if not decimal:
            return None
        numero, resto = decimal.group(1), decimal.group(2)
        partes = numero.split(".")
        primeiro = int(partes[0])

        if self.no_sumario:
            if self.numeros_sumario and len(partes) == 1 and primeiro <= self.numeros_sumario[-1] \
                    and eh_titulo_maiusculo(resto):
                self.no_sumario = False  # a numeração recomeçou: acabou o sumário
                self.secao = 0
            else:
                if len(partes) == 1:
                    self.numeros_sumario.append(primeiro)
                return None

        if len(partes) == 1:
            # Título principal: número + texto em maiúsculas, em sequência.
            # O primeiro título pode ter qualquer número: as Partes 2, 3... de uma NPT
            # continuam a numeração da Parte 1 (ex.: NPT 015 Parte 2 começa no item 7).
            # Dentro de anexos, não: lá uma linha de tabela ("17 DEA") pareceria título.
            primeiro_titulo = self.secao == 0 and not self.anexo
            em_sequencia = primeiro_titulo or self.secao < primeiro <= self.secao + 3
            if resto[:1].isupper() and eh_titulo_maiusculo(resto) and em_sequencia:
                self.secao = primeiro
                self.viu_decimal = True
                return self._com_anexo(numero)
            return None

        # Subitem (5.1.3): precisa ser da seção atual e começar com letra maiúscula.
        # Isso descarta citações quebradas ("...do item / 5.10.2.3 desta NPT") e
        # valores de tabela ("5.000m²": número de item não tem zero à esquerda).
        if any(p.startswith("0") for p in partes[1:]) or not resto[:1].isupper():
            return None
        if primeiro == self.secao and self.viu_decimal:
            return self._com_anexo(numero)
        return None

    def _com_anexo(self, numero):
        return f"Anexo {self.anexo}, {numero}" if self.anexo else numero

    def _artigo(self, linha):
        artigo = RE_ARTIGO.match(linha)
        if not artigo:
            return None
        numero = int(artigo.group(1))
        # A numeração recomeçou no 1: o que veio antes era a portaria de aprovação
        # (ex.: o arquivo do CSCIP 2026 começa com a portaria, que tem 2 artigos).
        if self.por_artigo and numero == 1 and self.ultimo_artigo > 0 and not self.recomecou:
            self.recomecou = True
            self.ultimo_artigo = 1
            return rotulo_artigo(1)
        # Em sequência: evita confundir com "Artigo 24 do CSCIP..." no começo de uma linha.
        if self.ultimo_artigo < numero <= self.ultimo_artigo + 5:
            self.ultimo_artigo = numero
            return rotulo_artigo(numero)
        return None


def dividir_em_trechos(versao_id, paginas, por_artigo, tem_paginas):
    """Devolve a lista de trechos (um por item e por página)."""
    divisor = Divisor(por_artigo)
    trechos = []
    item = INICIO
    renomeou = False
    for numero_pagina, linhas in enumerate(paginas, start=1):
        atuais = []
        # Depois da portaria de aprovação vêm a página de assinatura e a capa da norma.
        # Se a página nova não tem nenhum artigo, o texto volta para "início".
        if item.startswith("Portaria, ") and not any(RE_ARTIGO.match(l) for l in linhas):
            item = INICIO

        def fechar():
            if atuais:
                trechos.append({
                    "versao_id": versao_id,
                    "item": item,
                    "pagina": numero_pagina if tem_paginas else None,
                    "texto": "\n".join(atuais),
                })

        for linha in linhas:
            novo = divisor.novo_item(linha)
            if novo:
                fechar()
                atuais = []
                item = novo
                if divisor.recomecou and not renomeou:
                    # Os artigos anteriores eram da portaria de aprovação.
                    renomeou = True
                    for trecho in trechos:
                        if trecho["item"].startswith("Art."):
                            trecho["item"] = f"Portaria, {trecho['item']}"
            atuais.append(linha)
        fechar()
    return trechos


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def processar(linha):
    """Extrai um documento. Devolve a quantidade de trechos, ou None em caso de erro."""
    arquivo = PASTA_PROJETO / linha["arquivo_local"]
    if not arquivo.exists():
        print(f"  {linha['id']}: ERRO, arquivo não encontrado ({linha['arquivo_local']})")
        return None

    eh_html = arquivo.suffix.lower() == ".html"
    try:
        paginas = ler_pagina_html(arquivo) if eh_html else ler_pdf(arquivo)
    except Exception as erro:
        print(f"  {linha['id']}: ERRO ao ler ({erro})")
        return None

    if not eh_html:
        paginas = tirar_cabecalhos_e_rodapes(paginas)
    # Conta depois de tirar os cabeçalhos: uma página só com cabeçalho está "sem texto".
    sem_texto = [] if eh_html else [
        n for n, linhas in enumerate(paginas, start=1)
        if len("".join(linhas)) < MINIMO_CARACTERES
    ]

    por_artigo = linha["tipo"] in TIPOS_POR_ARTIGO
    trechos = dividir_em_trechos(linha["id"], paginas, por_artigo, tem_paginas=not eh_html)

    PASTA_TEXTO.mkdir(parents=True, exist_ok=True)
    with open(PASTA_TEXTO / f"{linha['id']}.jsonl", "w", encoding="utf-8") as saida:
        for trecho in trechos:
            saida.write(json.dumps(trecho, ensure_ascii=False) + "\n")

    # Catálogo: páginas e OCR.
    precisa_ocr = "sim" if paginas and len(sem_texto) > len(paginas) / 2 else "não"
    novos = {"paginas": "" if eh_html else str(len(paginas)), "precisa_ocr": precisa_ocr}
    for coluna, valor in novos.items():
        if linha["revisado"] != "sim" or not linha[coluna]:
            linha[coluna] = valor

    itens = len({t["item"] for t in trechos})
    resumo = f"  {linha['id']}: {len(trechos)} trechos, {itens} itens"
    if not eh_html:
        resumo += f", {len(paginas)} páginas"
    if sem_texto:
        lista = ", ".join(map(str, sem_texto[:15])) + (" ..." if len(sem_texto) > 15 else "")
        resumo += f" | páginas quase sem texto: {lista}"
    if precisa_ocr == "sim":
        resumo += " | PRECISA DE OCR"
    print(resumo)
    return len(trechos)


def main():
    parser = argparse.ArgumentParser(description="Extrai o texto das normas, dividido em itens.")
    parser.add_argument("--somente", nargs="+", metavar="ID",
                        help="extrai só os ids indicados (ex.: npt-022_2015-03 lei-19449)")
    args = parser.parse_args()

    linhas = ler_catalogo()
    escolhidas = [l for l in linhas if l["arquivo_local"]]
    if args.somente:
        ids_existentes = {l["id"] for l in linhas}
        desconhecidos = [i for i in args.somente if i not in ids_existentes]
        if desconhecidos:
            sys.exit(f"ERRO: ids que não estão no catálogo: {', '.join(desconhecidos)}")
        escolhidas = [l for l in escolhidas if l["id"] in args.somente]

    print(f"{len(escolhidas)} documento(s) a extrair.")
    erros = 0
    for linha in escolhidas:
        if processar(linha) is None:
            erros += 1
    gravar_catalogo(linhas)
    print(f"\nPronto. Erros: {erros}. Textos em dados\\texto\\")


if __name__ == "__main__":
    main()
