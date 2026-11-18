"""
Perguntas em linguagem natural respondidas pela IA, usando APENAS os trechos das normas.

Fluxo:
1. A pergunta vira termos de busca (sem as palavras de pergunta, como "qual", "deve", "mínimo").
   Isso é feito aqui mesmo, sem IA: não gasta cota e funciona sem chave.
2. A busca (com sinônimos, no modo "qualquer palavra") encontra os trechos mais relevantes.
3. Monta as instruções e a mensagem com os trechos rotulados [T1], [T2]...
4. A IA responde citando norma, versão, item e página; se não achar nos trechos, diz que não achou.

A "pergunta pronta" (instruções + trechos + pergunta) pode ser copiada para qualquer IA e
funciona mesmo sem chave configurada.

No terminal:
    python scripts\\perguntar.py "Qual a distância máxima entre pontos de iluminação de emergência?"
    python scripts\\perguntar.py "..." --pronta      # só mostra a pergunta pronta (sem IA)
"""

import argparse
import re
import sys
from datetime import datetime

import busca

TRECHOS_PARA_IA = 20          # quantos trechos vão para a IA
MAXIMO_CARACTERES = 1500      # tamanho máximo de cada trecho enviado

# Palavras típicas de pergunta, que não ajudam a achar o trecho (comparadas sem acentos).
PALAVRAS_DE_PERGUNTA = {
    "qual", "quais", "como", "quando", "onde", "quanto", "quanta", "quantos", "quantas", "porque",
    "deve", "devem", "ser", "sao", "e", "esta", "estao", "pode", "podem", "precisa", "precisam",
    "ha", "tem", "ter", "existe", "existem", "minimo", "minima", "maximo", "maxima",
    "obrigatorio", "obrigatoria", "exigido", "exigida", "exigidos", "exigidas", "necessario",
    "necessaria", "sobre", "diz", "dizem", "entre", "cada", "ate", "isso", "essa", "esse",
    "voce", "me", "meu", "minha", "segundo", "conforme", "norma", "normas",
}

INSTRUCOES = """Você é um assistente que responde perguntas sobre a legislação de prevenção de \
incêndios do Corpo de Bombeiros Militar do Paraná (CBMPR).

Regras obrigatórias:
1. Use APENAS os trechos fornecidos (marcados [T1], [T2], ...). Não use nenhum conhecimento de fora, \
nem outras normas que não estejam nos trechos.
2. Toda afirmação deve citar a fonte entre colchetes, com norma, versão, item e página, por exemplo: \
[NPT 022, versão 2015-03, item 5.10.2.3, pág. 13]. Para leis e decretos, que não têm página, cite o artigo.
3. Se os trechos não trouxerem a resposta, responda exatamente: "Não encontrei a resposta nos trechos \
das normas consultados." Não tente adivinhar. Se a resposta for só parcial, diga o que foi encontrado \
e o que faltou.
4. Se usar um trecho com situação REVOGADA ou AINDA NÃO VIGENTE, avise isso claramente na resposta, \
junto da citação.
5. Se trechos diferentes disserem coisas diferentes, mostre as duas versões e cite as duas.
6. Responda em português, de forma curta e objetiva.
7. Termine lembrando que a ferramenta não é oficial e que o texto deve ser conferido no documento oficial."""


def data_br(texto):
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return texto or "?"


# Normas citadas na pergunta: "NPT 003", "NPA nº 2", "OT 001", "CSCIP".
RE_NORMA_CITADA = re.compile(r"\b(NPT|NPA|OT)\s*(?:n[º°o.]?\s*)?(\d{1,3})\b|\b(CSCIP)\b", re.IGNORECASE)


def normas_citadas(pergunta):
    """[("npt", "003"), ("cscip", "")] para as normas citadas na pergunta."""
    citadas = []
    for m in RE_NORMA_CITADA.finditer(pergunta):
        norma = ("cscip", "") if m.group(3) else (m.group(1).lower(), m.group(2).zfill(3))
        if norma not in citadas:
            citadas.append(norma)
    return citadas


def termos_da_pergunta(pergunta):
    """'Qual a distância máxima entre dois pontos de iluminação?' -> 'distância dois pontos iluminação'.
    Frases entre aspas são mantidas. Normas citadas ("NPT 003") saem dos termos: viram filtro."""
    frases = re.findall(r'"[^"]*"', pergunta)
    resto = re.sub(r'"[^"]*"', " ", pergunta).replace('"', " ")
    resto = RE_NORMA_CITADA.sub(" ", resto)
    palavras = [p for p in busca.palavras_de(resto)
                if p not in busca.PALAVRAS_IGNORADAS and busca.sem_acentos(p) not in PALAVRAS_DE_PERGUNTA]
    return " ".join(frases + palavras).strip()


def situacao_por_extenso(t):
    if t["situacao"] == "revogada":
        return f"REVOGADA (vigente até {data_br(t['vigencia_fim'])})"
    if t["situacao"] == "futura":
        return f"AINDA NÃO VIGENTE (começa a valer em {data_br(t['vigencia_inicio'])})"
    return "vigente"


