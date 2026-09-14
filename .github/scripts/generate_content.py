#!/usr/bin/env python3
"""把 open issues 转成 Hugo 站点内容，并渲染访问统计静态页。

产物：
  site/content/posts/<n>.md      每篇文章的 headless content
                                 （frontmatter: title/date/tags/issue/
                                  externalURL/summary + build 配置）
  site/layouts/partials/verification.html
                                 Search Console 验证 meta（由 env 控制内容）
  site/static/traffic.html       访问统计报告（独立完整页面，Hugo 原样托管）

文章正文仍外指 GitHub issues（Hugo 只做列表/标签/RSS 的数据源），
content 每次全量重建，已关闭 issue 的旧文件自然清除。

依赖 env：GH_TOKEN、REPO（默认 wudanyang6/wiki）。
可选 env：GOOGLE_SITE_VERIFICATION。无第三方 Python 依赖（正文渲染交给 Hugo）。
"""
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = os.environ.get("REPO", "wudanyang6/wiki")
VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITE = Path(os.environ.get("SITE_DIR") or REPO_ROOT / "site")
TRAFFIC_DATA = Path(os.environ.get("TRAFFIC_DATA") or REPO_ROOT / "traffic/history.json")

TRAFFIC_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif;
       max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; }
a { color: inherit; }
.meta { color: gray; font-size: 0.9rem; }
.bars { display: flex; align-items: flex-end; gap: 2px; height: 120px; margin: 1rem 0; }
.bar { flex: 1; min-height: 2px; background: rgba(127,127,127,0.4);
       border-radius: 2px 2px 0 0; }
.bar:hover { background: rgba(127,127,127,0.7); }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
td, th { padding: 0.3rem 0.6rem; text-align: left; border-bottom: 1px solid rgba(127,127,127,0.25); }
td.num, th.num { text-align: right; }
footer { margin-top: 3rem; color: gray; font-size: 0.85rem; }
"""


def issue_url(n):
    return f"https://github.com/{REPO}/issues/{n}"


def fetch_issues():
    """拉取全部 open issues，按创建时间倒序。"""
    raw = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "open", "--limit", "500",
         "--json", "number,title,body,createdAt,updatedAt,labels"],
        check=True, capture_output=True, text=True,
        env={**os.environ, "GH_TOKEN": os.environ["GH_TOKEN"]},
    ).stdout
    return sorted(json.loads(raw), key=lambda i: i["createdAt"], reverse=True)


def parse_time(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


def excerpt(body, limit=200):
    """正文纯文本摘要。"""
    text = "".join(
        line.strip() for line in (body or "").splitlines() if line.strip()
    )
    for ch in "#*`>[]( #":
        text = text.replace(ch, "")
    return text[:limit] + ("…" if len(text) > limit else "")


def write_content(issues):
    """每篇 issue 写一个 headless content 文件。"""
    posts = SITE / "content" / "posts"
    posts.mkdir(parents=True, exist_ok=True)
    # 全量重建：先清掉旧文件，关闭的 issue 自然移除
    for old in posts.glob("*.md"):
        old.unlink()
    for i in issues:
        front = {
            "title": i["title"],
            # Hugo YAML frontmatter 吃 ISO8601 字符串
            "date": parse_time(i["createdAt"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tags": [l["name"] for l in i["labels"]],
            "issue": i["number"],
            "externalURL": issue_url(i["number"]),
            "summary": excerpt(i["body"]),
        }
        meta = yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
        (posts / f"{i['number']}.md").write_text(
            f"---\n{meta}---\n\n{i['body'] or ''}\n", encoding="utf-8"
        )
    print(f"content: {len(issues)} post(s) -> {posts}")


def write_verification_partial():
    """Search Console 验证 meta；未配置时写占位，保证 partial 恒存在。"""
    p = SITE / "layouts" / "partials" / "verification.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    if VERIFICATION:
        p.write_text(
            f'<meta name="google-site-verification" content="{VERIFICATION}" />\n',
            encoding="utf-8",
        )
    else:
        p.write_text("<!-- google-site-verification not configured -->\n", encoding="utf-8")


def write_traffic_page():
    """访问统计报告页（static 原样托管，独立于 Hugo 模板体系）。"""
    history = (json.loads(TRAFFIC_DATA.read_text(encoding="utf-8"))
               if TRAFFIC_DATA.exists() else {})
    days = history.get("days", [])

    if not days:
        body = "<p class='meta'>暂无访问数据，等待第一次采集。</p>"
    else:
        total_views = sum(d["views"] for d in days)
        total_uniques = sum(d["uniques"] for d in days)
        updated = history.get("updated", "")[:19].replace("T", " ")
        recent = days[-30:]
        peak = max((d["views"] for d in recent), default=1) or 1
        bars = "\n".join(
            f'<div class="bar" style="height:{max(2, round(d["views"] * 100 / peak))}%"'
            f' title="{d["date"]}: {d["views"]} views / {d["uniques"]} uniques"></div>'
            for d in recent
        )
        rows = []
        for p in history.get("paths", []):
            m = re.search(r"issues/(\d+)", p["path"])
            path_html = (f'<a href="{issue_url(m.group(1))}">{html.escape(p["path"])}</a>'
                         if m else html.escape(p["path"]))
            rows.append(
                f"<tr><td>{path_html}</td><td>{html.escape(p.get('title') or '')}"
                f"</td><td class='num'>{p['count']}</td><td class='num'>{p['uniques']}</td></tr>"
            )
        referrers = " · ".join(
            f"{html.escape(r['referrer'])} {r['count']}" for r in history.get("referrers", [])
        )
        body = f"""
<p class="meta">累计浏览 {total_views} 次 · 独立访客 {total_uniques} 人 · 更新于 {updated} UTC</p>
<h2>每日浏览（最近 30 天，悬停看明细）</h2>
<div class="bars">
{bars}
</div>
<p class="meta">{recent[0]['date']} ~ {recent[-1]['date']}</p>
<h2>热门内容（GitHub 近 14 天快照）</h2>
<table>
<tr><th>路径</th><th>标题</th><th class="num">浏览</th><th class="num">访客</th></tr>
{chr(10).join(rows)}
</table>
<h2>来源（近 14 天）</h2>
<p class="meta">{referrers or '（无）'}</p>
<p class="meta">注：每日趋势自首次采集日起累积；热门内容为 GitHub Traffic API 的
14 天滑动窗口，不含更早历史。文章页在 github.com 上，由 GitHub 统计。</p>
"""

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>访问统计 · wudanyang's wiki</title>
<style>{TRAFFIC_CSS}</style>
</head>
<body>
<h1>访问统计</h1>
<p class="meta"><a href="../">← wudanyang's wiki</a></p>
{body}
<footer>由 GitHub Actions 自动生成</footer>
</body>
</html>
"""
    out = SITE / "static" / "traffic.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"traffic page -> {out}")


def main():
    if "GH_TOKEN" not in os.environ:
        sys.exit("GH_TOKEN is required")
    issues = fetch_issues()
    write_content(issues)
    write_verification_partial()
    write_traffic_page()
    print("done")


if __name__ == "__main__":
    main()
