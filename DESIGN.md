# Diseño técnico — Ejecutable Wds Push GitHub

> Documento de diseño consolidado a partir de la sesión de discovery con el usuario.
> Fecha de redacción: 2026-05-11
> Autor: CJG Consultores (Max Godoy) en colaboración con Claude
> Estado: borrador para aprobación previa a la fase de implementación.

---

## 1. Objetivo

Construir un ejecutable de Windows (`.exe`, modo CLI interactivo, sin instalación) que respalde una carpeta local del usuario contra un repositorio privado de GitHub, manteniendo versionado diferencial, detección de cambios por contenido (no por nombre/timestamp), y permitiendo restaurar archivos borrados localmente.

---

## 2. Decisiones de diseño (resumen ejecutivo)

| Dimensión | Decisión |
|---|---|
| Lenguaje / runtime | Python 3.11 + PyInstaller (single-file `.exe`) |
| Algoritmo de hash | SHA-256 nativo (módulo `hashlib`) |
| Storage del PAT | Archivo cifrado AES-256-GCM + master password (derivada con PBKDF2-HMAC-SHA256, 600 000 iteraciones) |
| Storage de estado | `%APPDATA%\GitHubBackup\` (cache de hashes, manifiesto de borrados, config, logs) |
| Estructura del repo GitHub | Un repo privado único, cada carpeta source mapea a una rama distinta. El árbol de subcarpetas se replica idéntico dentro de la rama |
| Modelo de versionado | Commit + tag por push. Nombre custom propuesto por prompt; fallback automático `<archivo>_YYYYMMDD_HHMMSS` |
| Scope de source | Una sola carpeta source, confirmada al inicio de cada corrida (configurable vía `config`) |
| Detección de renombres | Sí, por coincidencia de SHA-256 |
| Confirmaciones | Resumen global + opción `[D]etalle` / `[S]eleccionar` / `[Y]es` / `[N]o` |
| Borrados locales | Nunca se borran en repo. Alerta + propuesta de restaurar los últimos 5 borrados del último mes |
| Atomicidad | Rollback total: si cualquier paso falla, el commit no se materializa |
| Logging | Dual: `operations.jsonl` (parseable, CI/CD) + `operations.md` (legible humano) |
| Documentación proyecto | Un único `README.md` con sección Changelog al final |
| Programación automática | Subcomando `schedule` que registra una Tarea Programada de Windows |

---

## 3. Arquitectura de carpetas y archivos

### 3.1. Estructura del proyecto (código fuente)

```
Ejecutable Wds Push Github/
├── DESIGN.md                    # este documento
├── README.md                    # uso, setup, comandos, FAQ, CHANGELOG
├── pyproject.toml               # metadata del paquete y dependencias
├── requirements.txt             # dependencias congeladas
├── build.spec                   # spec de PyInstaller
├── build.bat                    # script de compilación para Windows
├── src/
│   └── ghbackup/
│       ├── __init__.py
│       ├── __main__.py          # entrypoint cli
│       ├── cli.py               # parser y dispatch de subcomandos
│       ├── version.py           # __version__ del ejecutable
│       ├── auth/
│       │   ├── crypto.py        # AES-GCM + PBKDF2
│       │   ├── vault.py         # lectura/escritura del archivo cifrado
│       │   └── wizard.py        # paso a paso de generación de token
│       ├── github_io/
│       │   ├── client.py        # wrapper sobre PyGithub
│       │   ├── push.py          # commit atómico
│       │   ├── pull.py          # descarga de blobs
│       │   └── repo_setup.py    # creación/selección de repo
│       ├── scanner/
│       │   ├── walker.py        # recorrido recursivo del source
│       │   ├── hasher.py        # SHA-256 streaming
│       │   ├── diff.py          # comparación contra cache → DeltaReport
│       │   └── ignore.py        # parser de .gitignore + filtros default
│       ├── state/
│       │   ├── cache.py         # hashes y mtime persistidos
│       │   ├── deletion_manifest.py
│       │   └── config.py        # source path, repo, branch, etc.
│       ├── logging_/
│       │   ├── jsonl_writer.py
│       │   └── md_writer.py
│       ├── commands/
│       │   ├── setup.py
│       │   ├── push.py
│       │   ├── status.py
│       │   ├── restore.py       # --file / --tag / --date
│       │   ├── log.py
│       │   ├── config.py
│       │   ├── verify.py
│       │   └── schedule.py
│       └── ui/
│           ├── prompts.py       # questionary-like helpers
│           └── colors.py        # colorama wrappers
└── tests/
    ├── test_hasher.py
    ├── test_diff.py
    ├── test_vault.py
    └── ...
