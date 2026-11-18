from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from backend.database.db import connect

UA = "UpdateWatch/0.1 (+local Linux update monitor)"
TRUSTED_SOURCE_HOSTS = {
    "discuss.cachyos.org", "www.reddit.com", "reddit.com", "api.github.com",
    "gitlab.freedesktop.org", "archlinux.org", "www.archlinux.org",
}


def validate_source_url(url: str, github: bool = False) -> None:
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in TRUSTED_SOURCE_HOSTS or
            parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("URL de fonte externa não permitida")
    if github and parsed.hostname != "api.github.com":
        raise ValueError("Token GitHub só pode ser enviado à API oficial")


class TrustedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl, github=req.has_header("Authorization"))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, github: bool = False) -> bytes:
    validate_source_url(url, github=github)
    headers = {"User-Agent": UA, "Accept": "application/json, application/atom+xml, application/rss+xml, application/xml"}
    token = os.environ.get("UPDATE_WATCH_GITHUB_TOKEN")
    if github and token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(TrustedRedirectHandler())
    with opener.open(req, timeout=20) as response:
        return response.read(4_000_000)


def child_text(node, *names):
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_feed(payload: bytes) -> list[dict]:
    root = ET.fromstring(payload)
    items = root.findall(".//item") or root.findall("{http://www.w3.org/2005/Atom}entry")
    result = []
    for item in items:
        link = child_text(item, "link")
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.get("href", "") if atom_link is not None else ""
        title = child_text(item, "title") or "(sem título)"
        content = child_text(item, "description", "{http://www.w3.org/2005/Atom}content", "{http://purl.org/rss/1.0/modules/content/}encoded")
        result.append({"external_id": child_text(item, "guid", "id"), "title": title,
                       "content": content[:12000], "author": child_text(item, "author", "{http://www.w3.org/2005/Atom}author"),
                       "published_at": child_text(item, "pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}updated"),
                       "url": link})
    return [item for item in result if item["url"]]


def collect(source: dict) -> list[dict]:
    kind, base = source["kind"], source["url"]
    if kind in ("rss", "reddit"):
        return parse_feed(fetch(base))
    if kind == "discourse":
        data = json.loads(fetch(base.rstrip("/") + "/latest.json").decode())
        result = []
        for topic in data.get("topic_list", {}).get("topics", []):
            slug = urllib.parse.quote(topic.get("slug", ""))
            tid = topic.get("id")
            if tid:
                result.append({"external_id": str(tid), "title": topic.get("title", ""),
                    "content": topic.get("excerpt", ""), "author": topic.get("last_poster_username", ""),
                    "published_at": topic.get("last_posted_at", ""),
                    "resolution": "closed" if topic.get("closed") else "open",
                    "url": f"{base.rstrip('/')}/t/{slug}/{tid}"})
        return result
    if kind in ("github", "github_repo"):
        result = []
        if kind == "github_repo":
            path = urllib.parse.urlparse(base).path.strip("/").split("/")
            if len(path) < 2:
                raise ValueError("URL de repositório GitHub inválida")
            repositories = [(path[0], path[1])]
        else:
            # Official CachyOS repositories; issues and releases.
            repositories = [("CachyOS", repo) for repo in ("cachyos", "CachyOS-PKGBUILDS", "linux-cachyos")]
        for owner, repo in repositories:
            api = f"https://api.github.com/repos/{owner}/{repo}"
            endpoints = ("issues?state=all&per_page=30",) if kind == "github_repo" else (
                "issues?state=all&per_page=20", "releases?per_page=10")
            for endpoint in endpoints:
                try:
                    payload = json.loads(fetch(api + "/" + endpoint, github=True).decode())
                except urllib.error.HTTPError as exc:
                    if exc.code in (404, 410):
                        continue
                    raise
                if not isinstance(payload, list):
                    raise ValueError(f"Resposta inesperada da API GitHub para {owner}/{repo}")
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    if "pull_request" in item:
                        continue
                    issue_url = item.get("html_url")
                    if not issue_url:
                        continue
                    body = item.get("body") or ""
                    user = item.get("user") or {}
                    if not isinstance(body, str):
                        body = str(body)
                    if not isinstance(user, dict):
                        user = {}
                    result.append({"external_id": str(item.get("id", "")),
                        "title": item.get("title") or item.get("name", "(release)"),
                        "content": body[:12000],
                        "author": user.get("login", ""),
                        "published_at": item.get("updated_at") or item.get("published_at", ""),
                        "resolution": ("fixed" if endpoint.startswith("issues") and item.get("state") == "closed"
                                       and item.get("state_reason") == "completed" else
                                       "closed" if endpoint.startswith("issues") and item.get("state") == "closed" else
                                       "open" if endpoint.startswith("issues") else "unknown"),
                        "url": issue_url})
        return result
    if kind == "gitlab":
        path = urllib.parse.urlparse(base).path.strip("/").split("/")
        if len(path) < 2:
            raise ValueError("URL de projeto GitLab inválida")
        project = urllib.parse.quote("/".join(path[:2]), safe="")
        api = f"https://gitlab.freedesktop.org/api/v4/projects/{project}/issues?state=all&per_page=30&order_by=updated_at&sort=desc"
        data = json.loads(fetch(api).decode())
        return [{"external_id": str(item.get("id", "")), "title": item.get("title", ""),
                 "content": (item.get("description") or "")[:12000],
                 "author": (item.get("author") or {}).get("name", ""),
                 "published_at": item.get("updated_at") or item.get("created_at", ""),
                 "resolution": "closed" if item.get("state") == "closed" else "open",
                 "url": item.get("web_url", "")} for item in data if item.get("web_url")]
    raise ValueError("Tipo de fonte não suportado: " + kind)


def sync_all(path=None) -> dict:
    totals, errors = 0, []
    with connect(path) as db:
        sources = [dict(row) for row in db.execute("SELECT * FROM sources WHERE enabled=1")]
    for source in sources:
        try:
            entries = collect(source)
            with connect(path) as db:
                for entry in entries:
                    db.execute("""INSERT INTO publications
                      (source_id,external_id,title,content,author,published_at,url,resolution)
                      VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
                      external_id=excluded.external_id,title=excluded.title,content=excluded.content,
                      author=excluded.author,published_at=excluded.published_at,resolution=excluded.resolution""",
                      (source["id"], entry["external_id"], entry["title"],
                      entry["content"], entry["author"], entry["published_at"], entry["url"],
                      entry.get("resolution", "unknown")))
                db.execute("UPDATE sources SET last_sync=?,last_error=NULL WHERE id=?",
                           (datetime.now(timezone.utc).isoformat(), source["id"]))
            totals += len(entries)
        except Exception as exc:
            message = f"{source['name']}: {str(exc)[:300]}"
            errors.append(message)
            with connect(path) as db:
                db.execute("UPDATE sources SET last_error=? WHERE id=?", (str(exc)[:500], source["id"]))
    return {"received": totals, "errors": errors}
