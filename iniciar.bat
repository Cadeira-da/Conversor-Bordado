@echo off
title Conversor de Bordado
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/ marcando "Add Python to PATH".
  pause
  exit /b
)
python -c "import PIL, numpy" 2>nul || python -m pip install --upgrade pillow numpy
start "" pythonw conversor_bordado.py
