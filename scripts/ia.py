"""
Parte "plugável" da IA: escolhe o provedor pela configuração e define os erros comuns.

Este arquivo não sabe nada do Gemini. Cada provedor fica num arquivo próprio
(ex.: ia_gemini.py) com uma classe Provedor que tem o método responder(instrucoes, mensagem).

Para trocar de provedor:
1. crie scripts/ia_<nome>.py com a classe Provedor (veja ia_gemini.py como modelo);
2. acrescente a linha "<nome>": "ia_<nome>" em PROVEDORES, abaixo;
3. mude IA_PROVEDOR (e IA_MODELO) no arquivo .env.

A configuração vem do arquivo .env (que NUNCA vai para o GitHub):
    IA_PROVEDOR=gemini
    IA_MODELO=gemini-3.5-flash-lite
    GEMINI_API_KEY=...        (a chave: este programa nunca a mostra nem a grava em lugar nenhum)
"""

import importlib
import os

from dotenv import load_dotenv

from catalogo import PASTA_PROJETO

ARQUIVO_ENV = PASTA_PROJETO / ".env"

# nome no .env -> arquivo (módulo) do provedor
PROVEDORES = {
    "gemini": "ia_gemini",
}


# ---------------------------------------------------------------------------
# Erros comuns a todos os provedores (cada um traz uma mensagem clara em português)
# ---------------------------------------------------------------------------

class ErroIA(Exception):
    """Erro genérico da IA."""


class ErroChaveAusente(ErroIA):
    """Não há chave configurada no .env."""


class ErroChaveInvalida(ErroIA):
    """A chave foi recusada pelo provedor (inválida, expirada ou sem permissão)."""


class ErroLimite(ErroIA):
    """Limite do plano gratuito atingido. tipo = "por_minuto" ou "diario"."""

    def __init__(self, mensagem, tipo="por_minuto"):
        super().__init__(mensagem)
        self.tipo = tipo


class ErroModelo(ErroIA):
    """O modelo configurado não existe ou não está disponível."""


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def carregar_configuracao():
    """Lê o .env (se existir) para as variáveis de ambiente e devolve provedor e modelo."""
    load_dotenv(ARQUIVO_ENV, override=False)
    provedor = (os.getenv("IA_PROVEDOR") or "gemini").strip().lower()
    modelo = (os.getenv("IA_MODELO") or "").strip()
    return provedor, modelo


def _modulo(provedor):
    if provedor not in PROVEDORES:
        raise ErroIA(f'Provedor de IA "{provedor}" desconhecido. Opções: {", ".join(PROVEDORES)}. '
                     "Confira IA_PROVEDOR no arquivo .env.")
    return importlib.import_module(PROVEDORES[provedor])


def obter_provedor(modelo=None):
    """Cria o provedor configurado. 'modelo' troca o modelo só nesta vez (sem mexer no .env)."""
    provedor, modelo_configurado = carregar_configuracao()
    modulo = _modulo(provedor)
    return modulo.Provedor(modelo=modelo or modelo_configurado or modulo.MODELO_PADRAO)


def status():
    """Situação da configuração, para mostrar na tela. NUNCA inclui a chave:
    só diz se ela existe (tem_chave = True/False)."""
    provedor, modelo = carregar_configuracao()
    try:
        modulo = _modulo(provedor)
    except ErroIA as erro:
        return {"provedor": provedor, "nome": provedor, "modelo": modelo, "tem_chave": False,
                "erro": str(erro)}
    return {
        "provedor": provedor,
        "nome": modulo.NOME,
        "modelo": modelo or modulo.MODELO_PADRAO,
        "tem_chave": bool((os.getenv(modulo.VARIAVEL_CHAVE) or "").strip()),
        "variavel_chave": modulo.VARIAVEL_CHAVE,
        "erro": None,
    }


def esconder_segredo(texto, segredo):
    """Troca o valor da chave por *** em qualquer texto (ex.: mensagens de erro)."""
    texto = str(texto)
    if segredo:
        texto = texto.replace(segredo, "***")
    return texto
