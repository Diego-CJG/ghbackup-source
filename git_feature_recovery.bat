@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM git_feature_recovery.bat
REM
REM Crea la rama feature/recovery-codes-v0.2.0, commitea todos los cambios
REM de la nueva funcionalidad y la pushea a GitHub.
REM ─────────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║     Nueva rama: feature/recovery-codes-v0.2.0              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

where git >nul 2>&1
if errorlevel 1 ( echo [ERROR] Git no encontrado. & pause & exit /b 1 )

REM ── Asegurarse de estar en main y actualizado ────────────────────────────
echo Actualizando main...
git checkout main
git pull origin main
echo.

REM ── Crear rama feature ───────────────────────────────────────────────────
echo Creando rama feature/recovery-codes-v0.2.0...
git checkout -b feature/recovery-codes-v0.2.0
echo.

REM ── Mostrar archivos que se van a commitear ──────────────────────────────
echo Archivos modificados y nuevos:
git status --short
echo.
pause

REM ── Agregar todos los cambios ────────────────────────────────────────────
git add .

REM ── Commit ───────────────────────────────────────────────────────────────
git commit -m "feat(recovery): add recovery codes — v0.2.0

Nuevos archivos:
  - src/ghbackup/auth/recovery.py: generacion (8 codigos XXXXX-XXXXX-XXXXX-XXXXX-XXXXX,
    charset sin ambiguos), almacenamiento SHA-256, validacion de uso unico
  - src/ghbackup/commands/recover_cmd.py: comando `ghbackup config recover`
  - tests/test_recovery.py: 30 tests (133 total, todos verdes)

Archivos modificados:
  - state/paths.py: nueva funcion recovery_codes_path()
  - setup_cmd.py: genera y muestra 8 recovery codes al finalizar setup
  - config_cmd.py: registra subcomando `recover`, borra codigos en reset
  - version.py + pyproject.toml: bumpeados a v0.2.0

Comportamiento: al olvidar la master password, `ghbackup config recover`
valida un recovery code, elimina el vault y guia a re-configurar.
El historial de backups en GitHub se preserva."

if errorlevel 1 (
    echo [ERROR] Fallo el commit.
    pause
    exit /b 1
)

echo.
echo Pusheando rama a GitHub...
git push origin feature/recovery-codes-v0.2.0

if errorlevel 1 (
    echo [ERROR] Fallo el push. Verificá tu autenticacion con GitHub.
    pause
    exit /b 1
)

echo.
echo ┌──────────────────────────────────────────────────────────────┐
echo │  Rama pusheada correctamente.                                │
echo │                                                              │
echo │  Proximos pasos:                                             │
echo │  1. Revisar los workflows en GitHub Actions:                 │
echo │     https://github.com/Diego-CJG/ghbackup-source/actions    │
echo │  2. Cuando esten en verde, hacer merge a main:               │
echo │                                                              │
echo │     git checkout main                                        │
echo │     git merge feature/recovery-codes-v0.2.0 --no-ff         ^
echo │       -m "Merge feature/recovery-codes-v0.2.0 into main"    │
echo │     git push origin main                                     │
echo │     git branch -d feature/recovery-codes-v0.2.0             │
echo │                                                              │
echo │  3. Para generar el .exe de la v0.2.0:                       │
echo │     git tag v0.2.0                                           │
echo │     git push origin v0.2.0                                   │
echo └──────────────────────────────────────────────────────────────╝
echo.
pause
endlocal
