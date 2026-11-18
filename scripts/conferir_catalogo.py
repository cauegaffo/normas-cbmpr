"""
Etapa 2 — Confere o catálogo (dados/catalogo.csv) e lista os problemas. Não altera nada.

Como usar (no PowerShell, dentro da pasta do projeto):
    python scripts\\conferir_catalogo.py

- ERROS: precisam ser corrigidos (o programa termina com código 1).
- AVISOS: pendências esperadas, que vão sendo resolvidas nas próximas etapas.
"""

import sys
from collections import Counter, defaultdict
from datetime import date

from catalogo import TIPOS, calcular_situacao, ler_catalogo


def data_valida(texto):
    try:
        date.fromisoformat(texto)
        return len(texto) == 10
    except ValueError:
        return False


def main():
    linhas = ler_catalogo()
    if not linhas:
        sys.exit("O catálogo está vazio ou não existe. Rode antes: python scripts\\listar_normas.py")

    erros, avisos = [], defaultdict(list)
    contagem_ids = Counter(l["id"] for l in linhas)
    ids = set(contagem_ids)

    for l in linhas:
        id_ = l["id"] or "(sem id)"
        if contagem_ids[l["id"]] > 1:
            erros.append(f"{id_}: id repetido")
        if l["tipo"] not in TIPOS:
            erros.append(f"{id_}: tipo desconhecido '{l['tipo']}'")
        for coluna in ("vigencia_inicio", "vigencia_fim"):
            if l[coluna] and not data_valida(l[coluna]):
                erros.append(f"{id_}: {coluna} '{l[coluna]}' não está no formato AAAA-MM-DD")
        if data_valida(l["vigencia_inicio"]) and data_valida(l["vigencia_fim"]) \
                and l["vigencia_inicio"] > l["vigencia_fim"]:
            erros.append(f"{id_}: início da vigência depois do fim")
        for substituta in filter(None, l["substituida_por"].split("|")):
            if substituta not in ids:
                erros.append(f"{id_}: substituida_por aponta para '{substituta}', que não existe")
        if l["baixar"] not in ("sim", "não"):
            erros.append(f"{id_}: baixar deve ser 'sim' ou 'não'")
        if l["baixar"] == "sim" and not l["link_origem"]:
            erros.append(f"{id_}: baixar = sim, mas não tem link")
        if l["revisado"] not in ("sim", "não", ""):
            erros.append(f"{id_}: revisado deve ser 'sim' ou 'não'")
        datas_ok = all(not l[c] or data_valida(l[c]) for c in ("vigencia_inicio", "vigencia_fim"))
        if datas_ok and l["situacao"] != calcular_situacao(l):
            erros.append(f"{id_}: situação '{l['situacao']}' desatualizada "
                         f"(deveria ser '{calcular_situacao(l)}'); rode listar_normas.py")

        if l["situacao"] == "vigente" and not l["vigencia_inicio"]:
            avisos["Vigentes sem data de início (completar na Etapa 5)"].append(id_)
        if l["situacao"] == "revogada" and not l["substituida_por"]:
            avisos["Revogadas sem indicação da substituta"].append(id_)
        if l["situacao"] == "pendente":
            avisos["Pendentes (sem link; procurar o arquivo)"].append(id_)
        if l["no_site"] == "não":
            avisos["Sumiram do site na última verificação"].append(id_)
        if l["revisado"] != "sim":
            avisos["Ainda não revisadas pelo dono"].append(id_)

    vigentes_por_norma = Counter(l["norma_id"] for l in linhas if l["situacao"] == "vigente")
    for norma_id, n in vigentes_por_norma.items():
        if n > 1:
            erros.append(f"{norma_id}: {n} versões vigentes ao mesmo tempo")

    print(f"Catálogo: {len(linhas)} linhas\n")
    print(f"ERROS: {len(erros)}")
    for erro in erros:
        print(f"  - {erro}")
    print()
    for titulo, lista in avisos.items():
        print(f"AVISO — {titulo}: {len(lista)}")
        print(f"  {', '.join(lista)}")
    print()
    if erros:
        print("Resultado: há ERROS para corrigir.")
        sys.exit(1)
    print("Resultado: nenhum erro (os avisos são pendências esperadas).")


if __name__ == "__main__":
    main()
