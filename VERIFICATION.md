# Verificación final — checklist contra requisitos originales

Cruce línea por línea de los requisitos del pedido inicial vs. lo implementado.

| # | Requisito original | Implementación | Archivo |
|---|---|---|---|
| 1 | Ejecutable que administre respaldo de versiones nuevas a GitHub | `ghbackup.exe` single-file vía PyInstaller | `build.spec`, `build.bat` |
| 2 | Modo CLI interactivo con prompts (pregunta/validación/sí-no/todo/omitir) | click + questionary; opciones [Y]/[N]/[D]etalle/[S]eleccionar | `ui/prompts.py`, `commands/push_cmd.py` |
| 3 | Solo ejecutable, no instalable | PyInstaller `--onefile`, ejecutable portable sin admin | `build.spec` |
| 4 | Conexión por API key | Personal Access Token de GitHub | `auth/vault.py`, `github_io/client.py` |
| 5 | Instrucciones para conexión por primera vez | Wizard de 7 pasos con instrucciones impresas para generar PAT | `commands/setup_cmd.py` |
| 6 | Validar API key con test de conexión | `gh_client.test_connection()` → `GET /user` | `github_io/client.py` |
| 7 | Informar cuenta GitHub y directorio destino | El push imprime `login → repo (branch) | source` antes de actuar | `commands/push_cmd.py` líneas iniciales |
| 8 | Validar contenido de carpeta source y entender cambios | Walker + SHA-256 + diff vs cache | `scanner/walker.py`, `scanner/hasher.py`, `scanner/diff.py` |
| 9 | Solo respaldar archivos que cambiaron | `report.modified` y `report.new`; `unchanged` se saltea | `scanner/diff.py` |
| 10 | Archivos nuevos detectados | `report.new` en DeltaReport | `scanner/diff.py` |
| 11 | Carpetas nuevas dentro de la raíz | El walker recursivo las recorre y los archivos nuevos llevan su path completo | `scanner/walker.py` |
| 12 | Detectar cambios aunque mantenga timestamp/nombre | SHA-256 puro, no se usa mtime como atajo | `scanner/hasher.py`, `scanner/diff.py` |
| 13 | Archivos no cambiados NO se refrescan | Solo se generan blobs para `modified + new + renamed`; `unchanged` se ignora completamente | `commands/push_cmd.py` línea `upserts = ...` |
| 14 | Declarar archivos del push antes de subir | `_print_summary()` + opción `[D]etalle` que lista archivo por archivo | `commands/push_cmd.py` `_print_detail()` |
| 15 | Cada paso necesita confirmación | Confirmaciones en: setup (cada paso), push (escanear → subir), restore (modo + cada archivo), config reset, schedule create | `commands/*` |
| 16 | Carpetas borradas localmente JAMÁS se borran del repo | Política `local_deletions` solo anota en mensaje del commit; el tree nuevo se construye sobre el anterior sin remover paths | `github_io/push.py` `_do_push()` |
| 17 | Solo incrementar en versiones / marcar las borradas | `[Borrados localmente]` en el commit message + `deletion_manifest.json` | `github_io/push.py`, `state/deletion_manifest.py` |
| 18 | Comando para consultar y descargar archivos del repo | `ghbackup restore --file/--tag/--date` | `commands/restore_cmd.py` |
| 19 | Aviso de diferencias repo↔local por borrado | El push detecta `remote_files - local_paths` y avisa | `commands/push_cmd.py` |
| 20 | Sugerir restauración de los últimos 5 borrados | `manifest.recent_candidates(limit=5, days=30)` (los últimos 5 del último mes) | `state/deletion_manifest.py`, `commands/push_cmd.py` |
| 21 | Prompt para nombre de la nueva versión | Push pregunta nombre antes de subir, con default sugerido | `commands/push_cmd.py` `version_name` |
| 22 | Si no se define nombre → archivo + timestamp | `auto_tag_name()` → `<carpeta>_YYYYMMDD_HHMMSS` | `github_io/push.py` `auto_tag_name()` |
| 23 | Log de todos los pull y push para CI/CD | `operations.jsonl` + `operations.md` con cada `push`, `restore`, `push_failed`, etc. | `logging_/dual_logger.py` |
| 24 | README con todas las instrucciones | `README.md` con 13 secciones | `README.md` |
| 25 | Sección de versionado en README (fecha/hora/cambios) | Sección 13 "Changelog" del README con v0.1.0 | `README.md` |

## Verificaciones técnicas adicionales

- ✅ `python3 -m py_compile` sobre todos los `.py` → cero errores de sintaxis.
- ✅ Estructura modular: 7 paquetes con responsabilidades claras (auth, github_io, scanner, state, logging_, commands, ui).
- ✅ Sin imports circulares evidentes (cli.py importa comandos lazy).
- ✅ Token cifrado con AES-GCM (autenticado) y PBKDF2-HMAC-SHA256 con 600 000 iteraciones (estándar OWASP 2023+).
- ✅ El PAT nunca se guarda en plano ni se loguea.
- ✅ La master password nunca se persiste.
- ✅ Rollback total ante falla del push: la ref del branch no se actualiza si los pasos previos fallaron.
- ✅ Retry con backoff exponencial (3 intentos) ante fallas transitorias de red.

## Próximos pasos sugeridos para el usuario

1. **Compilar el `.exe`** en una PC con Windows usando `build.bat`.
2. **Correr el wizard** con `dist\ghbackup.exe setup`.
3. **Hacer un push de prueba** sobre una carpeta chica para validar el flujo completo.
4. **Crear la Tarea Programada** (opcional) con `ghbackup schedule create --every daily --at 19:00`.

## Posibles mejoras a futuro (fuera del scope inicial)

- Soporte para Git LFS (archivos > 100 MB).
- Múltiples carpetas source configuradas simultáneamente.
- Modo headless usando Windows Credential Manager (en vez de master password).
- Telegram/Discord webhooks ante éxito/falla.
- Comando `diff` para comparar dos tags directamente.
