@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM git_demo_branch.bat
REM
REM Demo completa del flujo de integración de una rama feature:
REM   1. Verifica que main esté limpio y actualizado
REM   2. Crea rama feature/improve-lockout-warnings
REM   3. Muestra los cambios incluidos en esta rama
REM   4. Corre los tests localmente (103 tests)
REM   5. Hace commit y push de la rama
REM   6. Hace merge a main y push — dispara GitHub Actions automáticamente
REM
REM REQUISITO: haber corrido git_setup.bat al menos una vez antes.
REM ─────────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║        DEMO: Flujo de integración de rama feature           ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Verificar dependencias ────────────────────────────────────────────────
where git >nul 2>&1
if errorlevel 1 ( echo [ERROR] Git no encontrado. & pause & exit /b 1 )
where python >nul 2>&1
if errorlevel 1 ( echo [ERROR] Python no encontrado. & pause & exit /b 1 )

echo [OK] Git y Python encontrados.
echo.

REM ── PASO 1: Estado inicial ────────────────────────────────────────────────
echo ══ PASO 1/6  Estado inicial de main ════════════════════════════
git checkout main
git status
git log --oneline -5
echo.
pause

REM ── PASO 2: Crear rama feature ────────────────────────────────────────────
echo ══ PASO 2/6  Crear rama feature ════════════════════════════════
git checkout -b feature/improve-lockout-warnings
echo.
echo Rama creada:
git branch
echo.
pause

REM ── PASO 3: Mostrar cambios ───────────────────────────────────────────────
echo ══ PASO 3/6  Cambios en esta rama ══════════════════════════════
echo.
echo Archivos modificados/creados respecto a main:
git diff main --name-only
echo.
echo Resumen del cambio:
echo   - lockout.py: nueva funcion remaining_attempts() y clase AttemptsWarning
echo   - lockout.py: record_failure() ahora advierte cuando quedan 2 intentos o menos
echo   - test_lockout.py: 16 tests nuevos cubriendo la nueva logica
echo.
pause

REM ── PASO 4: Tests locales ─────────────────────────────────────────────────
echo ══ PASO 4/6  Correr tests localmente ═══════════════════════════
echo.
pip install -e ".[dev]" -q 2>nul
python -m pytest tests/ -v --no-header --tb=short --no-cov
if errorlevel 1 (
    echo.
    echo [ERROR] Tests fallaron. No se hace commit.
    git checkout main
    git branch -D feature/improve-lockout-warnings
    pause
    exit /b 1
)
echo.
echo [OK] Todos los tests pasaron.
echo.
pause

REM ── PASO 5: Commit y push de la rama ─────────────────────────────────────
echo ══ PASO 5/6  Commit y push de la rama feature ══════════════════
git add .
git status
echo.
git commit -m "feat(lockout): add remaining_attempts() and AttemptsWarning

- Nueva funcion remaining_attempts() para consultar intentos disponibles
- record_failure() ahora lanza AttemptsWarning cuando quedan 2 intentos o menos
- Nueva clase AttemptsWarning para distinguir advertencia de bloqueo total
- 16 tests nuevos en test_lockout.py cubriendo toda la nueva logica
- 103/103 tests pasando"

git push origin feature/improve-lockout-warnings
echo.
echo [OK] Rama pusheada a GitHub.
echo     GitHub Actions correría los workflows de test + lint + security
echo     si esta fuera una Pull Request. Continuamos con el merge directo.
echo.
pause

REM ── PASO 6: Merge a main y push ──────────────────────────────────────────
echo ══ PASO 6/6  Merge a main y push (dispara GitHub Actions) ══════
git checkout main
git merge feature/improve-lockout-warnings --no-ff -m "Merge feature/improve-lockout-warnings into main"
echo.
echo Log actualizado:
git log --oneline -5
echo.
git push origin main
echo.
echo [OK] Push a main completado.
echo.
echo ┌──────────────────────────────────────────────────────────────┐
echo │  GitHub Actions ahora está corriendo automáticamente:        │
echo │                                                              │
echo │  ✓ test.yml    — pytest en Python 3.11 y 3.12               │
echo │  ✓ lint.yml    — ruff + mypy                                 │
echo │  ✓ security.yml — bandit + pip-audit                        │
echo │                                                              │
echo │  Seguí el progreso en:                                       │
echo │  https://github.com/Diego-CJG/ghbackup-source/actions       │
echo └──────────────────────────────────────────────────────────────┘
echo.
echo Limpiando rama local (ya mergeada):
git branch -d feature/improve-lockout-warnings
echo.
pause
endlocal