```

### 3.2. Datos en `%APPDATA%\GitHubBackup\`

```
%APPDATA%\GitHubBackup\
├── config.json                  # source path, repo full name, branch, etc. (sin secretos)
├── vault.enc                    # PAT cifrado (AES-GCM) — solo binario, no editar
├── cache.sqlite                 # hashes del último estado snapshot por archivo
├── deletion_manifest.json       # últimos borrados con timestamp + sha + ruta
└── logs/
    ├── operations.jsonl
    └── operations.md
```

---

## 4. Flujo del wizard de setup (primer arranque)

1. **Detección de primera vez:** si `%APPDATA%\GitHubBackup\config.json` no existe → arranca el wizard.
2. **Paso 1 — Master password:** se le pide al usuario crear una master password (mín. 12 caracteres). Se confirma con doble ingreso. Esta clave deriva la llave AES que cifra el PAT.
3. **Paso 2 — Generación del PAT en GitHub:**
   - El wizard imprime instrucciones paso a paso para crear un **fine-grained PAT** en `https://github.com/settings/personal-access-tokens/new`.
   - Scopes requeridos: `Repository access → All repositories (o seleccionar el repo destino)`, `Permissions → Contents: Read & Write`, `Metadata: Read`, `Administration: Read & Write` (solo si quiere crear repos desde el ejecutable).
   - Vigencia recomendada: 90 días (o "No expiration" si lo prefiere).
4. **Paso 3 — Ingreso del token:** el ejecutable lo lee por stdin (no eco), lo valida contra `GET /user`, muestra al usuario:
   - Cuenta de GitHub conectada (`login`, `name`, `email`)
   - Lista de repos donde tiene permisos de escritura
5. **Paso 4 — Selección de repo destino:**
   - Opción A: elegir uno de la lista de repos privados existentes.
   - Opción B: crear uno nuevo (siempre privado). El wizard pregunta nombre y descripción.
6. **Paso 5 — Carpeta source:** se le pide la ruta absoluta de la carpeta a respaldar. Se valida que exista y se calcula su tamaño total (para advertir si supera límites).
7. **Paso 6 — Nombre de rama:** se sugiere `<nombre-carpeta-source-slugificado>`. El usuario puede aceptar o cambiar.
8. **Paso 7 — Confirmación + inicialización:** se guarda `config.json` (sin secretos), `vault.enc` (con el PAT cifrado), y se hace el primer commit al repo (un `README.md` automático en la rama con metadata del backup).
9. **Paso 8 — Resumen final:** muestra repo destino, branch, source, y propone correr `ghbackup push` por primera vez.

---

## 5. Flujo del subcomando `push`

```text
ghbackup push [--name "v1.2"] [--yes]
```

1. **Desbloqueo:** pide la master password (oculta) y desencripta el PAT.
2. **Test de conexión:** `GET /user` y `GET /repos/{owner}/{repo}` → verifica acceso y muestra al usuario:
   `Conectado a GitHub como max.godoy → cjgconsultores/wds-backups, rama main-docs`.
3. **Confirmación de carpeta source:** muestra la ruta configurada y pide confirmar antes de escanear.
4. **Escaneo del source:**
   - Walker recursivo, aplicando filtros (`.backupignore`, defaults: `node_modules/`, `__pycache__/`, `.DS_Store`, `Thumbs.db`, `desktop.ini`, `*.tmp`).
   - Para cada archivo: hash SHA-256 streaming + size + mtime.
