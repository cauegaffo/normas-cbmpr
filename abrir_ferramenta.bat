@echo off
rem Abre a ferramenta de busca nas normas do CBMPR (Streamlit) com dois cliques.
rem Fechar esta janela desliga a ferramenta.

rem Entra na pasta onde este arquivo esta (a pasta do projeto).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: o ambiente virtual .venv nao foi encontrado nesta pasta.
    echo Crie o .venv e instale as bibliotecas antes - ver CLAUDE.md, Passo 2.
    pause
    exit /b 1
)

echo Abrindo a ferramenta Normas CBMPR no navegador...
echo Para FECHAR a ferramenta, feche esta janela.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py

rem Se o Streamlit parar com erro, a janela fica aberta para ler a mensagem.
pause
