@echo off
cd /d "%~dp0"
echo Iniciando o Portfolio de videos Cetrus...
echo Acesse http://127.0.0.1:8000 no navegador.
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause

