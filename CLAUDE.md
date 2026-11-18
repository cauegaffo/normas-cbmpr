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
6. **Idioma:** responder **sempre em português**, inclusive nas mensagens de progresso.

## Protótipo (prioridade atual)

**Decisão de 18/11/2026:** antes de completar a Fase 1, fazer um **protótipo local** para testar se a ferramenta é útil no dia a dia. **A revisão do catálogo (Etapa 3) e as etapas completas da Fase 1 ficam para depois do protótipo.** São elas: datas de vigência (Etapa 5), diagnóstico completo (7), hierarquia completa (8), tabelas (9), referências cruzadas (10) e relatório geral (11).

**Como é o protótipo:** roda só no computador do dono, **sem Supabase e sem login**. A busca usa um arquivo local SQLite com FTS5 (`dados/busca.sqlite`), que ignora acentos e aceita o começo da palavra.

**Passos (um por vez, parando para testar ao final de cada um):**
0. Registrar a decisão no `CLAUDE.md` e no `.gitignore`.
1. `scripts/baixar_pdfs.py`: baixa os PDFs para `dados/pdfs/<tipo>/<id>.pdf` e as leis e decretos para `dados/paginas/<id>.html`, e preenche no catálogo `arquivo_local`, `hash_sha256`, `tamanho_bytes` e `data_download`.
2. Ambiente virtual `.venv`, com pdfplumber e streamlit, registrados em `requirements.txt`. Os programas são rodados com `.\.venv\Scripts\python.exe`.
3. `scripts/extrair_texto.py`: gera `dados/texto/<id>.jsonl` com `versao_id`, `item`, `pagina` e `texto`.
   - Itens com numeração decimal (`5.1.3`) ou por artigo (`Art. 12`).
   - Um trecho por item e por página.
   - Marca `paginas` e `precisa_ocr` no catálogo.
4. `scripts/indexar.py`: monta `dados/busca.sqlite` (FTS5) a partir dos textos e do catálogo.
5. `app.py` (Streamlit), com:
   - aviso de **"catálogo ainda não revisado"** e de ferramenta não oficial;
   - data da última verificação;
   - busca, com filtro por tipo e caixa "incluir revogadas e futuras" (desmarcada por padrão);
   - resultados com norma, versão, situação, item, página e link para o PDF oficial em `#page=N`.

**Limitações conhecidas do protótipo:**
- O texto das tabelas sai misturado.
- PDFs escaneados não entram na busca (sem OCR).
- Cabeçalhos e rodapés podem aparecer nos trechos.
- A divisão em itens pode errar.
- A busca não entende variações além do começo da palavra e ainda não usa o `sinonimos.csv`.
- Leis e decretos ficam sem número de página.
- As datas de vigência estão incompletas: normas sem data aparecem como vigentes.

## Normas e versões

- **O que entra (baixar e indexar):** versões vigentes, futuras (ainda não vigentes) e revogadas/anteriores, de leis, decretos, portarias (ex.: Portaria 476/2025), CSCIP, NPA, NPT e orientações técnicas.
- **Consultas públicas:** ficam **de fora** (nem no catálogo).
- **Leis, decretos e resoluções** (ex.: Lei 19.449, Lei 13.976, Decreto 11.868, Resolução SESP 399/2020): não são PDF. O texto é capturado das páginas do site **legislacao.pr.gov.br** e a referência é **por artigo**, porque não há número de página.
- **Revogadas sem link** (ex.: NPT 001 Parte 2, NPT 004): entram no catálogo com situação **`pendente`** e sem link. Os arquivos serão procurados depois.
- **Cada versão** tem data de **início** e de **fim de vigência** e, quando houver, a indicação de **qual versão a substituiu**. Motivo: edificações antigas, existentes e novas podem seguir legislações diferentes, então é preciso filtrar "normas vigentes em uma data".
- **A situação é calculada pelas datas**, e não digitada (vigente / futura / revogada). A exceção é `pendente`: norma conhecida, mas ainda sem arquivo. Uma norma futura passa a vigente sozinha quando chega a data.
- **Cuidado:** a data que aparece no link do PDF (ex.: `/2026-08/`) é a data do envio ao site, **não** a da versão.

### Catálogo (`dados/catalogo.csv`)

