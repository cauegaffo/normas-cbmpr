"""
Protótipo, Passo 5 — Tela de busca nas normas do CBMPR (Streamlit).

Como abrir (no PowerShell, dentro da pasta do projeto):
    .\\.venv\\Scripts\\python.exe -m streamlit run app.py

A busca usa o arquivo dados/busca.sqlite, montado pelo scripts/indexar.py.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Os programas ficam na pasta scripts/: é de lá que vem a função de busca.
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import busca  # noqa: E402

LIMITE = 50
MAX_BOTOES = 12          # normas mostradas como botões; as demais vão para "Outras normas"
NENHUMA = "__nenhuma__"  # opção vazia da lista "Outras normas"
SITE_OFICIAL = "https://www.bombeiros.pr.gov.br/Prevencao"
ORDEM_TIPOS = list(busca.NOMES_TIPOS)

# Marcas que vão em volta das palavras encontradas. São caracteres "invisíveis",
# trocados por negrito só depois de proteger o texto (ver formatar_trecho).
MARCA_INICIO, MARCA_FIM = "\x02", "\x03"


def data_br(texto):
    """'2026-11-18T18:56' -> '18/11/2026 às 18:56'; '2026-11-05' -> '05/11/2026'."""
    if not texto:
        return "—"
    try:
        if "T" in texto:
            return datetime.fromisoformat(texto).strftime("%d/%m/%Y às %H:%M")
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y")
    except ValueError:
        return texto


def formatar_trecho(trecho):
    """Protege caracteres que o Streamlit trataria como formatação (ex.: "R$" viraria
    fórmula, "*" viraria itálico) e põe em negrito as palavras encontradas."""
    trecho = " ".join(trecho.split())
    trecho = re.sub(r"([\\`*_{}\[\]<>()#+\-.!|$~])", r"\\\1", trecho)
    return trecho.replace(MARCA_INICIO, "**").replace(MARCA_FIM, "**")


def nomes_das_versoes(conexao, ids):
    """Nomes legíveis das versões substitutas, ex.: 'NPT 028 Parte 1 (2027-04)'."""
    nomes = []
    for versao_id in ids:
        linha = conexao.execute("SELECT * FROM normas WHERE id = ?", (versao_id,)).fetchone()
        if linha:
            nome = busca.nome_norma(linha)
            nomes.append(f"{nome} ({linha['versao']})" if linha["versao"] else nome)
        else:
            nomes.append(versao_id)
    return nomes


def selo_situacao(r):
    """Texto colorido com a situação da versão."""
    if r["situacao"] == "revogada":
        if r["vigencia_inicio"]:
            periodo = f"vigência: {data_br(r['vigencia_inicio'])} a {data_br(r['vigencia_fim'])}"
        else:
            periodo = f"vigente até {data_br(r['vigencia_fim'])}"
        return f":red-badge[REVOGADA] {periodo}"
    if r["situacao"] == "futura":
        return f":orange-badge[AINDA NÃO VIGENTE] começa a valer em {data_br(r['vigencia_inicio'])}"
    return ":green-badge[vigente]"


def chave_por_norma(r):
    tipo = ORDEM_TIPOS.index(r["tipo"]) if r["tipo"] in ORDEM_TIPOS else len(ORDEM_TIPOS)
    return (tipo, r["numero"].zfill(6), r["parte"].zfill(3), r["versao"], r["pagina"] or 0)


def mostrar_resultado(conexao, r):
    with st.container(border=True):
        versao = f" — versão {r['versao']}" if r["versao"] else ""
        st.markdown(f"**{r['norma']}**{versao} · {selo_situacao(r)}")
        st.caption(r["titulo"])

        local = f"Item **{r['item']}**"
        if r["pagina"]:
            local += f" · página **{r['pagina']}**"
        st.markdown(local)
        st.markdown(formatar_trecho(r["trecho"]))

        if r["situacao"] == "revogada" and r["substituida_por"]:
            substitutas = nomes_das_versoes(conexao, r["substituida_por"].split("|"))
            st.markdown(f"Substituída por: {', '.join(substitutas)}")

        coluna_texto, coluna_link = st.columns([3, 2])
        with coluna_texto.expander("Ver o trecho completo"):
            st.text(r["texto"])
        if r["link"]:
            rotulo = f"Abrir o PDF oficial na página {r['pagina']}" if r["pagina"] \
                else "Abrir o texto oficial"
            coluna_link.link_button(rotulo, r["link"])


def rotulo_norma(n):
    versao = f" ({n['versao']})" if n["versao"] else ""
    return f"{n['norma']}{versao}"


def mostrar_resumo_normas(resultado, chave_filtro, chave_botoes, chave_outras):
    """Resumo "Normas encontradas": botões para as 12 primeiras e uma lista para as demais.
    É um filtro só: escolher num lugar limpa o outro."""
    normas = resultado["normas"]
    principais, outras = normas[:MAX_BOTOES], normas[MAX_BOTOES:]
    rotulos = {n["id"]: f"{rotulo_norma(n)} · {n['quantidade']} trecho(s)" for n in normas}

    def escolheu_botao():
        st.session_state[chave_filtro] = st.session_state.get(chave_botoes)
        if outras:
            st.session_state[chave_outras] = NENHUMA

    def escolheu_outra():
        valor = st.session_state.get(chave_outras)
        st.session_state[chave_filtro] = None if valor == NENHUMA else valor
        st.session_state[chave_botoes] = None

    parcial = " (contagem parcial: busca muito ampla)" if resultado["limitado"] else ""
    st.markdown(f"**Normas encontradas:** {len(normas)}{parcial}. Clique numa norma para ver só os "
                "trechos dela; clique de novo para ver todas.")
    st.pills(
        "Normas encontradas", options=[n["id"] for n in principais], format_func=rotulos.get,
        selection_mode="single", key=chave_botoes, on_change=escolheu_botao,
        label_visibility="collapsed",
    )
    if outras:
        opcoes = [NENHUMA] + [n["id"] for n in outras]
        st.selectbox(
            f"Outras normas ({len(outras)})", options=opcoes,
            format_func=lambda i: "(nenhuma)" if i == NENHUMA else rotulos[i],
            key=chave_outras, on_change=escolheu_outra,
        )


def main():
    st.set_page_config(page_title="Normas CBMPR — busca", page_icon="🔥", layout="wide")
    st.title("Busca nas normas de prevenção do CBMPR")

    try:
        conexao = busca.conectar()
    except FileNotFoundError as erro:
        st.error(str(erro))
        st.stop()
    info = busca.ler_info(conexao)

    # --- Avisos ---------------------------------------------------------------
    st.warning(
        f"**Ferramenta não oficial, em fase de protótipo.** A fonte oficial é o "
        f"[site do CBMPR]({SITE_OFICIAL}). Confira sempre o texto no documento oficial."
    )
    total = int(info.get("total_normas", 0))
    revisadas = int(info.get("total_revisadas", 0))
    if revisadas < total:
        st.warning(
            f"**Catálogo ainda não revisado** ({revisadas} de {total} versões conferidas). "
            "As datas de vigência estão incompletas: normas sem data aparecem como vigentes. "
            "A divisão em itens pode errar, e o texto de tabelas pode sair misturado."
        )
    st.caption(
        f"Última verificação do site: {data_br(info.get('ultima_verificacao'))} · "
        f"Índice montado em: {data_br(info.get('indexado_em'))} · "
        f"{int(info.get('total_trechos', 0)):,} trechos".replace(",", ".")
    )

    # --- Busca e filtros --------------------------------------------------------
    texto = st.text_input("O que você procura?", placeholder='ex.: saída de emergência  ou  "rota de fuga"')
    coluna1, coluna2, coluna3 = st.columns([3, 2, 2])
    tipos = coluna1.multiselect(
        "Tipo de norma", options=ORDEM_TIPOS, format_func=lambda t: busca.NOMES_TIPOS[t],
        placeholder="Todos os tipos",
    )
    ordem = coluna2.radio("Ordenar por", ["Relevância", "Norma"], horizontal=True)
    incluir_todas = coluna3.checkbox("Incluir revogadas e futuras", value=False)
    usar_sinonimos = coluna3.checkbox("Usar sinônimos", value=True)

    if not texto.strip():
        st.info("Digite uma ou mais palavras. A busca ignora acentos e aceita o começo "
                "da palavra (ex.: **hidrant** acha *hidrante* e *hidrantes*). "
                'Use aspas para uma frase exata (ex.: **"saída de emergência"**). '
                "Com **Usar sinônimos**, a busca também procura termos equivalentes "
                "(ex.: *sprinkler* = *chuveiros automáticos*), com peso menor.")
        return

    # Filtro por norma: guardado com uma chave que depende da busca. Mudou o texto, os
    # sinônimos, "revogadas e futuras" ou os tipos? A chave muda e o filtro volta para "todas".
    chave = repr((texto.strip(), usar_sinonimos, incluir_todas, sorted(tipos)))
    chave_filtro, chave_botoes, chave_outras = (f"filtro|{chave}", f"botoes|{chave}", f"outras|{chave}")
    filtro = st.session_state.get(chave_filtro)

    def pesquisar(versao_id):
        return busca.buscar(conexao, texto, tipos, incluir_todas, LIMITE,
                            marca_inicio=MARCA_INICIO, marca_fim=MARCA_FIM,
                            usar_sinonimos=usar_sinonimos, versao_id=versao_id)

    resultado = pesquisar(filtro)
    ids_no_resumo = [n["id"] for n in resultado["normas"]]
    if filtro and filtro not in ids_no_resumo:
        # A norma escolhida não está mais no resumo: volta para "todas", sem erro.
        filtro = None
        st.session_state[chave_filtro] = None
        resultado = pesquisar(None)

    for digitado, sinonimos in resultado["sinonimos_usados"].items():
        st.caption(f"Sinônimos usados: **{digitado}** → {', '.join(sinonimos)}")

    if not resultado["normas"]:
        dica = "" if incluir_todas else " Tente marcar **Incluir revogadas e futuras**."
        st.info(f"Nenhum trecho encontrado.{dica}")
        return

    mostrar_resumo_normas(resultado, chave_filtro, chave_botoes, chave_outras)

    trechos = resultado["trechos"]
    if ordem == "Norma":
        trechos.sort(key=chave_por_norma)
    aviso_limite = f" (os {LIMITE} mais relevantes)" if len(trechos) == LIMITE else ""
    if filtro:
        norma = next(n for n in resultado["normas"] if n["id"] == filtro)
        st.subheader(f"{len(trechos)} trecho(s) de {rotulo_norma(norma)}{aviso_limite}")
    else:
        st.subheader(f"{len(trechos)} trecho(s) encontrado(s){aviso_limite}")
    for r in trechos:
        mostrar_resultado(conexao, r)


main()
