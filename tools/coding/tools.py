"""tools/coding/tools.py — coding tools: GitHub repo ops, code analysis.

GitHub requires a PAT (minimal scopes). See docs/component-5 §5.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from langchain_core.tools import tool

log = logging.getLogger("don.tools.coding")


@tool
def github_list_repos(
    owner: Optional[str] = None,
    max_results: int = 10,
) -> str:
    """List GitHub repositories for a user or org.

    Args:
        owner: GitHub username or org (default: authenticated user).
        max_results: maximum repos to return.
    """
    try:
        from github import Github

        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return "[github: GITHUB_TOKEN not set in environment]"
        g = Github(token)
        user = g.get_user(owner) if owner else g.get_user()
        repos = sorted(user.get_repos(), key=lambda r: r.updated_at, reverse=True)[:max_results]
        lines = [f"- {r.full_name} ({r.language or 'N/A'}) — {r.description or 'no description'}" for r in repos]
        return "\n".join(lines) if lines else "No repositories found."
    except ImportError:
        return "[github: pygithub not installed. pip install pygithub]"
    except Exception as exc:  # noqa: BLE001
        log.error("github_list_repos failed: %s", exc)
        return f"[github error: {exc}]"


@tool
def github_get_file(
    repo: str,
    path: str,
    branch: str = "main",
) -> str:
    """Read a file from a GitHub repository.

    Args:
        repo: repository in 'owner/repo' format.
        path: file path within the repo.
        branch: branch name (default: main).
    """
    try:
        from github import Github

        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return "[github: GITHUB_TOKEN not set]"
        g = Github(token)
        repository = g.get_repo(repo)
        file_content = repository.get_contents(path, ref=branch)
        if hasattr(file_content, "decoded_content"):
            return file_content.decoded_content.decode("utf-8", errors="replace")[:8192]
        return f"[file too large or is a directory: {path}]"
    except ImportError:
        return "[github: pygithub not installed]"
    except Exception as exc:  # noqa: BLE001
        log.error("github_get_file failed: %s", exc)
        return f"[github error: {exc}]"


@tool
def github_create_issue(
    repo: str,
    title: str,
    body: str = "",
    labels: str = "",
) -> str:
    """Create a GitHub issue.

    Args:
        repo: repository in 'owner/repo' format.
        title: issue title.
        body: issue body (markdown).
        labels: comma-separated label names.
    """
    try:
        from github import Github

        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return "[github: GITHUB_TOKEN not set]"
        g = Github(token)
        repository = g.get_repo(repo)
        label_names = [l.strip() for l in labels.split(",") if l.strip()]
        label_objs = [repository.get_label(name) for name in label_names] if label_names else []
        issue = repository.create_issue(title=title, body=body, labels=label_objs)
        return f"[issue #{issue.number} created: {issue.html_url}]"
    except ImportError:
        return "[github: pygithub not installed]"
    except Exception as exc:  # noqa: BLE001
        log.error("github_create_issue failed: %s", exc)
        return f"[github error: {exc}]"


TOOLS = [github_list_repos, github_get_file, github_create_issue]
