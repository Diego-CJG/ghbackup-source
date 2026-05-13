"""Cliente delgado sobre PyGithub.

Encapsula la creación del Github(), el test de conexión y la obtención de repo + branch.
"""

from __future__ import annotations

from dataclasses import dataclass

from github import Auth, Github, GithubException
from github.AuthenticatedUser import AuthenticatedUser
from github.Repository import Repository


@dataclass
class ConnectionInfo:
    login: str
    name: str
    email: str
    avatar_url: str


class GitHubError(Exception):
    """Error genérico al hablar con la API de GitHub."""


def make_client(token: str) -> Github:
    return Github(auth=Auth.Token(token), per_page=100)


def test_connection(token: str) -> ConnectionInfo:
    """Valida el token llamando a GET /user. Devuelve info de la cuenta."""
    try:
        gh = make_client(token)
        user: AuthenticatedUser = gh.get_user()
        return ConnectionInfo(
            login=user.login,
            name=user.name or "",
            email=user.email or "",
            avatar_url=user.avatar_url or "",
        )
    except GithubException as exc:
        raise GitHubError(f"Token inválido o sin permisos: {exc.data}") from exc
    except Exception as exc:  # noqa: BLE001
        raise GitHubError(f"No se pudo conectar a GitHub: {exc}") from exc


def list_writable_repos(token: str) -> list[Repository]:
    """Lista repos donde el usuario autenticado tiene permiso de push."""
    gh = make_client(token)
    user = gh.get_user()
    repos: list[Repository] = []
    for r in user.get_repos(affiliation="owner,collaborator,organization_member"):
        try:
            perm = r.permissions
            if perm and (perm.push or perm.admin):
                repos.append(r)
        except GithubException:
            continue
    return repos


def get_repo(token: str, full_name: str) -> Repository:
    gh = make_client(token)
    try:
        return gh.get_repo(full_name)
    except GithubException as exc:
        raise GitHubError(f"No se pudo acceder al repo {full_name}: {exc.data}") from exc


def create_private_repo(token: str, name: str, description: str = "") -> Repository:
    """Crea un repo privado en la cuenta del usuario autenticado."""
    gh = make_client(token)
    user = gh.get_user()
    try:
        return user.create_repo(
            name=name,
            description=description or "Repositorio de respaldo automático (ghbackup)",
            private=True,
            auto_init=True,
        )
    except GithubException as exc:
        raise GitHubError(f"No se pudo crear el repo: {exc.data}") from exc


def list_branches(repo: Repository) -> list[str]:
    return [b.name for b in repo.get_branches()]


def list_tags(repo: Repository) -> list[str]:
    return [t.name for t in repo.get_tags()]