- **Uma linha por versão** de norma (um PDF).
- Usa `;` como separador e UTF-8 com BOM, para abrir certo no Excel em português.
- Colunas: `id`, `norma_id`, `tipo`, `numero`, `parte`, `titulo`, `versao`, `vigencia_inicio`, `vigencia_fim`, `substituida_por`, `situacao`, `baixar`, `link_origem`, `arquivo_local`, `hash_sha256`, `tamanho_bytes`, `paginas`, `precisa_ocr`, `data_download`, `ultima_verificacao`, `no_site`, `revisado`, `observacao`. A lista oficial fica em `scripts/catalogo.py`.
- Tipos: `lei`, `decreto`, `resolucao`, `portaria`, `cscip`, `npa`, `npt`, `ot`.
- Formatos:
  - `id` como `npt-022_2015-03` (norma + versão AAAA-MM). Normas em partes usam `npt-015-p1_2012-01`.
  - `norma_id` como `npt-022`. Quando o número já inclui o ano, o `id` não repete o ano (ex.: `portaria-476-2025`, `ot-001-2013`).
  - `parte` guarda só o número da parte.
  - `substituida_por` aceita vários ids separados por `|`.
  - Datas em `AAAA-MM-DD`. `vigencia_fim` vazio quer dizer "ainda em vigor".
- `no_site = não` quer dizer que o link sumiu da página na última verificação.
- `revisado = sim` quer dizer que o dono conferiu a linha. Os programas **nunca sobrescrevem** linhas revisadas.
- A data geral da última verificação do site fica em `dados/estado.json`.

### Organização das pastas

```
dados/
  catalogo.csv     ← vai para o GitHub
  estado.json      ← vai para o GitHub (data da última verificação)
  sinonimos.csv    ← vai para o GitHub
  fontes/          ← plano B: página do site salva no navegador (fora do GitHub)
  pdfs/<tipo>/<id>.pdf   ← fora do GitHub (cscip, portarias, npa, npt, ot)
  paginas/<id>.html      ← leis, decretos e resoluções do legislacao.pr.gov.br (fora do GitHub)
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
  1. o dono roda `listar_normas.py`, que **baixa sozinho** a página https://www.bombeiros.pr.gov.br/Prevencao. **Plano B:** se o download falhar, o programa usa a página salva manualmente em `dados/fontes/legislacao.html`;
  2. revisa as linhas novas;
  3. roda `baixar_pdfs.py`.
- **Depois, GitHub Actions** (rodar sozinho na nuvem). Em 18/11/2026, a página `/Prevencao` **abriu normalmente para programas** (status 200), assim como os PDFs, então o GitHub Actions parece viável. Se o site passar a bloquear, volta-se a salvar a página manualmente em `dados/fontes/`.
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
   - **1.** Conferir a lista de links da página de legislação (feito em 18/11/2026).
   - **2.** `scripts/listar_normas.py` baixa a página, com o plano B da cópia manual, e monta e atualiza o catálogo, incluindo as leis, decretos e resoluções do legislacao.pr.gov.br e as linhas `pendente`. `scripts/conferir_catalogo.py` aponta os problemas.
   - **3.** O dono revisa o catálogo.
   - **4.** `scripts/baixar_pdfs.py` baixa os PDFs e as páginas das leis e decretos, com hash e opção `--reverificar`.
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
  - **página correta das legislações:** https://www.bombeiros.pr.gov.br/Prevencao (seção `#legislacao`). Cópia manual (plano B): `dados/fontes/legislacao.html`;
  - essa página **abre para programas** (testado em 18/11/2026), e os PDFs também;
  - os endereços `/Pagina/Legislacao-...` e `/PrevFogo/Pagina/Legislacao-...` **não servem** (não abrem no navegador e dão erro 403).
- **Conferência da Etapa 1 (18/11/2026)**, feita numa cópia baixada da página:
  - **91 links de PDF**, sem repetição: 87 de legislação e 4 "Modelos de documentação", que não são normas;
  - **por tipo:** CSCIP 2, portarias 2 (476/2025 e 443/2024), NPA 5, NPT 59 (contando as partes das NPTs 015, 025, 027 e 028), OT 19;
  - **leis e decretos** (Lei 19.449, Lei 13.976, Decreto 11.868, Resolução SESP 399/2020) não são PDF: apontam para páginas do site legislacao.pr.gov.br;
  - **revogadas sem link:** NPT 001 Parte 2 e NPT 004 (incorporadas à NPA 002) → entram como `pendente`;
  - **nenhuma consulta pública** aparece nesta página.
