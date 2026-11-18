# Normas CBMPR — Memória do Projeto

## Objetivo

Criar uma ferramenta web para **buscar e consultar a legislação de prevenção de incêndios** do Corpo de Bombeiros Militar do Paraná (CBMPR).

**Problema atual:** as normas estão em PDFs no site do CBMPR (leis, decretos, portarias, Código de Segurança Contra Incêndio e Pânico — CSCIP, orientações técnicas, Normas de Procedimento Administrativo — NPA, e Normas de Procedimento Técnico — NPT). Para consultar, é preciso abrir PDF por PDF.

**Solução:** um único lugar onde se pesquisa em todas as normas de uma vez.

## Funcionalidades

- **Busca unificada:** pesquisar em todos os PDFs ao mesmo tempo.
- **Filtros:** por tipo de norma (lei, decreto, portaria, CSCIP, NPA, NPT, orientação técnica) e por número.
- **Ordenação** dos resultados.
- **Trecho encontrado** exibido com a indicação de **norma, versão, item e página**.
- **Login individual**, com **histórico de buscas e consultas** de cada usuário.
- **Chat com IA** que responde **apenas com base nas normas**, sempre **citando a fonte** (norma, versão, item, página).
- **Botão "pergunta pronta":** monta um texto com a pergunta e os trechos relevantes para o usuário copiar e colar em qualquer IA.

## Tecnologias

| Item | Escolha |
|---|---|
| Linguagem | Python |
| Interface | Streamlit |
| Banco de dados | Supabase (PostgreSQL com busca de texto em português) |
| Login e histórico | Supabase |
| IA | Plugável — trocar de provedor deve exigir só mudar a configuração. Começar com **Google Gemini (plano gratuito)** |
| Leitura de PDFs | pdfplumber (a confirmar no Python 3.15) |
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
4. **Pequenas etapas testáveis:** executar **uma etapa por vez** e **parar ao final de cada uma** para o dono testar antes de seguir.
5. **Commits:** ao final de cada etapa testada, fazer um commit e atualizar a "Situação atual".

## Normas e versões

- **O que entra (baixar e indexar):** versões vigentes, futuras (ainda não vigentes) e revogadas/anteriores, de leis, decretos, portarias (ex.: Portaria 476/2025), CSCIP, NPA, NPT e orientações técnicas.
- **Consultas públicas:** não baixar. Ficam só no catálogo, com `baixar = não`.
- **Cada versão** tem data de **início** e de **fim de vigência** e, quando houver, a indicação de **qual versão a substituiu**. Motivo: edificações antigas, existentes e novas podem seguir legislações diferentes, então é preciso filtrar "normas vigentes em uma data".
- **A situação é calculada pelas datas**, e não digitada (vigente / futura / revogada / consulta_publica). Uma norma futura passa a vigente sozinha quando chega a data.
- **Cuidado:** a data que aparece no link do PDF (ex.: `/2026-08/`) é a data do envio ao site, **não** a da versão.

### Catálogo (`dados/catalogo.csv`)

- **Uma linha por versão** de norma (um PDF).
- Usa `;` como separador e UTF-8 com BOM, para abrir certo no Excel em português.
- Colunas: `id`, `norma_id`, `tipo`, `numero`, `parte`, `titulo`, `versao`, `vigencia_inicio`, `vigencia_fim`, `substituida_por`, `situacao`, `baixar`, `link_origem`, `arquivo_local`, `hash_sha256`, `tamanho_bytes`, `paginas`, `precisa_ocr`, `data_download`, `ultima_verificacao`, `revisado`, `observacao`.
- Formatos: `id` como `npt-022_2026-11` e `norma_id` como `npt-022`. Datas em `AAAA-MM-DD`. `vigencia_fim` vazio quer dizer "ainda em vigor".
- `revisado = sim` quer dizer que o dono conferiu a linha. Os programas **nunca sobrescrevem** linhas revisadas.
- A data geral da última verificação do site fica em `dados/estado.json`.

### Organização das pastas

```
dados/
  catalogo.csv     ← vai para o GitHub
  estado.json      ← vai para o GitHub (data da última verificação)
  sinonimos.csv    ← vai para o GitHub
  fontes/          ← páginas do site salvas no navegador (fora do GitHub)
  pdfs/<tipo>/<id>.pdf   ← fora do GitHub (cscip, leis, decretos, portarias, npa, npt, ot)
  texto/<id>.jsonl ← texto extraído (decidir na Etapa 8 se vai para o GitHub)
scripts/           ← programas da Fase 1
```

## Como o aplicativo trata as versões (regras para as fases futuras)

- **Por padrão**, a busca mostra **só as normas vigentes**.
- **Filtros:** "incluir versões anteriores" e "vigentes em [data]".
- **Revogadas:** selo vermelho **REVOGADA**, com o período de vigência e um link para a versão substituta.
- **Futuras:** aviso de **"ainda não vigente"**, com a data de início.
- **Chat com IA:** diz sempre qual versão está citando e **alerta** quando o trecho vier de norma revogada.

## Atualização automática

- **Objetivo:** a ferramenta se mantém atualizada. Um "atualizador" compara a lista do site com o catálogo, detecta normas **novas, alteradas e revogadas**, baixa **só o que mudou** e grava a **data da última verificação**.
- **Como detecta mudanças:**
  - links novos ou que sumiram da página;
  - mudança no `hash_sha256`, a "impressão digital" do conteúdo, que revela um PDF trocado no mesmo link (opção `--reverificar`).
