"""Push atómico: construye un commit único con todos los cambios y lo taggea.

Si cualquier paso falla, NO se actualiza la ref del branch, por lo que el repo
queda en su estado anterior y el cache local no se modifica.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from github import GithubException, InputGitTreeElement
from github.Repository import Repository

from ghbackup.github_io.client import GitHubError

_INVALID_TAG_CHARS = re.compile(r"[\s\^~:?*\[\\]")


@dataclass
class PushResult:
    commit_sha: str
    commit_url: str
    tag_name: str
    tag_url: str
    branch: str
    bytes_uploaded: int


def sanitize_tag(name: str) -> str:
    """Reemplaza espacios por _ y elimina caracteres inválidos para refs de Git."""
    name = name.strip()
    name = _INVALID_TAG_CHARS.sub("_", name)
    name = name.replace("..", "_").strip("/").strip(".")
    return name or "wds_untitled"


def auto_tag_name(source_root: Path) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{source_root.name}_{ts}"


def ensure_unique_tag(repo: Repository, tag_name: str) -> str:
    """Si el tag ya existe, agrega sufijo _2, _3, ..."""
    existing = {t.name for t in repo.get_tags()}
    if tag_name not in existing:
        return tag_name
    i = 2
    while f"{tag_name}_{i}" in existing:
        i += 1
    return f"{tag_name}_{i}"


def ensure_branch(repo: Repository, branch: str, base_sha: str | None = None) -> str:
    """Asegura que el branch exista; si no, lo crea desde el default branch.

    Devuelve el SHA del head actual del branch.
    """
    try:
        ref = repo.get_git_ref(f"heads/{branch}")
        return ref.object.sha
    except GithubException:
        # crear desde default branch
        default = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch}", sha=default.commit.sha)
        return default.commit.sha


def _file_to_blob(repo: Repository, abs_path: Path) -> str:
    """Sube el contenido binario del archivo como blob y devuelve su SHA."""
    data = abs_path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    blob = repo.create_git_blob(content=encoded, encoding="base64")
    return blob.sha


def atomic_push(
    repo: Repository,
    branch: str,
    *,
    upserts: list[tuple[str, Path]],  # [(rel_path, abs_path), ...]
    renames: list[tuple[str, str, Path]],  # [(old_rel, new_rel, new_abs_path), ...]
    local_deletions: list[str],  # rel paths borrados localmente (solo se anotan, no se borran)
    commit_message: str,
    tag_name: str,
    tag_message: str,
    max_retries: int = 3,
) -> PushResult:
    """Construye y empuja un commit + tag de forma atómica.

    Política importante: los borrados locales NO se materializan como deleciones
    en Git. Solo se mencionan en el mensaje del commit como `[Local-deleted: ...]`.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return _do_push(
                repo,
                branch,
                upserts=upserts,
                renames=renames,
                local_deletions=local_deletions,
                commit_message=commit_message,
                tag_name=tag_name,
                tag_message=tag_message,
            )
        except (TimeoutError, GithubException, ConnectionError) as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(2**attempt)
            continue
    raise GitHubError(f"Push falló tras {max_retries} intentos: {last_exc}") from last_exc


def _do_push(
    repo: Repository,
    branch: str,
    *,
    upserts: list[tuple[str, Path]],
    renames: list[tuple[str, str, Path]],
    local_deletions: list[str],
    commit_message: str,
    tag_name: str,
    tag_message: str,
) -> PushResult:
    # 1. Asegurar branch
    base_sha = ensure_branch(repo, branch)
    base_commit = repo.get_git_commit(base_sha)

    # 2. Crear blobs
    tree_elements: list[InputGitTreeElement] = []
    bytes_uploaded = 0
    for rel_path, abs_path in upserts:
        blob_sha = _file_to_blob(repo, abs_path)
        bytes_uploaded += abs_path.stat().st_size
        tree_elements.append(
            InputGitTreeElement(path=rel_path, mode="100644", type="blob", sha=blob_sha)
        )

    for _old_rel, new_rel, new_abs in renames:
        blob_sha = _file_to_blob(repo, new_abs)
        bytes_uploaded += new_abs.stat().st_size
        # nuevo path con nuevo contenido
        tree_elements.append(
            InputGitTreeElement(path=new_rel, mode="100644", type="blob", sha=blob_sha)
        )
        # NO borramos el path viejo: política del usuario es "el repo nunca borra"

    if not tree_elements and not local_deletions:
        raise GitHubError("Nada para pushear.")

    # 3. Crear nuevo tree basado en el anterior (incremental)
    new_tree = repo.create_git_tree(tree=tree_elements, base_tree=base_commit.tree)

    # 4. Crear commit
    full_message = commit_message
    if local_deletions:
        full_message += "\n\n[Borrados localmente — NO eliminados del repositorio]\n"
        for p in local_deletions:
            full_message += f"- {p}\n"

    new_commit = repo.create_git_commit(
        message=full_message,
        tree=new_tree,
        parents=[base_commit],
    )

    # 5. Actualizar la ref del branch (este es el "punto de no retorno")
    ref = repo.get_git_ref(f"heads/{branch}")
    ref.edit(sha=new_commit.sha, force=False)

    # 6. Crear tag annotated
    tag_obj = repo.create_git_tag(
        tag=tag_name,
        message=tag_message or commit_message,
        object=new_commit.sha,
        type="commit",
    )
    repo.create_git_ref(ref=f"refs/tags/{tag_name}", sha=tag_obj.sha)

    commit_url = f"{repo.html_url}/commit/{new_commit.sha}"
    tag_url = f"{repo.html_url}/releases/tag/{tag_name}"
    return PushResult(
        commit_sha=new_commit.sha,
        commit_url=commit_url,
        tag_name=tag_name,
        tag_url=tag_url,
        branch=branch,
        bytes_uploaded=bytes_uploaded,
    )
