"""
Provedor de IA: Google Gemini (biblioteca oficial google-genai, Interactions API).

Conferido na documentação oficial (aistudio.google.com/docs, 18/11/2026):
- biblioteca: google-genai  ->  from google import genai
- chamada:    client.interactions.create(model=..., system_instruction=..., input=...)
- resposta:   interaction.output_text
- os modelos 3.6 em diante ignoram "temperature", por isso não usamos.
- erros: 401 chave inválida; 403 sem permissão; 404 modelo não encontrado;
         429 limite (rate_limit_exceeded = por minuto; quota_exceeded = do dia).
"""

import os

from google import genai
from google.genai import errors, types

# A Interactions API tem exceções próprias (conferido na google-genai 3.6.1): APIStatusError
# (com status_code e body), APIConnectionError e APITimeoutError. Na prática, uma chave inválida
# volta como 400 com "API_KEY_INVALID" (e não 401, como diz a documentação).
try:
    from google.genai import _interactions_errors as erros_interactions
except ImportError:  # versões da biblioteca sem a Interactions API
    erros_interactions = None

ERROS_DE_STATUS = tuple(e for e in (errors.APIError, getattr(erros_interactions, "APIStatusError", None)) if e)
ERROS_DE_CONEXAO = tuple(e for e in (getattr(erros_interactions, "APIConnectionError", None),) if e)

from ia import (ErroChaveAusente, ErroChaveInvalida, ErroIA, ErroLimite, ErroModelo,
                esconder_segredo)

NOME = "Google Gemini"
VARIAVEL_CHAVE = "GEMINI_API_KEY"
MODELO_PADRAO = "gemini-3.5-flash-lite"
TEMPO_LIMITE_MS = 120_000   # espera no máximo 2 minutos por uma resposta


class Provedor:
    def __init__(self, modelo=MODELO_PADRAO):
        self.modelo = modelo
        self._chave = (os.getenv(VARIAVEL_CHAVE) or "").strip()
        if not self._chave:
            raise ErroChaveAusente(
                "Nenhuma chave do Gemini configurada. Crie o arquivo .env a partir do "
                ".env.example e cole a sua chave em GEMINI_API_KEY.")
        # attempts=1: sem repetições automáticas. Assim, se o limite do plano gratuito for
        # atingido, a mensagem aparece na hora (a biblioteca repetiria até 4 vezes, por minutos).
        self._cliente = genai.Client(
            api_key=self._chave,
            http_options=types.HttpOptions(
                timeout=TEMPO_LIMITE_MS,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def responder(self, instrucoes, mensagem):
        """Envia as instruções e a mensagem e devolve o texto da resposta."""
        try:
            interacao = self._cliente.interactions.create(
                model=self.modelo, system_instruction=instrucoes, input=mensagem)
        except ERROS_DE_STATUS as erro:
            raise traduzir_erro(erro, self._chave, self.modelo) from None
        except ERROS_DE_CONEXAO:  # sem internet ou tempo esgotado (APITimeoutError é um caso dele)
            raise ErroIA("Não consegui falar com o Google (sem conexão ou tempo esgotado). "
                         "Confira a internet e tente de novo.") from None
        except Exception as erro:  # qualquer outro problema
            detalhe = esconder_segredo(type(erro).__name__, self._chave)
            raise ErroIA(f"Não consegui falar com o Google ({detalhe}). "
                         "Confira a conexão com a internet e tente de novo.") from None
        texto = (getattr(interacao, "output_text", None) or "").strip()
        if not texto:
            raise ErroIA("O Gemini devolveu uma resposta vazia. Tente de novo.")
        return texto


def traduzir_erro(erro, chave, modelo):
    """Transforma o erro da biblioteca do Google num dos erros comuns (ia.py),
    com mensagem clara e SEM a chave."""
    if isinstance(getattr(erro, "status_code", None), int):   # exceções da Interactions API
        codigo = erro.status_code
        bruto = f"{getattr(erro, 'message', '')} {getattr(erro, 'body', '')}"
    else:                                                       # google.genai.errors.APIError
        codigo = erro.code if isinstance(erro.code, int) else None
        bruto = f"{erro.status} {erro.message} {erro.details}"
    detalhes = esconder_segredo(bruto, chave).lower()

    if codigo == 401 or "api_key_invalid" in detalhes or "api key not valid" in detalhes \
            or (codigo == 400 and "api key" in detalhes):
        return ErroChaveInvalida(
            "A chave do Gemini foi recusada (inválida ou expirada). Confira a chave em "
            "https://aistudio.google.com/apikey e corrija o GEMINI_API_KEY no arquivo .env.")
    if codigo == 403:
        # Em 18/11/2026 um 403 apareceu numa pergunta e sumiu ao repetir (falha passageira),
        # com a mesma chave funcionando nas outras. Por isso a mensagem sugere tentar de novo.
        return ErroChaveInvalida(
            "O Google negou o acesso (403). Se outras perguntas funcionaram, pode ser uma falha "
            "passageira: tente de novo. Se continuar, a chave pode ter sido bloqueada ou o projeto "
            "restrito: confira em https://aistudio.google.com/apikey.")
    if codigo == 429:
        # Limite do dia aparece como "quota_exceeded" (Interactions API) ou como uma cota
        # "...PerDay..." / "..._per_day" nos detalhes. O resto é limite por minuto.
        diario = any(marca in detalhes for marca in ("quota_exceeded", "per day", "perday", "per_day"))
        if diario:
            return ErroLimite(
                "Limite DIÁRIO do plano gratuito atingido. Ele renova à meia-noite do horário "
                "do Pacífico (por volta das 5h de Brasília). Enquanto isso, use o botão "
                '"Copiar pergunta pronta" e cole numa IA de sua escolha.', tipo="diario")
        return ErroLimite(
            "Limite POR MINUTO do plano gratuito atingido. Espere cerca de 1 minuto e tente "
            'de novo, ou use o botão "Copiar pergunta pronta".', tipo="por_minuto")
    if codigo == 404:
        return ErroModelo(
            f'O modelo "{modelo}" não foi encontrado. Confira o IA_MODELO no arquivo .env '
            "(ex.: gemini-3.5-flash-lite).")
    if codigo in (500, 502, 503, 504):
        # Ex. real (18/11/2026): 503 "gemini-3.8-flash is currently experiencing high demand".
        return ErroIA(
            f'O modelo "{modelo}" está sobrecarregado ou indisponível no Google neste momento '
            f"({codigo}). Isso costuma ser passageiro: tente de novo em alguns minutos, troque o "
            'IA_MODELO no .env ou use o botão "Copiar pergunta pronta".')
    return ErroIA(f"O Gemini devolveu um erro ({codigo or 'sem código'}). Tente de novo mais tarde.")
