#!/usr/bin/env python3
"""Regenerate the repository table in README.md from the GitHub API.

Rewrites everything between the START_SECTION:repos / END_SECTION:repos markers.
Run by .github/workflows/profile-stats.yml on a daily schedule.

Environment:
    GITHUB_USER   GitHub login to summarise      (default: Amritmatti)
    GITHUB_TOKEN  token used only to raise the API rate limit (optional)
    README_PATH   file to rewrite                (default: README.md)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER = os.environ.get("GITHUB_USER", "Amritmatti")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = os.environ.get("README_PATH", "README.md")

START = "<!--START_SECTION:repos-->"
END = "<!--END_SECTION:repos-->"

API = "https://api.github.com"

# Repos that are placeholders, scratch space or the profile repo itself.
SKIP = {USER.lower(), "test", "codex"}


def api_get(url):
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", f"{USER}-profile-readme")
    if TOKEN:
        request.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_repos():
    repos = []
    page = 1
    while True:
        batch = api_get(f"{API}/users/{USER}/repos?per_page=100&page={page}&type=owner")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def humanise(iso):
    """Turn an ISO timestamp into 'today' / '3 days ago' / 'Mar 2024'."""
    when = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - when).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        return f"{days // 30} months ago"
    return when.strftime("%b %Y")


def build_table(repos):
    sources = [
        r for r in repos
        if not r["fork"] and not r["archived"] and r["name"].lower() not in SKIP
    ]
    # Most-starred first, then most recently worked on (sorts are stable).
    sources.sort(key=lambda r: r["pushed_at"], reverse=True)
    sources.sort(key=lambda r: r["stargazers_count"], reverse=True)

    if not sources:
        return "_No public source repositories yet._"

    lines = [
        "| Repository | Description | Language | Stars | Last Push |",
        "|:--|:--|:--|--:|:--|",
    ]
    for repo in sources:
        name = repo["name"]
        desc = (repo["description"] or "-").replace("|", "\\|").strip()
        if len(desc) > 90:
            desc = desc[:87].rstrip() + "..."
        lang = repo["language"] or "-"
        stars = repo["stargazers_count"]
        pushed = humanise(repo["pushed_at"])
        lines.append(
            f"| [`{name}`](https://github.com/{USER}/{name}) | {desc} | {lang} | {stars} | {pushed} |"
        )

    total_stars = sum(r["stargazers_count"] for r in sources)
    total_forks = sum(r["forks_count"] for r in sources)
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    lines.append("")
    lines.append(
        f"<sub><b>{len(sources)}</b> source repositories &middot; "
        f"<b>{total_stars}</b> stars &middot; <b>{total_forks}</b> forks &middot; "
        f"last refreshed {stamp}</sub>"
    )
    return "\n".join(lines)


def main():
    try:
        repos = fetch_repos()
    except urllib.error.URLError as exc:
        print(f"::error::GitHub API request failed: {exc}", file=sys.stderr)
        return 1

    table = build_table(repos)

    with open(README, encoding="utf-8") as handle:
        content = handle.read()

    if START not in content or END not in content:
        print(f"::error::markers {START} / {END} not found in {README}", file=sys.stderr)
        return 1

    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        f"{START}\n{table}\n{END}",
        content,
        flags=re.DOTALL,
    )

    if updated == content:
        print("Repository table already up to date.")
        return 0

    with open(README, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    print(f"Repository table updated ({len(repos)} repos scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