def rotulo_trecho(numero, t):
    """[T1] NPT 022 — versão 2015-03 — situação: vigente — item 5.10.2.3 — página 13"""
    versao = t["versao"] or "sem versão"
    pagina = f"página {t['pagina']}" if t["pagina"] else "sem página (cite o artigo)"
    return (f"[T{numero}] {t['norma']} — versão {versao} — situação: {situacao_por_extenso(t)} — "
            f"item {t['item']} — {pagina}")


def texto_do_trecho(t):
    texto = t["texto"].strip()
    return texto if len(texto) <= MAXIMO_CARACTERES else texto[:MAXIMO_CARACTERES] + " […]"


def montar_mensagem(pergunta, trechos):
    blocos = [f"{rotulo_trecho(i, t)}\n{texto_do_trecho(t)}" for i, t in enumerate(trechos, start=1)]
    corpo = "\n\n".join(blocos) if blocos else "(nenhum trecho encontrado)"
    return f"TRECHOS DAS NORMAS:\n\n{corpo}\n\nPERGUNTA:\n{pergunta.strip()}"


def montar_pergunta_pronta(pergunta, trechos):
    """Instruções + trechos + pergunta, num texto só, para colar em qualquer IA."""
    return f"{INSTRUCOES}\n\n{montar_mensagem(pergunta, trechos)}"


def avisos_de_situacao(trechos):
    """Avisos que a TELA mostra sozinha (não depende da IA lembrar)."""
    avisos = []
    revogadas = sorted({f"{t['norma']} ({t['versao']})" for t in trechos if t["situacao"] == "revogada"})
    futuras = sorted({f"{t['norma']} ({t['versao']})" for t in trechos if t["situacao"] == "futura"})
    if revogadas:
        avisos.append("Há trechos de norma REVOGADA entre os usados: " + ", ".join(revogadas) + ".")
    if futuras:
        avisos.append("Há trechos de norma AINDA NÃO VIGENTE entre os usados: " + ", ".join(futuras) + ".")
    return avisos


def preparar(conexao, pergunta, incluir_todas=False, marca_inicio="[", marca_fim="]"):
    """Faz os passos 1 a 3 (sem IA). Devolve um dicionário com termos, trechos, avisos,
    mensagem e pergunta pronta."""
    termos = termos_da_pergunta(pergunta)
    citadas = normas_citadas(pergunta)
    trechos = []
    if termos:
        # Se a pergunta cita normas ("na NPT 003"), procura só nelas.
        resultado = busca.buscar(conexao, termos, incluir_todas=incluir_todas, limite=TRECHOS_PARA_IA,
                                 marca_inicio=marca_inicio, marca_fim=marca_fim,
                                 usar_sinonimos=True, modo="qualquer", normas=citadas or None)
        trechos = resultado["trechos"]
        sinonimos = resultado["sinonimos_usados"]
    else:
        sinonimos = {}
    return {
        "pergunta": pergunta.strip(),
        "termos": termos,
        "normas_citadas": [f"{busca.NOMES_TIPOS[t]} {n}".strip() for t, n in citadas],
        "sinonimos_usados": sinonimos,
        "trechos": trechos,
        "avisos": avisos_de_situacao(trechos),
        "instrucoes": INSTRUCOES,
        "mensagem": montar_mensagem(pergunta, trechos),
        "pergunta_pronta": montar_pergunta_pronta(pergunta, trechos),
    }


def responder(preparado, modelo=None):
    """Passo 4: envia à IA configurada (ver ia.py). Pode levantar os erros de ia.py."""
    import ia  # só carrega a IA quando for mesmo perguntar (a pergunta pronta não precisa)
    provedor = ia.obter_provedor(modelo)
    if not preparado["trechos"]:
        return "Não encontrei a resposta nos trechos das normas consultados. (Nenhum trecho foi encontrado.)"
    return provedor.responder(preparado["instrucoes"], preparado["mensagem"])


def main():
    parser = argparse.ArgumentParser(description="Pergunta à IA com base nas normas.")
    parser.add_argument("pergunta")
    parser.add_argument("--pronta", action="store_true", help="só mostra a pergunta pronta (sem IA)")
    parser.add_argument("--todas", action="store_true", help="inclui revogadas e futuras")
    parser.add_argument("--modelo", help="modelo só desta vez (ex.: gemini-3.8-flash)")
    args = parser.parse_args()

    conexao = busca.conectar()
    preparado = preparar(conexao, args.pergunta, args.todas)
    if args.pronta:
        print(preparado["pergunta_pronta"])
        return
    import ia
    try:
        print(responder(preparado, args.modelo))
    except ia.ErroIA as erro:
        sys.exit(f"ERRO: {erro}")
    for aviso in preparado["avisos"]:
        print(f"\nAVISO: {aviso}")
    print("\nTrechos usados:")
    for i, t in enumerate(preparado["trechos"], start=1):
        print(f"  {rotulo_trecho(i, t)}")


if __name__ == "__main__":
    main()
