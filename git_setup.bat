@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM git_setup.bat — Inicializa el repositorio Git local y conecta a GitHub
REM Ejecutar UNA SOLA VEZ desde la raíz del proyecto.
REM Podés borrarlo después.
REM ─────────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

echo.
echo === [1/6] Verificando Git ===
where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git no encontrado en PATH.
    echo Descargalo desde https://git-scm.com e instalalo.
    pause
    exit /b 1
)
git --version

echo.
echo === [2/6] Limpiando repo previo (si existe) ===
if exist ".git" (
    echo Se encontró una carpeta .git preexistente. Eliminando...
    rmdir /s /q ".git"
    if exist ".git" (
        echo [WARN] No se pudo eliminar .git automaticamente.
        echo Elimínala manualmente y volvé a correr este script.
        pause
        exit /b 1
    )
    echo Eliminada OK.
)

echo.
echo === [3/6] Inicializando repositorio local (rama: main) ===
git init -b main
if errorlevel 1 (
    echo [ERROR] Falló git init.
    pause
    exit /b 1
)

echo.
echo === [4/6] Configurando identidad local ===
git config user.name "Diego Barahona"
git config user.email "diego.barahona@cjgconsultores.com"

echo.
echo === [5/6] Conectando al repositorio remoto ===
git remote add origin https://github.com/Diego-CJG/ghbackup-source.git
echo Remote "origin" agregado: https://github.com/Diego-CJG/ghbackup-source.git

echo.
echo === [6/6] Primer commit y push ===
git add .
git status
echo.
git commit -m "feat: initial commit — ghbackup v0.1.0

Código fuente completo del ejecutable ghbackup.
Incluye: src/, build.bat, build.spec, requirements.txt,
pyproject.toml, DESIGN.md, VERIFICATION.md, README.md."

if errorlevel 1 (
    echo [ERROR] Falló el commit.
    pause
    exit /b 1
)

echo.
echo Subiendo al repositorio remoto...
echo (Si es la primera vez, GitHub te pedirá autenticación)
git push -u origin main

if errorlevel 1 (
    echo.
    echo [INFO] El push falló. Puede ser un problema de autenticacion.
    echo Opciones:
    echo   1. Corré: git push -u origin main
    echo      y autenticate con tu usuario y un Personal Access Token de GitHub.
    echo   2. Configurá Git Credential Manager:
    echo      https://github.com/git-ecosystem/git-credential-manager
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  SETUP COMPLETO
echo  Repositorio: https://github.com/Diego-CJG/ghbackup-source
echo  Rama: main
echo ============================================================
echo.
echo Podés borrar este archivo (git_setup.bat) — ya no lo necesitás.
echo.
pause
endlocal
