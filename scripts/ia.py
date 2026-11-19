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
    IA_MODELO_RESERVA=gemini-3.6-flash   (usado uma vez se o principal estiver sobrecarregado
                                          ou no limite por minuto; opcional)
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


class ErroSobrecarga(ErroIA):
    """O modelo está sobrecarregado ou indisponível no provedor (erros 500 a 504)."""


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def carregar_configuracao():
    """Lê o .env (se existir) para as variáveis de ambiente e devolve provedor e modelo."""
    load_dotenv(ARQUIVO_ENV, override=False)
    provedor = (os.getenv("IA_PROVEDOR") or "gemini").strip().lower()
    modelo = (os.getenv("IA_MODELO") or "").strip()
    return provedor, modelo


def modelo_reserva():
    """Modelo reserva do .env (IA_MODELO_RESERVA), ou "" se não houver."""
    load_dotenv(ARQUIVO_ENV, override=False)
    return (os.getenv("IA_MODELO_RESERVA") or "").strip()


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


def _vale_tentar_reserva(erro):
    """Só sobrecarga (500 a 504) e limite POR MINUTO levam ao modelo reserva.
    Limite diário, chave inválida e modelo inexistente, não."""
    return isinstance(erro, ErroSobrecarga) or (isinstance(erro, ErroLimite) and erro.tipo == "por_minuto")


def responder_com_reserva(instrucoes, mensagem, modelo=None, usar_reserva=True):
    """Pergunta ao modelo principal. Se ele der sobrecarga ou limite por minuto, tenta UMA vez
    no modelo reserva (IA_MODELO_RESERVA). Devolve um dicionário:
      texto, modelo (o que respondeu), usou_reserva (True/False), motivo (por que usou a reserva).
    """
    provedor = obter_provedor(modelo)
    try:
        return {"texto": provedor.responder(instrucoes, mensagem), "modelo": provedor.modelo,
                "usou_reserva": False, "motivo": ""}
    except ErroIA as erro:
        reserva = modelo_reserva()
        if not (usar_reserva and reserva and reserva != provedor.modelo and _vale_tentar_reserva(erro)):
            raise
        motivo = "sobrecarregado" if isinstance(erro, ErroSobrecarga) else "no limite por minuto"
        principal = provedor.modelo
    try:
        provedor_reserva = obter_provedor(reserva)
        texto = provedor_reserva.responder(instrucoes, mensagem)
    except ErroIA as erro_reserva:
        nova = type(erro_reserva)(
            f'O modelo principal "{principal}" estava {motivo}, e o modelo reserva "{reserva}" '
            f"também falhou: {erro_reserva}")
        if isinstance(erro_reserva, ErroLimite):
            nova.tipo = erro_reserva.tipo
        raise nova from None
    return {"texto": texto, "modelo": reserva, "usou_reserva": True,
            "motivo": f'o modelo principal "{principal}" estava {motivo}'}


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
        "modelo_reserva": modelo_reserva(),
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