- **A confirmar:**
  - **NPT 001 Partes 1 e 3:** não aparecem na página. Não se sabe se foram revogadas ou se só ficaram de fora. Por ora, `pendente`.
  - **CSCIP "Agosto de 2021":** o arquivo se chama "versao_final_agosto_de_2023", foi criado em 20/03/2023 e tem 51 páginas. Pode ser o texto de 2021 consolidado em 2023. Conferir o conteúdo na Etapa 6.
  - **NPT 041:** o link aponta para "anexo_2_errata…", um arquivo criado em 28/10/2022 com 11 páginas. Parece ser a norma inteira com a errata, e não só a errata. Conferir na Etapa 6.
  - O texto desses PDFs está codificado: sem uma biblioteca de PDF (pdfplumber, Etapa 6), não dá para lê-lo.
- **Legislações anteriores:** a página tem o link "Clique aqui e tenha acesso as Legislações Anteriores", que leva a uma pasta do Google Drive: http://drive.google.com/drive/folders/1Z0fbQ0Skmlz4bqyO6hp7AqzFfTLQ6qvy. É o lugar para procurar as versões `pendente` e as revogadas antigas.
- **Etapa 2 concluída (18/11/2026):**
  - `scripts/catalogo.py` traz as funções comuns; `scripts/listar_normas.py` e `scripts/conferir_catalogo.py` foram criados;
  - catálogo gerado com **95 linhas**: 83 vigentes, 5 revogadas, 3 futuras e 4 pendentes;
  - por tipo: lei 2, decreto 1, resolução 1, portaria 2, CSCIP 2, NPA 5, NPT 63 (59 + 4 pendentes), OT 19.
  - **Testes que passaram:**
    - rodar duas vezes não duplica nada;
    - uma linha com `revisado = sim` é preservada;
    - o plano B (`--copia-local`) dá o mesmo resultado;
    - `conferir_catalogo.py` termina com 0 erros.
  - **Para a revisão:** a NPT 028 de 2014 (vigente até 24/04/2027) é substituída pela NPT 028 nova, que foi dividida em 3 partes. O programa não liga as duas sozinho. Preencher à mão `substituida_por = npt-028-p1_2027-04|npt-028-p2_2027-04|npt-028-p3_2027-04`.
- **Fase 1: Etapas 0, 1 e 2 concluídas.** A Etapa 3 (revisão do catálogo) ficou **adiada**. Nenhuma linha está marcada como `revisado = sim`.
- **Ajustes no catálogo:** `npt-028_2014-10` tem `substituida_por` = as 3 partes da NPT 028 nova. `npt-001-p3` tem na observação o link do PDF antigo.
- **Prioridade atual: protótipo** (ver seção "Protótipo").
- **Protótipo, Passo 1 concluído (18/11/2026):** `scripts/baixar_pdfs.py` criado.
  - **91 documentos baixados**, sem erros: 87 PDFs (cerca de 115 MB) e 4 páginas de leis, decretos e resoluções. As 4 `pendente` ficaram de fora por não terem link. `conferir_catalogo.py` termina com 0 erros.
  - **Opções:**
    - `--somente <ids>` baixa só os ids indicados;
    - `--reverificar` baixa de novo e avisa se o arquivo mudou.
  - **Como ele funciona:**
    - pula o que já foi baixado;
    - recusa um "PDF" que não comece com `%PDF`;
    - em linhas `revisado = sim`, só preenche as colunas vazias.
  - **Detalhe:** as páginas do legislacao.pr.gov.br trazem um código de sessão (`;jsessionid=...`) que muda a cada visita. O programa o apaga antes de salvar e de calcular o hash, para não acusar uma mudança falsa.
- **Próximo: Passo 2** (`.venv` com pdfplumber e streamlit, e `requirements.txt`).

## Como rodar os programas (PowerShell, dentro da pasta do projeto)

```powershell
cd "$HOME\OneDrive\Documentos\Normas_CBMPR"
python scripts\listar_normas.py                 # baixa a página e atualiza dados\catalogo.csv
python scripts\listar_normas.py --copia-local   # plano B: usa dados\fontes\legislacao.html
python scripts\conferir_catalogo.py             # lista erros e avisos do catálogo (não altera nada)
python scripts\baixar_pdfs.py                   # baixa o que falta (PDFs e páginas das leis)
python scripts\baixar_pdfs.py --reverificar     # baixa de novo e avisa se algum arquivo mudou no site
```
