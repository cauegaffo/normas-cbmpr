"""
Etapa 2 — Monta (ou atualiza) o catálogo de normas a partir da página de legislação do CBMPR.

Como usar (no PowerShell, dentro da pasta do projeto):
    python scripts\\listar_normas.py                 # baixa a página do site
    python scripts\\listar_normas.py --copia-local   # usa dados\\fontes\\legislacao.html

O que ele faz:
1. Baixa a página https://www.bombeiros.pr.gov.br/Prevencao.
   Se não conseguir, usa a cópia salva manualmente (plano B).
2. Lê a seção "Legislação de Prevenção e Combate a Incêndios e a Desastres".
3. Reconhece cada norma: tipo, número, parte, título, versão e datas de vigência.
4. Atualiza dados/catalogo.csv sem apagar nada e sem mexer nas linhas com revisado = sim.
5. Grava a data da verificação em dados/estado.json.
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

from catalogo import (
    ARQUIVO_ESTADO,
    COLUNAS,
    PASTA_PROJETO,
    calcular_situacao,
    gravar_catalogo,
    hoje,
    ler_catalogo,
)

URL_PAGINA = "https://www.bombeiros.pr.gov.br/Prevencao"
COPIA_LOCAL = PASTA_PROJETO / "dados" / "fontes" / "legislacao.html"
NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

INICIO_SECAO = "Legislação de Prevenção e Combate a Incêndios e a Desastres"
FIM_SECAO = "consulta p"  # a seção termina no bloco "Consulta Publica"

# Normas que sabemos que existem, mas que não aparecem na página.
# Entram no catálogo como "pendente" (sem link). Ver CLAUDE.md, "A confirmar".
PENDENTES_CONHECIDAS = [
    {"tipo": "npt", "numero": "001", "parte": "1",
     "observacao": "Não aparece na página de legislação; situação a confirmar."},
    {"tipo": "npt", "numero": "001", "parte": "3",
     "observacao": "Não aparece na página de legislação; situação a confirmar."},
]

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}
_NOMES_MESES = "|".join(MESES)


# ---------------------------------------------------------------------------
# 1. Obter a página
# ---------------------------------------------------------------------------

def obter_html(usar_copia_local):
    """Devolve (html, fonte). Tenta o site primeiro; se falhar, usa a cópia local."""
    if not usar_copia_local:
        try:
            pedido = urllib.request.Request(URL_PAGINA, headers={"User-Agent": NAVEGADOR})
            with urllib.request.urlopen(pedido, timeout=60) as resposta:
                html = resposta.read().decode("utf-8", errors="replace")
            print(f"Página baixada do site: {URL_PAGINA}")
            return html, "site"
        except Exception as erro:
            print(f"AVISO: não consegui baixar a página ({erro}).")
            print("       Vou usar a cópia salva manualmente (plano B).")

    if not COPIA_LOCAL.exists():
        sys.exit(f"ERRO: a cópia local {COPIA_LOCAL} não existe. Salve a página no navegador.")
    print(f"Usando a cópia local: {COPIA_LOCAL}")
    return COPIA_LOCAL.read_text(encoding="utf-8", errors="replace"), "copia_local"


# ---------------------------------------------------------------------------
# 2. Transformar o HTML numa sequência de textos e links
# ---------------------------------------------------------------------------

class LeitorDePagina(HTMLParser):
    """Percorre o HTML e guarda, em ordem, os pedaços de texto e os links."""

    BLOCOS = {"p", "li", "div", "br", "tr", "td", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pedacos = []      # lista de ("texto", conteúdo) ou ("link", texto, endereço)
        self._texto = []
        self._link = None      # endereço do link aberto no momento
        self._texto_link = []
        self._ignorar = 0      # dentro de <script> ou <style>

    def _fechar_texto(self):
        texto = "".join(self._texto)
        if texto.strip():
            self.pedacos.append(("texto", texto))
        self._texto = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        elif tag == "a":
            self._fechar_texto()
            self._link = dict(attrs).get("href") or ""
            self._texto_link = []
        elif tag in self.BLOCOS and self._link is None:
            self._fechar_texto()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar -= 1
        elif tag == "a" and self._link is not None:
            self.pedacos.append(("link", "".join(self._texto_link), self._link))
            self._link = None
        elif tag in self.BLOCOS and self._link is None:
            self._fechar_texto()

    def handle_data(self, data):
        if self._ignorar:
            return
        if self._link is not None:
            self._texto_link.append(data)
        else:
            self._texto.append(data)


def limpar(texto):
    """Tira espaços repetidos, caracteres invisíveis, a marca 'NOVO!' e o '-' do começo."""
    texto = texto.replace("​", "").replace("\xa0", " ").replace("NOVO!", " ")
    texto = " ".join(texto.split())
    return texto.lstrip("- ").strip()


def recortar_secao(pedacos):
    """Fica só com a parte da página entre o título da seção de legislação e 'Consulta Publica'."""
    def texto_de(pedaco):
        return limpar(pedaco[1])

    inicio = next((i for i, p in enumerate(pedacos) if INICIO_SECAO in texto_de(p)), None)
    if inicio is None:
        sys.exit("ERRO: não encontrei a seção de legislação na página. O site pode ter mudado.")
    fim = next(
        (i for i in range(inicio + 1, len(pedacos)) if texto_de(pedacos[i]).lower().startswith(FIM_SECAO)),
        len(pedacos),
    )
    return pedacos[inicio + 1 : fim]


# ---------------------------------------------------------------------------
# 3. Reconhecer datas, versões e títulos
# ---------------------------------------------------------------------------

def data_por_extenso(texto):
    """'5 de novembro de 2026' -> '2026-11-05'. Devolve '' se não achar."""
    m = re.search(rf"(\d{{1,2}})\s+de\s+({_NOMES_MESES})\s+de\s+(\d{{4}})", texto, re.IGNORECASE)
    if not m:
        return ""
    return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1))).isoformat()


def mes_ano(texto):
    """Último 'Outubro de 2014' (ou 'Novembro 2026') do texto -> '2014-10'. Devolve '' se não achar."""
    achados = re.findall(rf"\b({_NOMES_MESES})\s+(?:de\s+)?(\d{{4}})", texto, re.IGNORECASE)
    if not achados:
        return ""
    mes, ano = achados[-1]
    return f"{ano}-{MESES[mes.lower()]:02d}"


def titulo_sem_data(texto):
    """Tira do título os pedaços que são data, versão ou aviso de vigência."""
    pedacos = [p.strip(" .") for p in re.split(r"\s+-\s+", texto)]
    uteis = []
    for p in pedacos:
        minusculo = p.lower()
        if not p:
            continue
        if re.fullmatch(rf"({_NOMES_MESES})\s+(de\s+)?\d{{4}}", minusculo):
            continue
        if re.fullmatch(r"\d{4}", p):
            continue
        if minusculo.startswith(("vigente até", "entra em vigência", "alterada em")):
            continue
        uteis.append(p)
    return " - ".join(uteis)


def nova_linha(**valores):
    """Cria uma linha do catálogo com todas as colunas (as não informadas ficam vazias)."""
    linha = {coluna: "" for coluna in COLUNAS}
    linha.update(valores)
    return linha


def montar_ids(linha):
    """Preenche norma_id e id a partir do tipo, número, parte e versão."""
    if not linha["norma_id"]:
        partes = [linha["tipo"]]
        if linha["numero"]:
            partes.append(linha["numero"])
        norma_id = "-".join(partes)
        if linha["parte"]:
            norma_id += f"-p{linha['parte']}"
        linha["norma_id"] = norma_id
    # Não repete a versão quando o norma_id já termina com ela (ex.: portaria-476-2025)
    if linha["versao"] and not linha["norma_id"].endswith(linha["versao"]):
        linha["id"] = f"{linha['norma_id']}_{linha['versao']}"
    else:
        linha["id"] = linha["norma_id"]


# ---------------------------------------------------------------------------
# 4. Interpretar cada link e cada texto da seção
# ---------------------------------------------------------------------------

def interpretar_link(rotulo, endereco, pai):
    """Transforma um link da página numa linha do catálogo. Devolve None se não reconhecer."""
    rotulo = limpar(rotulo)

    # Leis, decretos e resoluções (páginas do legislacao.pr.gov.br, não PDF)
    m = re.match(r"(Lei|Decreto|Resolução\s+SESP)\s*n?[º°o]?\s*([\d.]+)(?:/(\d{4}))?", rotulo, re.IGNORECASE)
    if m and "legislacao.pr.gov.br" in endereco:
        tipo = {"lei": "lei", "decreto": "decreto"}.get(m.group(1).lower(), "resolucao")
        numero = m.group(2).rstrip(".")
        ano = m.group(3) or ""
        norma_id = f"{tipo}-{numero.replace('.', '')}"
        if tipo == "resolucao":
            norma_id = f"resolucao-sesp-{numero}-{ano}"
        return nova_linha(tipo=tipo, numero=numero, versao=ano, norma_id=norma_id, link_origem=endereco)

    if ".pdf" not in endereco.lower():
        return None

    # CSCIP
    if rotulo.upper().startswith("CSCIP"):
        return nova_linha(tipo="cscip", titulo="Código de Segurança Contra Incêndio e Pânico",
                          versao=mes_ano(rotulo), link_origem=endereco)

    # Portarias: "Portaria nº 476/2025"
    m = re.match(r"Portaria\s*n?[º°o]?\s*(\d+)/(\d{4})", rotulo, re.IGNORECASE)
    if m:
        return nova_linha(tipo="portaria", numero=m.group(1).zfill(3), versao=m.group(2),
                          norma_id=f"portaria-{m.group(1).zfill(3)}-{m.group(2)}", link_origem=endereco)

    # NPT e NPA inteiras: "NPT 022 - Título - Março de 2015"
    m = re.match(r"(NPT|NPA)\s*0*(\d+)\s*-\s*(.*)", rotulo, re.IGNORECASE)
    if m:
        resto = m.group(3)
        alterada = re.search(r"Alterada em [^-]*", resto, re.IGNORECASE)
        return nova_linha(tipo=m.group(1).lower(), numero=m.group(2).zfill(3), titulo=titulo_sem_data(resto),
                          versao=mes_ano(resto), link_origem=endereco,
                          observacao=alterada.group(0).strip(" .") if alterada else "")

    # Partes de uma norma: "Parte 1 - Regras Gerais" (o cabeçalho veio antes, em 'pai')
    m = re.match(r"Parte\s*0*(\d+)\s*-\s*(.*)", rotulo, re.IGNORECASE)
    if m and pai:
        return nova_linha(tipo=pai["tipo"], numero=pai["numero"], parte=m.group(1),
                          titulo=f"{pai['titulo']} — {m.group(2).strip(' .')}", versao=pai["versao"],
                          vigencia_inicio=pai["inicio"], link_origem=endereco)

    # Orientações técnicas: "nº 01 - 13 - Título - 2013" ou "nº 006/2025 - Título"
    m = re.match(r"Orienta\w*\s+T\w*cnica\s+n\s*[º°o.]*\s*(\d+)\s*[-/]\s*(\d{2,4})\b\s*-?\s*(.*)",
                 rotulo, re.IGNORECASE)
    if m:
        ano = m.group(2) if len(m.group(2)) == 4 else f"20{m.group(2)}"
        numero = m.group(1).zfill(3)
        return nova_linha(tipo="ot", numero=numero, titulo=titulo_sem_data(m.group(3)), versao=ano,
                          norma_id=f"ot-{numero}-{ano}", link_origem=endereco)

    return None


def aplicar_texto(linha, texto):
    """Usa um texto que aparece logo depois de um link para completar aquela linha."""
    minusculo = texto.lower()
    if "vigente até" in minusculo:
        linha["vigencia_fim"] = data_por_extenso(texto) or linha["vigencia_fim"]
    if "entra em vigência" in minusculo:
        linha["vigencia_inicio"] = data_por_extenso(texto) or linha["vigencia_inicio"]
    if minusculo.startswith(("vigente até", "entra em vigência")):
        return  # texto só de data: já aproveitado
    if not linha["titulo"]:
        linha["titulo"] = texto.strip(" .")  # descrição de leis, decretos e portarias
    else:
        linha["observacao"] = "; ".join(filter(None, [linha["observacao"], texto]))


def interpretar_secao(pedacos):
    """Percorre a seção e devolve (linhas do catálogo, links não reconhecidos)."""
    linhas, nao_reconhecidos = [], []
    ultima = None   # última linha criada a partir de um link
    pai = None      # cabeçalho de norma dividida em partes (ex.: "NPT 015 - Controle de fumaça")

    for pedaco in pedacos:
        if pedaco[0] == "texto":
            texto = limpar(pedaco[1])
            if not texto:
                continue
            m = re.match(r"(NPT|NPA)\s*0*(\d+)\s*-\s*(.*)", texto, re.IGNORECASE)
            if m and "revogada" in texto.lower():
                # Norma revogada que aparece só como texto, sem link -> pendente
                parte = re.search(r"Parte\s*0*(\d+)", texto, re.IGNORECASE)
                linhas.append(nova_linha(tipo=m.group(1).lower(), numero=m.group(2).zfill(3),
                                         parte=parte.group(1) if parte else "", observacao=texto))
                ultima, pai = None, None
            elif m:
                # Cabeçalho de norma dividida em partes; as partes vêm nos links seguintes
                resto = m.group(3)
                pai = {"tipo": m.group(1).lower(), "numero": m.group(2).zfill(3),
                       "titulo": titulo_sem_data(resto), "versao": mes_ano(resto),
                       "inicio": data_por_extenso(resto) if "entra em vigência" in resto.lower() else ""}
                ultima = None
            elif ultima:
                aplicar_texto(ultima, texto)
            continue

        _, rotulo, endereco = pedaco
        if not limpar(rotulo) or endereco.startswith("#") or "#collapse" in endereco:
            continue
        linha = interpretar_link(rotulo, endereco, pai)
        if linha is None:
            nao_reconhecidos.append(f"{limpar(rotulo)} -> {endereco}")
            continue
        if not linha["parte"]:
            pai = None  # uma norma inteira encerra a lista de partes anterior
        linhas.append(linha)
        ultima = linha

    for extra in PENDENTES_CONHECIDAS:
        linhas.append(nova_linha(**extra))

    for linha in linhas:
        montar_ids(linha)
        linha["baixar"] = "sim" if linha["link_origem"] else "não"

    # IDs repetidos (não deveria acontecer): acrescenta um sufixo e avisa
    vistos = {}
    for linha in linhas:
        if linha["id"] in vistos:
            vistos[linha["id"]] += 1
            print(f"AVISO: id repetido {linha['id']}; renomeado para {linha['id']}_{vistos[linha['id']]}")
            linha["id"] = f"{linha['id']}_{vistos[linha['id']]}"
        else:
            vistos[linha["id"]] = 1

    sugerir_substituicoes(linhas)
    return linhas, nao_reconhecidos


def sugerir_substituicoes(linhas):
    """Se uma versão termina num dia e outra da mesma norma começa no dia seguinte,
    sugere que a segunda substituiu a primeira."""
    for antiga in linhas:
        if not antiga["vigencia_fim"] or antiga["substituida_por"]:
            continue
        dia_seguinte = (date.fromisoformat(antiga["vigencia_fim"]) + timedelta(days=1)).isoformat()
        novas = [l["id"] for l in linhas
                 if l["norma_id"] == antiga["norma_id"] and l["vigencia_inicio"] == dia_seguinte]
        antiga["substituida_por"] = "|".join(novas)


# ---------------------------------------------------------------------------
# 5. Juntar com o catálogo que já existe
# ---------------------------------------------------------------------------

COLUNAS_DO_SITE = ["norma_id", "tipo", "numero", "parte", "titulo", "versao", "link_origem"]
COLUNAS_SUGERIDAS = ["vigencia_inicio", "vigencia_fim", "substituida_por", "baixar", "observacao"]


def atualizar_catalogo(existentes, encontradas, data):
    """Junta o que foi encontrado no site com o catálogo atual.
    Devolve (catálogo atualizado, novas, links alterados, sumidas)."""
    por_id = {linha["id"]: linha for linha in existentes}
    vistos, novas, alteradas = set(), [], []

    for nova in encontradas:
        vistos.add(nova["id"])
        atual = por_id.get(nova["id"])
        if nova["link_origem"]:
            nova["ultima_verificacao"], nova["no_site"] = data, "sim"

        if atual is None:  # norma nova
            nova["revisado"] = "não"
            por_id[nova["id"]] = nova
            novas.append(nova["id"])
            continue

        if atual["link_origem"] and nova["link_origem"] and atual["link_origem"] != nova["link_origem"]:
            alteradas.append(nova["id"])
        if nova["link_origem"]:
            atual["ultima_verificacao"], atual["no_site"] = data, "sim"
        if atual["revisado"] == "sim":
            continue  # linha conferida pelo dono: não mexer
        for coluna in COLUNAS_DO_SITE:
            atual[coluna] = nova[coluna]
        for coluna in COLUNAS_SUGERIDAS:
            if not atual[coluna]:
                atual[coluna] = nova[coluna]

    sumidas = []
    for id_, linha in por_id.items():
        if id_ not in vistos and linha["link_origem"]:
            linha["no_site"] = "não"
            sumidas.append(id_)

    catalogo = list(por_id.values())
    for linha in catalogo:
        linha["situacao"] = calcular_situacao(linha, data)
    return catalogo, novas, alteradas, sumidas


# ---------------------------------------------------------------------------
# 6. Programa principal
# ---------------------------------------------------------------------------

def contar(linhas, coluna):
    contagem = {}
    for linha in linhas:
        contagem[linha[coluna]] = contagem.get(linha[coluna], 0) + 1
    return ", ".join(f"{chave or '(vazio)'}: {n}" for chave, n in sorted(contagem.items()))


def main():
    parser = argparse.ArgumentParser(description="Monta ou atualiza dados/catalogo.csv.")
    parser.add_argument("--copia-local", action="store_true",
                        help="usar dados/fontes/legislacao.html em vez de baixar a página")
    args = parser.parse_args()

    html, fonte = obter_html(args.copia_local)
    leitor = LeitorDePagina()
    leitor.feed(html)
    encontradas, nao_reconhecidos = interpretar_secao(recortar_secao(leitor.pedacos))

    data = hoje()
    catalogo, novas, alteradas, sumidas = atualizar_catalogo(ler_catalogo(), encontradas, data)
    gravar_catalogo(catalogo)

    links = sum(1 for l in encontradas if l["link_origem"])
    ARQUIVO_ESTADO.write_text(json.dumps({
        "ultima_verificacao": datetime.now().isoformat(timespec="minutes"),
        "fonte": fonte,
        "endereco": URL_PAGINA,
        "links_encontrados": links,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"Links de normas encontrados na página: {links}")
    print(f"Linhas no catálogo: {len(catalogo)}")
    print(f"  por tipo:     {contar(catalogo, 'tipo')}")
    print(f"  por situação: {contar(catalogo, 'situacao')}")
    print(f"Novas nesta execução: {len(novas)}")
    if alteradas:
        print(f"ATENÇÃO, link mudou (confira): {', '.join(alteradas)}")
    if sumidas:
        print(f"ATENÇÃO, sumiram do site (no_site = não): {', '.join(sumidas)}")
    if nao_reconhecidos:
        print("ATENÇÃO, links da seção que não reconheci (ficaram de fora):")
        for item in nao_reconhecidos:
            print(f"  - {item}")
    print(f"\nCatálogo gravado em: {PASTA_PROJETO / 'dados' / 'catalogo.csv'}")
    print("Próximo passo: python scripts\\conferir_catalogo.py")


if __name__ == "__main__":
    main()