- **Primeiro, modo semiautomático:**
  1. o dono salva a página no navegador;
  2. roda `listar_normas.py`;
  3. revisa as linhas novas;
  4. roda `baixar_pdfs.py`.
- **Depois, GitHub Actions** (rodar sozinho na nuvem). **Limitação conhecida:** a página de legislação bloqueia programas (erro 403) e provavelmente vai bloquear o GitHub também. Os PDFs não são bloqueados.
- **O aplicativo mostra** a data da última verificação.

## Extração do texto (segunda parte da Fase 1)

- **Hierarquia:** guardar o número de cada item e o item "pai", para mostrar cada trecho com o seu contexto. São duas estruturas:
  - **NPTs e CSCIP:** numeração decimal, `5 > 5.1 > 5.1.3 > 5.1.3.2.1`. O pai é obtido tirando o último número. Anexos com letras: `A`, `A.1`.
  - **Leis, decretos, NPAs e portarias:** `Capítulo > Seção > Art. > § > inciso > alínea`.
- **Tabelas:** muitas exigências estão em tabelas (ex.: as tabelas de exigências do CSCIP). Cada tabela é guardada de duas formas: em linhas e colunas, para mostrar na tela, e como texto "linha → coluna: valor", para a busca. Toda tabela fica marcada para conferência. **Limitações:**
  - células mescladas;
  - tabelas que continuam em várias páginas;
  - páginas giradas;
  - notas de tabela;
  - tabelas sem linhas desenhadas.
- **Referências cruzadas:** reconhecer citações a outras normas (ex.: "conforme NPT 003", "item 8.1 da NPT 002", "Lei nº …") e guardá-las como (norma, item), para virarem links no aplicativo.
- **Página:** guardar a página do PDF de cada trecho, para o link oficial abrir direto nela (`#page=N`). É a página do arquivo, que pode ser diferente do número impresso na folha.
- **Cabeçalhos e rodapés** que se repetem em todas as páginas são removidos.
- **PDFs escaneados:** detectar as páginas quase sem texto e marcar `precisa_ocr = sim` no catálogo. O OCR em si fica para depois.
- **Sinônimos:** `dados/sinonimos.csv` (`termo;equivalentes`, com os equivalentes separados por `|`), para o dono completar. A NPT 003 (Terminologia) serve de fonte.

## Fases do projeto

1. **Extração:** baixar os PDFs e extrair o texto, separado por norma, versão, item e página. Etapas:
   - **0.** Registrar as decisões, criar o `sinonimos.csv` e ajustar o `.gitignore`.
   - **1.** O dono salva as páginas de legislação do site em `dados/fontes/`.
   - **2.** `scripts/listar_normas.py` monta e atualiza o catálogo. `scripts/conferir_catalogo.py` aponta os problemas.
   - **3.** O dono revisa o catálogo.
   - **4.** `scripts/baixar_pdfs.py` baixa os PDFs, com hash e opção `--reverificar`.
   - **5.** Completar as datas de vigência e as substituições, com sugestões tiradas da primeira página dos PDFs.
   - **6.** Criar o ambiente virtual `.venv` e testar o pdfplumber no Python 3.15.
   - **7.** `scripts/diagnosticar_pdfs.py` conta as páginas e detecta os PDFs escaneados.
   - **8.** Texto e hierarquia. Testes com a NPT 003, uma NPT curta e a NPA 002.
   - **9.** Tabelas, com teste nas tabelas do CSCIP.
   - **10.** Referências cruzadas.
   - **11.** Rodar em todos os PDFs e gerar um relatório.
2. **Banco e busca:** criar o banco de dados no Supabase e implementar a busca de texto em português.
3. **Interface:** tela no Streamlit com busca, filtros (incluindo versões e data de vigência) e ordenação.
4. **Login e histórico:** autenticação de usuários e registro de buscas e consultas.
5. **Publicação:** colocar a ferramenta online.
6. **Chat com IA:** chat que responde só com base nas normas, citando a fonte e a versão, e o botão de "pergunta pronta".

## Ideias futuras

- **Aviso:** a ferramenta **não é oficial**; a fonte oficial é o site do CBMPR.
- **Comparação entre versões** de uma mesma norma.
- **Botão de citação pronta** para relatórios e pareceres.
- **Gabarito de perguntas reais** para testar a busca e a IA.
- **Histórico do usuário com opção de apagar** (LGPD).
- **Interface boa no celular.**

## Situação atual

- Repositório Git criado (ramo `main`), com identidade local `cauegaffo` (e-mail privado do GitHub).
- **Site do CBMPR:**
  - a página de legislação **bloqueia programas** (erro 403), por isso o dono a salva manualmente no navegador;
  - os **links diretos dos PDFs funcionam** em programas;
  - a página existe em dois endereços, cujas listas podem ser diferentes:
    - https://www.bombeiros.pr.gov.br/Pagina/Legislacao-de-Prevencao-e-Combate-Incendios-e-Desastres
    - https://www.bombeiros.pr.gov.br/PrevFogo/Pagina/Legislacao-de-Prevencao-e-Combate-Incendios-e-Desastres
- **Fase 1, Etapa 0 concluída.** Próximo passo: **Etapa 1** (o dono salva as páginas em `dados/fontes/`).
