# ghbackup — Ejecutable de respaldo diferencial a GitHub

> Herramienta CLI interactiva (Windows `.exe`, modo línea de comando con prompts) que
> respalda una carpeta local a un repositorio privado de GitHub con detección de cambios
> por contenido (SHA-256), versionado por tags, y restauración bajo demanda.

---

## Tabla de contenidos

1. [Características](#1-características)
2. [Requisitos](#2-requisitos)
3. [Instalación / Compilación](#3-instalación--compilación)
4. [Primer uso (Setup)](#4-primer-uso-setup)
5. [Comandos disponibles](#5-comandos-disponibles)
6. [Cómo funciona internamente](#6-cómo-funciona-internamente)
7. [Archivos de estado](#7-archivos-de-estado)
8. [Logs y CI/CD](#8-logs-y-cicd)
9. [Restauración](#9-restauración)
10. [Respaldo automático (Tarea Programada)](#10-respaldo-automático-tarea-programada)
11. [Preguntas frecuentes](#11-preguntas-frecuentes)
12. [Limitaciones conocidas](#12-limitaciones-conocidas)
13. [Changelog](#13-changelog)

---

## 1. Características

- **Single-file `.exe` para Windows.** No requiere instalar Python ni nada en la PC destino.
- **CLI 100% interactiva.** Confirmaciones, prompts, opciones [Y]es / [N]o / [D]etalle / [S]eleccionar.
- **Detección de cambios por contenido.** Cada archivo se hashea con SHA-256: cambios en el contenido se detectan aunque el nombre y el timestamp sigan iguales.
- **Versionado por tag.** Cada push crea un commit + un tag annotated con el nombre que vos elijas (o uno automático `carpeta_YYYYMMDD_HHMMSS`).
- **Rollback total.** Si el push falla en cualquier paso, ningún commit queda en el repo y el cache local no se modifica.
- **Detección de renombres.** Si un archivo cambia de ruta pero conserva su SHA-256, se reporta como rename (no como delete+add).
- **El repo nunca borra.** Los archivos eliminados localmente quedan intactos en el repositorio y se anotan en el mensaje del commit.
- **Restore por archivo / tag / fecha.** Tres modos de recuperación desde GitHub.
- **Propuesta de recuperación.** En cada push, propone restaurar los últimos 5 archivos borrados dentro del último mes.
- **Token cifrado.** El Personal Access Token se guarda en disco cifrado con AES-256-GCM derivado de una master password mediante PBKDF2 (600 000 iteraciones).
- **Logs duales.** Cada operación queda registrada en `operations.jsonl` (parseable para CI/CD) y en `operations.md` (legible humano).
- **Programación automática opcional.** Subcomando `schedule` para registrar una Tarea Programada de Windows.

---

## 2. Requisitos

### Para correr el `.exe` ya compilado

- Windows 10 / 11 (64-bit).
- Conexión a internet.
- Una cuenta de GitHub (gratuita o paga).
- Permiso para crear Personal Access Tokens en esa cuenta.

### Para compilarlo desde código fuente

- Windows 10 / 11.
- Python 3.11 o superior (`python --version`).
- Acceso a internet para `pip install`.

---

## 3. Instalación / Compilación

### Opción A — Usar el `.exe` precompilado

Si ya tenés el archivo `ghbackup.exe`, copialo a cualquier carpeta de tu PC (por ejemplo
`C:\Tools\ghbackup\`). No necesita instalación ni privilegios de administrador.

Probá que funciona:

```cmd
ghbackup.exe --version
```

### Opción B — Compilar desde código fuente

1. Cloná o copiá el proyecto a una PC con Windows.
2. Asegurate de tener Python 3.11+ instalado y en el PATH.
3. Desde la raíz del proyecto, ejecutá:

   ```cmd
   build.bat
   ```

4. Al terminar tendrás el ejecutable en `dist\ghbackup.exe`.

Detalles internos del build:

- Se crea un virtualenv temporal en `.build_venv\`.
- Se instalan las dependencias declaradas en `requirements.txt`.
- Se invoca `pyinstaller --clean build.spec` que produce un `.exe` single-file.

---

## 4. Primer uso (Setup)

La primera vez que corras el ejecutable, lanzá el wizard:

```cmd
ghbackup.exe setup
```

El wizard te guía paso a paso:

### Paso 1 — Master password

Definís una contraseña local que se usará para cifrar el token de GitHub. Mínimo 12
caracteres. Se te pide dos veces para evitar typos. **Esta master password NO se guarda
en ningún lado.** La vas a tener que ingresar cada vez que corras un comando que necesite
hablar con GitHub.

### Paso 2 — Generar el Personal Access Token (PAT) en GitHub

El wizard imprime las instrucciones detalladas:

1. Abrir `https://github.com/settings/personal-access-tokens/new`.
2. Crear un token **fine-grained** con:
   - **Expiration:** 90 días (recomendado).
   - **Repository access:** "All repositories" si querés que `ghbackup` cree el repo, o
     "Only select repositories" si ya lo creaste y querés solo conectarte.
   - **Permissions:**
     - Contents → Read and write
     - Metadata → Read-only
     - Administration → Read and write (solo si querés crear repos desde el ejecutable)
3. Generate token → copialo.

### Paso 3 — Pegar y validar el token

Lo pegás en la terminal (no se muestra al tipear) y el ejecutable valida que tenga
permisos llamando a `GET /user`. Te muestra a qué cuenta está conectado.

### Paso 4 — Elegir repositorio destino (siempre privado)

El wizard te presenta dos opciones:

- **Crear uno nuevo.** Te pide nombre, lo crea privado, lo inicializa con un README.
- **Conectar a uno existente.** Te lista los repos privados donde tenés permiso de
  escritura y elegís uno.

### Paso 5 — Carpeta source local

Le indicás la ruta absoluta de la carpeta que querés respaldar
(`C:\Documentos\MiCarpeta`, `D:\Proyectos\ClienteX`, etc.). Se valida que exista.

### Paso 6 — Nombre de la rama

Se sugiere el nombre slugificado de la carpeta. Podés aceptarlo o tipear otro.

### Paso 7 — Confirmar y guardar

Te muestra un resumen, confirmás, y el ejecutable:

- Guarda el token cifrado en `%APPDATA%\GitHubBackup\vault.enc`.
- Guarda la config en `%APPDATA%\GitHubBackup\config.json` (sin secretos).
- Asegura que la rama exista en el repo (la crea si hace falta).

Listo. Ya podés correr `ghbackup push`.

---

## 5. Comandos disponibles

```text
ghbackup --version
ghbackup --help
ghbackup setup                              Wizard de primera conexión
ghbackup push [--name STR] [--yes]          Detecta cambios y respalda
ghbackup status                             Dry-run: muestra deltas sin subir
ghbackup restore --file PATH [--out PATH]   Restaura un archivo (elegís versión)
ghbackup restore --tag NAME                 Restaura un snapshot completo
ghbackup restore --date YYYY-MM-DD          Restaura el estado a esa fecha
ghbackup log [--last N] [--json]            Histórico de operaciones
ghbackup config show                        Muestra la configuración actual
ghbackup config set KEY VALUE               Cambia source_folder o branch
ghbackup config rotate-token                Reemplaza el PAT
ghbackup config reset                       Borra todo (irreversible)
ghbackup verify [--rebuild]                 Diagnóstico de consistencia
ghbackup schedule create [--every ...]      Crea Tarea Programada de Windows
ghbackup schedule list                      Lista la tarea registrada
ghbackup schedule remove                    Elimina la tarea
```

### Ejemplo típico — flujo completo

```cmd
:: Primera vez
ghbackup setup

:: Revisar qué cambió antes de subir
ghbackup status

:: Pushear con un nombre custom
ghbackup push --name "antes_de_la_reunion_con_cliente"

:: Más tarde, recuperar la versión "antes_de_la_reunion_con_cliente"
ghbackup restore --tag antes_de_la_reunion_con_cliente

:: Recuperar solo un archivo específico
ghbackup restore --file "Clientes\X\propuesta.docx"

:: Recuperar como estaba todo el 1 de mayo
ghbackup restore --date 2026-05-01
```

---

## 6. Cómo funciona internamente

### 6.1. Detección de cambios

1. Walker recursivo de la carpeta source, aplicando filtros (`.backupignore` opcional +
   defaults como `node_modules/`, `__pycache__/`, `.DS_Store`, `Thumbs.db`, `*.tmp`...).
2. Para cada archivo, se calcula el SHA-256 con lectura por chunks de 1 MB.
3. Se compara contra el cache local (`cache.sqlite` en `%APPDATA%\GitHubBackup\`):
   - SHA-256 igual → sin cambios.
   - SHA-256 distinto, mismo path → modificado.
   - Path nuevo → potencialmente nuevo o renombre.
   - Path en cache pero no en disco → potencialmente borrado o renombre.
4. Reconciliación: si un archivo desaparece en path A y aparece otro con el mismo
   SHA-256 en path B, se reporta como **rename**.

### 6.2. Push atómico

El push se hace en pasos discretos contra la API de GitHub:

1. Asegurar que la rama exista (crearla si hace falta desde el default branch).
2. Crear blobs (`POST /repos/.../git/blobs`) para cada archivo nuevo/modificado.
3. Construir el tree (`POST /repos/.../git/trees`) basado en el tree anterior.
4. Crear el commit (`POST /repos/.../git/commits`) referenciando ese tree y el commit padre.
5. Actualizar la ref del branch (`PATCH /refs/heads/<branch>`). **Este es el punto de no retorno.**
6. Crear el tag annotated (`POST /git/tags` + `POST /refs/tags/...`).

Si cualquier paso anterior al 5 falla, no se actualiza la ref → el repo queda intacto.
Si falla el paso 6 (tag), el commit ya quedó pero se reintenta el tag aparte; el log
queda con `result: warning`.

### 6.3. Política de borrados

Los archivos borrados localmente **nunca se borran en el repo**. Cada push los menciona
en el cuerpo del commit:

```
nombre_de_version_aquí | max.godoy | versión generada por ghbackup

[Borrados localmente — NO eliminados del repositorio]
- Clientes/X/notas_2023.txt
- Templates/old_logo.png
```

Y se agregan a `deletion_manifest.json` para proponer su restauración en los próximos
30 días (hasta un máximo de 5 propuestas por push).

---

## 7. Archivos de estado

Todo el estado del ejecutable vive en `%APPDATA%\GitHubBackup\`:

```
%APPDATA%\GitHubBackup\
├── config.json              Config (source, repo, branch, cuenta). Sin secretos.
├── vault.enc                PAT cifrado (AES-GCM). NO editar manualmente.
├── cache.sqlite             Cache de hashes por archivo.
├── deletion_manifest.json   Manifiesto de archivos borrados localmente.
└── logs/
    ├── operations.jsonl     Una línea JSON por evento (CI/CD).
    └── operations.md        Tabla legible humana.
```

---

## 8. Logs y CI/CD

Cada operación deja dos rastros:

### 8.1. `operations.jsonl`

Una línea JSON por evento. Ejemplo:

```json
{"ts":"2026-05-11T17:42:00Z","action":"push","branch":"clientes","tag":"v_pre_demo","commit":"3a4b9c1...","files":{"modified":4,"new":2,"renamed":1,"deleted":0,"unchanged":312},"bytes":1247392,"result":"ok","duration_ms":2841}
```

Acciones posibles: `setup_complete`, `push`, `push_failed`, `pull`, `restore`,
`verify`, `config_changed`, `token_rotated`, `schedule_created`.

Pensado para parsearlo con `jq`, integrarlo a un script de monitoreo, o exponerlo en un
dashboard. Cada línea es autocontenida.

### 8.2. `operations.md`

Tabla apend-only con cada fila representando una operación. Ideal para leer a ojo o
abrir desde el explorador.

### 8.3. Consultar desde la CLI

```cmd
ghbackup log --last 30           :: imprime los últimos 30 eventos formateados
ghbackup log --last 100 --json   :: imprime el JSON crudo
```

---

## 9. Restauración

Hay tres modos, todos interactivos:

### `--file <ruta-relativa>`

Lista todos los commits que tocaron ese archivo en la rama configurada, muestra fecha,
tag asociado, primera línea del mensaje, y te deja elegir cuál descargar. Por defecto
escribe en la ubicación original del archivo. Si querés a otra ruta, usá `--out`.

### `--tag <nombre>`

Descarga el snapshot completo del tag. Te pregunta confirmación antes de empezar y,
archivo por archivo, te ofrece `[Sobrescribir] [Saltar] [Backup local y sobrescribir]`.

### `--date YYYY-MM-DD`

Busca el último commit en la rama con `committer.date <= fecha` y se comporta como
`--tag`, pero sobre ese commit.

---

## 10. Respaldo automático (Tarea Programada)

Para correr el push de forma automática:

```cmd
ghbackup schedule create --every daily --at 19:00
ghbackup schedule create --every hours --interval 4
ghbackup schedule create --every logon
```

Esto registra una Tarea en Windows Task Scheduler que ejecuta
`ghbackup push --yes --no-prompt-name --master-pass-env GHBACKUP_MASTER`.

> **Importante:** para que la tarea no pida la master password, hay que definir una
> variable de entorno (por ejemplo `GHBACKUP_MASTER`) con tu master password en el
> contexto de Windows. Eso es un paso manual que el ejecutable no automatiza por
> seguridad. Se puede setear con `setx GHBACKUP_MASTER "tu_master_password"` en un
> cmd con privilegios.

Otras operaciones:

```cmd
ghbackup schedule list      :: ver la tarea registrada
ghbackup schedule remove    :: borrar la tarea
```

---

## 11. Preguntas frecuentes

### ¿Qué pasa si olvido la master password?

No se puede recuperar (no se guarda en ningún lado). Solución: regenerar el PAT desde
github.com y correr `ghbackup setup` de nuevo (o `ghbackup config reset` antes).

### ¿Qué pasa si el repo ya tiene contenido?

Si conectás a un repo existente con archivos, el primer push construye un tree
incremental sobre el HEAD actual del branch, sin pisar lo que ya estaba.

### ¿Puedo respaldar más de una carpeta?

En esta versión inicial, una sola carpeta por configuración. Si querés respaldar varias
carpetas, podés correr `ghbackup config set source_folder D:\OtraCarpeta` para rotar.
Cada carpeta puede vivir en una rama distinta del mismo repo.

### ¿Cómo evito que se respalden archivos sensibles?

Creá un archivo `.backupignore` en la raíz de la carpeta source con sintaxis idéntica
a `.gitignore`. Por ejemplo:

```
secretos/
*.key
config.local.json
```

### ¿Por qué SHA-256 y no MD5?

Porque MD5 tiene colisiones conocidas (dos archivos distintos pueden dar el mismo
hash si alguien las fabrica adrede) y SHA-256 no. Para detectar cambios accidentales
MD5 alcanza, pero SHA-256 es nativo en Python (sin dependencias extra), suficientemente
rápido para tamaños típicos, y elimina cualquier ambigüedad. NIST y OWASP lo recomiendan.

### ¿Qué pasa si un archivo supera 100 MB?

GitHub rechaza blobs > 100 MB vía API. El ejecutable los detecta antes del push, los
reporta y los omite, dejándolos disponibles para tratarlos manualmente (por ejemplo con
Git LFS, que está fuera del scope de esta versión).

### ¿Puedo correrlo sin internet?

No. Todas las operaciones que tocan GitHub (`push`, `restore`, `verify` contra repo)
requieren conexión. `status` sí funciona offline porque solo compara local vs cache.

---

## 12. Limitaciones conocidas

- **Solo Windows.** El binario se compila para Windows. El código Python es portable y
  podría usarse desde Mac/Linux con `python -m ghbackup`, pero el subcomando `schedule`
  solo funciona en Windows (usa `schtasks`).
- **Una sola carpeta source por configuración.** Para más, rotar con `config set`.
- **Sin Git LFS.** Archivos > 100 MB se omiten.
- **Sin merge de cambios remotos.** Si dos PCs distintas pushean a la misma rama, la
  segunda corrida puede quedar desactualizada. Esta herramienta está pensada para una
  PC origen única.

---

## 13. Changelog

Cada cambio sobre el código del ejecutable se documenta acá con fecha, hora (UTC) y
descripción de cambios.

### v0.1.0 — 2026-05-11 (estimado)

**Hora UTC:** 18:00

**Cambios — versión inicial:**

- Estructura del proyecto Python con `src/ghbackup/` modularizado (auth, github_io, scanner, state, logging_, commands, ui).
- Implementado `setup` con wizard interactivo paso a paso: master password, instrucciones para generar PAT, validación, selección de repo (siempre privado), definición de carpeta source, definición de rama, confirmación y persistencia.
- Implementado almacenamiento del PAT cifrado con AES-256-GCM derivado por PBKDF2-HMAC-SHA256 (600 000 iteraciones), guardado en `%APPDATA%\GitHubBackup\vault.enc`.
- Implementado motor de detección de cambios usando SHA-256 nativo, con detección de renombres por coincidencia de hash y filtros default tipo `.gitignore` + soporte para `.backupignore` personalizado.
- Implementado push atómico contra la API de GitHub: blobs → tree → commit → ref update → tag annotated, con reintentos exponenciales y rollback total ante cualquier falla.
- Implementados los tres modos de restore (`--file`, `--tag`, `--date`).
- Implementado manifiesto de borrados (`deletion_manifest.json`) que propone restaurar hasta 5 archivos borrados localmente dentro de los últimos 30 días en cada push.
- Implementado logging dual: `operations.jsonl` (CI/CD) + `operations.md` (legible).
- Implementados subcomandos auxiliares: `status`, `log`, `config show/set/rotate-token/reset`, `verify [--rebuild]`, `schedule create/list/remove`.
- Configurado build con PyInstaller (`build.spec` + `build.bat`).
- Documentación completa en este README.