5. **Diff vs cache local:**
   - **Modificados:** mismo path, diferente SHA-256.
   - **Nuevos:** path no estaba en cache.
   - **Renombres:** archivo desaparece en path A pero aparece otro con el mismo SHA-256 en path B.
   - **Borrados:** path estaba en cache pero ya no existe en disco.
6. **Detección de drift con el repo:** se traen los SHAs del último commit del branch y se comparan con el cache local. Si hay archivos en el repo que no están localmente y no figuran en el manifiesto de borrados, se alerta:
   > "Hay 3 archivos en el repo que no están en tu carpeta source. ¿Querés ver si fueron borrados localmente?"
7. **Propuesta de restauración** (si aplica): muestra los últimos 5 archivos borrados dentro del último mes y permite recuperarlos uno por uno antes de pushear.
8. **Resumen + nombre de versión:**
   ```
   Resumen de cambios a respaldar:
     • Modificados: 4
     • Nuevos:      2
     • Renombres:   1
     • Carpetas nuevas: 1
   Tamaño total a subir: 1.2 MB

   Nombre de la versión (deja vacío para usar 'wds_20260511_143012'):
     >
   [Y]es subir / [N]o cancelar / [D]etalle / [S]eleccionar archivos
   ```
9. **Push atómico:**
   - Crea blobs para cada archivo nuevo/modificado (`POST /repos/.../git/blobs`).
   - Construye un tree completo del estado deseado (`POST /repos/.../git/trees`).
   - Crea un commit con mensaje `<nombre-versión> | <usuario>@<host> | <timestamp>` (`POST /repos/.../git/commits`).
   - Actualiza la ref del branch (`PATCH /repos/.../git/refs/heads/<branch>`).
   - Crea un tag annotated con el mismo nombre (`POST /repos/.../git/tags` + ref).
   - Si cualquier llamada falla → ningún commit queda en el branch. El estado local del cache no se actualiza.
10. **Post-éxito:**
    - Actualiza `cache.sqlite` con los nuevos hashes.
    - Loguea en `operations.jsonl` y `operations.md`.
    - Imprime el SHA del commit y la URL del tag en GitHub.

---

## 6. Modelo de versionado en GitHub

