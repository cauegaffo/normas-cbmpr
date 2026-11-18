"""
Funções compartilhadas pelos programas que leem e gravam o catálogo de normas.

O catálogo é o arquivo dados/catalogo.csv: uma linha por versão de norma.
Ele usa ";" como separador e UTF-8 com BOM, para abrir certo no Excel em português.
"""

import csv
from datetime import date
from pathlib import Path

# Pastas e arquivos do projeto (calculados a partir do lugar deste arquivo).
PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_CATALOGO = PASTA_PROJETO / "dados" / "catalogo.csv"
ARQUIVO_ESTADO = PASTA_PROJETO / "dados" / "estado.json"

# Colunas do catálogo, na ordem em que aparecem no Excel.
COLUNAS = [
    "id",                  # identificador único da versão, ex.: npt-022_2015-03
    "norma_id",            # agrupa as versões da mesma norma, ex.: npt-022
    "tipo",                # lei, decreto, resolucao, portaria, cscip, npa, npt, ot
    "numero",              # ex.: 022
    "parte",               # número da parte, quando a norma é dividida (ex.: 3)
    "titulo",
    "versao",              # AAAA-MM (ou AAAA) tirado do rótulo do site
    "vigencia_inicio",     # AAAA-MM-DD
    "vigencia_fim",        # AAAA-MM-DD; vazio = ainda em vigor
    "substituida_por",     # id da versão que substituiu esta (várias separadas por |)
    "situacao",            # calculada: vigente, futura, revogada ou pendente
    "baixar",              # sim / não
    "link_origem",         # endereço do PDF (ou da página, para leis e decretos)
    "arquivo_local",       # preenchido pelo download (Etapa 4)
    "hash_sha256",         # "impressão digital" do arquivo (Etapa 4)
    "tamanho_bytes",       # Etapa 4
    "paginas",             # Etapa 7
    "precisa_ocr",         # Etapa 7
    "data_download",       # Etapa 4
    "ultima_verificacao",  # data em que o link foi visto no site pela última vez
    "no_site",             # sim = o link apareceu na última verificação; não = sumiu
    "revisado",            # sim = o dono conferiu; os programas não sobrescrevem
    "observacao",
]

# Tipos de norma aceitos, na ordem em que aparecem no catálogo.
TIPOS = ["lei", "decreto", "resolucao", "portaria", "cscip", "npa", "npt", "ot"]


def hoje():
    """Data de hoje no formato AAAA-MM-DD."""
    return date.today().isoformat()


def ler_catalogo():
    """Lê o catálogo e devolve uma lista de linhas (cada linha é um dicionário).
    Se o arquivo ainda não existir, devolve uma lista vazia."""
    if not ARQUIVO_CATALOGO.exists():
        return []
    with open(ARQUIVO_CATALOGO, encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo, delimiter=";"))
    # Garante que toda linha tenha todas as colunas (mesmo que vazias).
    for linha in linhas:
        for coluna in COLUNAS:
            linha[coluna] = (linha.get(coluna) or "").strip()
    return linhas


def _chave_de_ordem(linha):
    """Ordena por tipo, número, parte e versão."""
    tipo = TIPOS.index(linha["tipo"]) if linha["tipo"] in TIPOS else len(TIPOS)
    parte = int(linha["parte"]) if linha["parte"].isdigit() else 0
    return (tipo, linha["numero"].zfill(6), linha["norma_id"], parte, linha["versao"])


def gravar_catalogo(linhas):
    """Grava o catálogo no formato que o Excel em português entende."""
    ARQUIVO_CATALOGO.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_CATALOGO, "w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, delimiter=";", extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(sorted(linhas, key=_chave_de_ordem))


def calcular_situacao(linha, data_referencia=None):
    """Calcula a situação de uma versão a partir das datas de vigência.

    - pendente: norma conhecida, mas ainda sem link para o arquivo;
    - futura:   começa a valer depois da data de referência;
    - revogada: deixou de valer antes da data de referência;
    - vigente:  nos demais casos (inclusive quando as datas ainda não foram preenchidas).
    """
    if not linha["link_origem"]:
        return "pendente"
    referencia = data_referencia or hoje()
    inicio, fim = linha["vigencia_inicio"], linha["vigencia_fim"]
    # Datas no formato AAAA-MM-DD podem ser comparadas como texto.
    if inicio and inicio > referencia:
        return "futura"
    if fim and fim < referencia:
        return "revogada"
    return "vigente"
