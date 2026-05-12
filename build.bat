@echo off
REM -------------------------------------------------------------------------
REM Build script para ghbackup.exe
REM
REM Uso (en una PC con Windows + Python 3.11 instalado):
REM   1. Abrí cmd o PowerShell en la raíz del proyecto.
REM   2. Ejecutá:    build.bat
REM   3. El .exe queda en  dist\ghbackup.exe
REM -------------------------------------------------------------------------
setlocal enabledelayedexpansion

echo.
echo === [1/4] Verificando Python ===
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en PATH. Instalá Python 3.11+ desde python.org.
    exit /b 1
)
python --version

echo.
echo === [2/4] Creando virtualenv local en .build_venv ===
if not exist .build_venv (
    python -m venv .build_venv
)
call .build_venv\Scripts\activate.bat

echo.
echo === [3/4] Instalando dependencias y PyInstaller ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo === [4/4] Compilando con PyInstaller ===
pyinstaller --clean build.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller falló.
    exit /b 1
)

echo.
echo === BUILD OK ===
echo Ejecutable generado en:  dist\ghbackup.exe
echo.
echo Probalo con:    dist\ghbackup.exe --version
echo Setup inicial:  dist\ghbackup.exe setup
echo.
endlocal
