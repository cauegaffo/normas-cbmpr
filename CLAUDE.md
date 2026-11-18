# Normas CBMPR — Memória do Projeto

## Objetivo

Criar uma ferramenta web para **buscar e consultar a legislação de prevenção de incêndios** do Corpo de Bombeiros Militar do Paraná (CBMPR).

**Problema atual:** as normas estão em PDFs no site do CBMPR (leis, decretos, orientações técnicas, Normas de Procedimento Administrativo — NPA, e Normas de Procedimento Técnico — NPT). Para consultar, é preciso abrir PDF por PDF.

**Solução:** um único lugar onde se pesquisa em todas as normas de uma vez.

## Funcionalidades

- **Busca unificada:** pesquisar em todos os PDFs ao mesmo tempo.
- **Filtros:** por tipo de norma (lei, decreto, orientação técnica, NPA, NPT) e por número.
- **Ordenação** dos resultados.
- **Trecho encontrado** exibido com a indicação de **norma, item e página**.
- **Login individual**, com **histórico de buscas e consultas** de cada usuário.
- **Chat com IA** que responde **apenas com base nas normas**, sempre **citando a fonte** (norma, item, página).
- **Botão "pergunta pronta":** monta um texto com a pergunta e os trechos relevantes para o usuário copiar e colar em qualquer IA.

## Tecnologias

| Item | Escolha |
|---|---|
| Linguagem | Python |
| Interface | Streamlit |
| Banco de dados | Supabase (PostgreSQL com busca de texto em português) |
| Login e histórico | Supabase |
| IA | Plugável — trocar de provedor deve exigir só mudar a configuração. Começar com **Google Gemini (plano gratuito)** |
| Versionamento e publicação | Git e GitHub |

**Chave da IA:** cada usuário cadastra a própria chave do Gemini. Ela fica **criptografada** no banco e **nunca é exibida novamente** depois de salva.

## Ambiente

- Sistema operacional: **Windows 11**
- Terminal: **PowerShell**. Todos os comandos sugeridos devem funcionar no PowerShell (não usar sintaxe de Linux/bash).
- **Python 3.15** instalado
- **Git** instalado
- **VS Code** instalado

## Regras de trabalho

1. **Segredos fora do código:** nunca colocar chaves, senhas ou segredos no código nem no GitHub. Usar arquivos de configuração locais ignorados pelo Git (ex.: `.env`, `.streamlit/secrets.toml`) e listá-los no `.gitignore`.
2. **Explicar antes de fazer:** o dono do projeto está aprendendo a programar. Antes de cada passo, explicar em **português simples** o que será feito e por quê.
3. **Simplicidade:** preferir sempre a solução mais simples que resolva o problema.
4. **Pequenas etapas testáveis:** avançar aos poucos, e cada etapa deve poder ser testada antes de seguir para a próxima.

## Fases do projeto

1. **Extração:** baixar os PDFs do site do CBMPR e extrair o texto, separado por norma, item e página.
2. **Banco e busca:** criar o banco de dados no Supabase e implementar a busca de texto em português.
3. **Interface:** tela no Streamlit com busca, filtros e ordenação.
4. **Login e histórico:** autenticação de usuários e registro de buscas e consultas.
5. **Publicação:** colocar a ferramenta online.
6. **Chat com IA:** chat que responde só com base nas normas, citando a fonte, e o botão de "pergunta pronta".

## Situação atual

- Projeto iniciado. Nenhum código escrito ainda.
- Repositório Git criado (ramo `main`). O `.gitignore` protege segredos (`.env`, `.streamlit/secrets.toml`), ambientes virtuais (`.venv/`) e a pasta dos PDFs baixados.
- **Pasta dos PDFs baixados:** `dados/pdfs/` (não vai para o GitHub).
- Próximo passo: Fase 1 (extração dos PDFs).
