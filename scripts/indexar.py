"""
Protótipo, Passo 4 — Monta o arquivo de busca dados/busca.sqlite.

Como usar (no PowerShell, dentro da pasta do projeto):
    python scripts\\indexar.py

O que ele faz:
1. Lê o catálogo (dados/catalogo.csv) e os textos extraídos (dados/texto/<id>.jsonl).
2. Cria do zero o arquivo dados/busca.sqlite, com:
   - normas:  uma linha por versão de norma (dados do catálogo);
   - trechos: o texto de cada trecho, com um índice de busca (FTS5) que ignora
              acentos e maiúsculas;
   - info:    data da indexação e da última verificação do site.
3. O arquivo é montado com outro nome e só no fim substitui o antigo. Assim, se der
   erro no meio, a busca antiga continua funcionando.

Rode de novo sempre que extrair textos novos (extrair_texto.py).
"""

import json
import sqlite3
from datetime import datetime

from baixar_pdfs import endereco_download
from catalogo import ARQUIVO_ESTADO, PASTA_PROJETO, ler_catalogo

PASTA_TEXTO = PASTA_PROJETO / "dados" / "texto"
ARQUIVO_BUSCA = PASTA_PROJETO / "dados" / "busca.sqlite"
ARQUIVO_TEMPORARIO = ARQUIVO_BUSCA.with_suffix(".tmp")

COLUNAS_NORMAS = [
    "id", "norma_id", "tipo", "numero", "parte", "titulo", "versao",
    "vigencia_inicio", "vigencia_fim", "substituida_por", "link_oficial",
    "paginas", "precisa_ocr", "revisado",
]


def criar_tabelas(conexao):
    conexao.execute(f"CREATE TABLE normas ({', '.join(COLUNAS_NORMAS)}, PRIMARY KEY (id))")
    # remove_diacritics 2: ignora acentos ("emergencia" acha "emergência").
    # As colunas UNINDEXED são guardadas, mas não entram na busca.
    conexao.execute("""
        CREATE VIRTUAL TABLE trechos USING fts5(
            texto,
            versao_id UNINDEXED,
            item UNINDEXED,
            pagina UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    conexao.execute("CREATE TABLE info (chave TEXT PRIMARY KEY, valor TEXT)")


def main():
    catalogo = ler_catalogo()
    if ARQUIVO_TEMPORARIO.exists():
        ARQUIVO_TEMPORARIO.unlink()

    conexao = sqlite3.connect(ARQUIVO_TEMPORARIO)
    criar_tabelas(conexao)

    total_trechos = 0
    sem_texto = []
    for linha in catalogo:
        # link_oficial: o PDF, ou a versão "Compilado" da lei no legislacao.pr.gov.br.
        dados = dict(linha, link_oficial=endereco_download(linha) if linha["link_origem"] else "")
        conexao.execute(
            f"INSERT INTO normas VALUES ({', '.join('?' * len(COLUNAS_NORMAS))})",
            [dados[c] for c in COLUNAS_NORMAS],
        )

        arquivo_texto = PASTA_TEXTO / f"{linha['id']}.jsonl"
        if not arquivo_texto.exists():
            if linha["link_origem"]:
                sem_texto.append(linha["id"])
            continue
        with open(arquivo_texto, encoding="utf-8") as arquivo:
            trechos = [json.loads(l) for l in arquivo if l.strip()]
        conexao.executemany(
            "INSERT INTO trechos (texto, versao_id, item, pagina) VALUES (?, ?, ?, ?)",
            [(t["texto"], t["versao_id"], t["item"], t["pagina"]) for t in trechos],
        )
        total_trechos += len(trechos)

    estado = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8")) if ARQUIVO_ESTADO.exists() else {}
    info = {
        "indexado_em": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "ultima_verificacao": estado.get("ultima_verificacao", ""),
        "total_normas": str(len(catalogo)),
        "total_revisadas": str(sum(1 for l in catalogo if l["revisado"] == "sim")),
        "total_trechos": str(total_trechos),
    }
    conexao.executemany("INSERT INTO info VALUES (?, ?)", info.items())
    # Deixa o índice compacto e mais rápido.
    conexao.execute("INSERT INTO trechos (trechos) VALUES ('optimize')")
    conexao.commit()
    conexao.close()

    ARQUIVO_TEMPORARIO.replace(ARQUIVO_BUSCA)

    print(f"Normas no catálogo: {len(catalogo)}")
    print(f"Trechos indexados:  {total_trechos}")
    if sem_texto:
        print(f"AVISO: {len(sem_texto)} norma(s) com link, mas sem texto extraído: {', '.join(sem_texto)}")
        print("       Rode antes: .\\.venv\\Scripts\\python.exe scripts\\extrair_texto.py")
    print(f"Arquivo de busca: {ARQUIVO_BUSCA.relative_to(PASTA_PROJETO)}")


if __name__ == "__main__":
    main()