- **Commit por push:** mensaje `<nombre-versión> | <usuario>@<host> | <ISO-timestamp>`.
- **Tag annotated por push:** nombre = lo que el usuario tipeó, o `wds_YYYYMMDD_HHMMSS` por defecto.
  - Sanitización: espacios → `_`, sin caracteres especiales (`^`, `~`, `:`, `?`, `*`, `[`, `\`, `..`).
  - Si el tag ya existe, se sugiere un sufijo `_2`, `_3`, etc.
- **No se borra historia jamás:** ni archivos, ni carpetas, ni tags. Los borrados locales se marcan en el cuerpo del commit como `[Local-deleted: <ruta>]` y opcionalmente en un `.deleted-manifest.json` en la raíz de la rama.

---

## 7. Subcomando `restore`

Tres modos, todos interactivos:

```text
ghbackup restore --file <ruta-relativa>         # elige versión del archivo
ghbackup restore --tag <nombre-tag>             # snapshot completo de un tag
ghbackup restore --date 2026-05-01              # estado a esa fecha
```

- **`--file`:** lista los commits que afectaron ese path, muestra para cada uno la fecha y el tag asociado, descarga la versión elegida a la ruta original (o a `--out <ruta>` si se pasa).
- **`--tag`:** descarga el tree completo del tag a la carpeta source (avisa qué archivos sobrescribiría y pide confirmación).
- **`--date`:** busca el último commit con `committer.date <= fecha` y procede como `--tag`.

**Nunca sobrescribe sin confirmación.** Para cada archivo a restaurar pregunta `[O]verwrite / [S]kip / [B]ackup-existing-and-overwrite`.

---

## 8. Detección de cambios

### 8.1. Algoritmo

```python
sha256 = hashlib.sha256()
with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        sha256.update(chunk)
digest = sha256.hexdigest()
```

### 8.2. Política

- Un archivo se considera "no cambiado" únicamente si su SHA-256 coincide con el del cache.
- `size` y `mtime` se almacenan también, pero solo como metadata informativa; **no se usan como atajo para saltarse el hash** (porque el usuario explícitamente pidió detectar cambios que mantengan el mismo timestamp).
- Para archivos > 50 MB se imprime un indicador de progreso para que el usuario sepa que el hashing está vivo.

### 8.3. Cache local (`cache.sqlite`)

```sql
CREATE TABLE files (
    path        TEXT PRIMARY KEY,    -- ruta relativa al source root
    sha256      TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    mtime_utc   TEXT NOT NULL,       -- ISO 8601
    last_seen_commit TEXT,           -- SHA del último commit donde figuró
    last_push_tag    TEXT
);
CREATE INDEX idx_files_sha ON files(sha256);
```

---

## 9. Manifiesto de borrados

Se mantiene un archivo `deletion_manifest.json` en `%APPDATA%\GitHubBackup\`:

```json
{
  "entries": [
    {
      "path": "Proyectos/Cliente A/contrato_v3.docx",
      "sha256": "9af1...",
      "deleted_at_utc": "2026-05-10T18:23:00Z",
      "last_known_in_commit": "3a4b...",
      "last_known_in_tag": "wds_20260510_181104",
      "restored": false
    }
  ]
}
```

- **Política de propuesta:** en cada `push`, se muestran los hasta 5 borrados más recientes que (a) tengan `deleted_at_utc` dentro de los últimos 30 días y (b) tengan `restored == false`.
- Una vez propuesta una entrada, se marca `proposed_at_utc`; al cabo de 30 días deja de proponerse automáticamente.

---

## 10. Filtros de ignorado

### 10.1. Default (hard-coded)

```
node_modules/
__pycache__/
.git/
.venv/
venv/
.DS_Store
Thumbs.db
desktop.ini
*.tmp
*.swp
~$*
```

### 10.2. Custom (`.backupignore`)

Se admite un archivo `.backupignore` en la raíz del source con sintaxis idéntica a `.gitignore`.

---

## 11. Logging dual

### 11.1. `operations.jsonl`

Una línea JSON por evento:

```json
{"ts":"2026-05-11T17:42:00Z","action":"push","branch":"main-docs","tag":"v1.2","commit":"3a4b...","files":{"modified":4,"new":2,"renamed":1,"deleted":0},"bytes":1247392,"result":"ok","duration_ms":2841}
```

Acciones posibles: `setup_complete`, `push`, `push_failed`, `pull`, `restore`, `verify`, `config_changed`, `token_rotated`, `schedule_created`.

### 11.2. `operations.md`

Tabla apend-only:

```markdown
| Fecha (UTC)         | Acción  | Rama       | Tag                  | Archivos     | Tamaño   | Resultado |
|---------------------|---------|------------|----------------------|--------------|----------|-----------|
| 2026-05-11 17:42:00 | push    | main-docs  | v1.2                 | 4M / 2N / 1R | 1.19 MB  | ✅ ok     |
```

---

## 12. Subcomando `schedule`

```text
ghbackup schedule create --every daily --at 19:00
ghbackup schedule create --every hours --interval 4
ghbackup schedule create --at-logon
ghbackup schedule list
ghbackup schedule remove
```

- Registra una entrada en el Windows Task Scheduler vía `schtasks.exe /Create ...`.
- La tarea ejecuta `ghbackup.exe push --yes --no-prompt-name` (genera nombre de versión automático).
- Importante: en modo programado, el ejecutable necesita la master password. Hay dos opciones:
  - **a)** la tarea pasa la password vía argumento `--master-pass-env <VAR>` que lee de una variable de entorno cifrada por Windows (DPAPI). Recomendado.
  - **b)** se ofrece registrar una versión "headless" del PAT en el Credential Manager nativo de Windows (sin master password). Solo si el usuario lo elige explícitamente.

---

## 13. CLI completa

```text
ghbackup --version
ghbackup --help

ghbackup setup                     # wizard de primera vez
ghbackup push [--name STR] [--yes]
ghbackup status                    # dry-run
ghbackup restore --file PATH [--out PATH]
ghbackup restore --tag NAME
ghbackup restore --date YYYY-MM-DD
ghbackup log [--last N] [--json]
ghbackup config [show|set KEY VALUE|reset|rotate-token]
ghbackup verify                    # re-hashea, compara cache↔local↔repo
ghbackup schedule create ...
ghbackup schedule list
ghbackup schedule remove
```

---

## 14. Manejo de errores y casos límite

| Caso | Comportamiento |
|---|---|
| Token vencido / inválido | `push` aborta sin commitear, sugiere `config rotate-token` |
| Sin conexión a internet | retry x3 con backoff exponencial; si falla, aborta y no actualiza cache |
| Archivo > 100 MB (límite GitHub) | se reporta y se omite del push, queda en lista de "pendientes con tamaño excedido" |
| Master password olvidada | el PAT no se puede recuperar; hay que regenerarlo en GitHub y correr `setup` o `config rotate-token` |
| `cache.sqlite` corrupto | `verify` lo detecta y propone re-construirlo desde cero (re-hashea todo) |
| Carpeta source no existe | `push` aborta; el usuario puede correr `config set source <ruta>` |
| El tag ya existe en el repo | se sugiere sufijo `_2`, o el usuario tipea otro nombre |
| Conflicto de mayúsculas (Windows case-insensitive vs Git case-sensitive) | se detecta y se reporta como warning; se mantiene el casing del nombre que vino primero al repo |

---

## 15. Seguridad

- **PAT nunca en texto plano en disco.** Solo cifrado con AES-GCM dentro de `vault.enc`.
- **Master password nunca persistida.** Se pide en cada sesión interactiva y se mantiene solo en RAM durante la corrida.
- **Derivación de clave:** PBKDF2-HMAC-SHA256 con 600 000 iteraciones (recomendación OWASP 2023+) y salt aleatorio de 16 bytes guardado dentro de `vault.enc`.
- **No se loguea el PAT** en ningún archivo de log, ni siquiera enmascarado.
- **Master password mínimo 12 caracteres**; se sugiere passphrase de 4+ palabras.

---

## 16. Dependencias Python

```
PyGithub>=2.1.1            # API de GitHub
cryptography>=42.0.0       # AES-GCM, PBKDF2
colorama>=0.4.6            # colores en Windows CMD
questionary>=2.0.1         # prompts interactivos elegantes
pathspec>=0.12.1           # parsing de .gitignore-like
click>=8.1.7               # CLI framework
```

Build:

```
pyinstaller --onefile --name ghbackup --icon assets/icon.ico src/ghbackup/__main__.py
```

---

## 17. Plan de implementación

Las 12 tareas registradas en TodoList (visibles arriba en la sesión) cubren:

1. Consolidar diseño en `DESIGN.md` ← **este documento**
2. Esqueleto del proyecto Python
3. Módulo de autenticación (token cifrado)
4. Wizard de setup
5. Motor de detección de cambios
6. Push atómico
7. Restore (3 modos) y manifiesto de borrados
8. Logging dual
9. Subcomandos auxiliares (status, log, config, verify, schedule)
10. README.md con Changelog
11. Build con PyInstaller
12. Verificación final contra requisitos originales

---

## 18. Supuestos pendientes de confirmar

Los siguientes puntos los voy a asumir por defecto si no me decís lo contrario:

1. **Idioma de la CLI:** español (lo escribís así, asumo que querés los prompts en español).
2. **Nombre del ejecutable:** `ghbackup.exe`.
3. **Master password se pide en cada sesión interactiva.** No se cachea entre corridas.
4. **El ejecutable corre en Python 3.11+ embebido por PyInstaller.** No requiere Python instalado en la PC destino.
5. **Compilación se hará desde una PC con Windows.** Cross-compilar desde Mac/Linux con PyInstaller no es trivial; se documentará el paso de build en Windows.

---

## 19. Cambios a este diseño

Cualquier cambio que vayamos haciendo durante la implementación se va a reflejar acá y en la sección Changelog del `README.md`.
