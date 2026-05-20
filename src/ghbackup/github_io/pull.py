"""Operaciones de lectura desde GitHub para los modos de `restore`."""

from __future__ import annotations

import base64
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone

from github import GithubException
from github.Repository import Repository

from ghbackup.github_io.client import GitHubError


@dataclass
class FileVersion:
    commit_sha: str
    commit_date_utc: str
    message_first_line: str
    tag: str | None  # tag asociado a ese commit, si existe


def list_versions_of_file(repo: Repository, branch: str, rel_path: str) -> list[FileVersion]:
    """Lista los commits que tocaron `rel_path` en `branch`."""
    try:
        commits = repo.get_commits(sha=branch, path=rel_path)
    except GithubException as exc:
        raise GitHubError(f"No se pudo listar versiones de {rel_path}: {exc.data}") from exc

    # mapeo commit_sha → tag
    tag_by_sha: dict[str, str] = {}
    for t in repo.get_tags():
        with contextlib.suppress(GithubException):
            tag_by_sha[t.commit.sha] = t.name

    versions: list[FileVersion] = []
    for c in commits:
        sha = c.sha
        dt = c.commit.committer.date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        versions.append(
            FileVersion(
                commit_sha=sha,
                commit_date_utc=dt.astimezone(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                message_first_line=c.commit.message.splitlines()[0] if c.commit.message else "",
                tag=tag_by_sha.get(sha),
            )
        )
    return versions


def download_file_at_commit(repo: Repository, commit_sha: str, rel_path: str) -> bytes:
    """Descarga el contenido binario de un archivo en un commit específico."""
    try:
        content = repo.get_contents(rel_path, ref=commit_sha)
    except GithubException as exc:
        raise GitHubError(f"No se pudo descargar {rel_path}@{commit_sha[:7]}: {exc.data}") from exc
    # PyGithub devuelve un objeto ContentFile con .content base64
    if isinstance(content, list):
        raise GitHubError(f"{rel_path} es un directorio, no un archivo.")
    return base64.b64decode(content.content)


def find_commit_by_date(repo: Repository, branch: str, date_yyyy_mm_dd: str) -> str:
    """Devuelve el SHA del último commit en `branch` con committer.date <= fecha."""
    try:
        until = datetime.strptime(date_yyyy_mm_dd, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise GitHubError(f"Fecha inválida: {date_yyyy_mm_dd} (usar YYYY-MM-DD)") from exc

    commits = repo.get_commits(sha=branch, until=until)
    try:
        first = next(iter(commits))
    except StopIteration as exc:
        raise GitHubError(f"No hay commits en {branch} antes de {date_yyyy_mm_dd}") from exc
    return first.sha


def list_files_in_commit(repo: Repository, commit_sha: str) -> list[str]:
    """Lista todas las rutas de blobs del tree en ese commit."""
    commit = repo.get_git_commit(commit_sha)
    tree = repo.get_git_tree(commit.tree.sha, recursive=True)
    return [el.path for el in tree.tree if el.type == "blob"]
