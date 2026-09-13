#!/usr/bin/env python3
"""从 open issues 生成静态博客站点。

产物（写入 ./public/）：
  index.html          文章列表
  posts/<n>.html      每篇文章全文
  feed.xml            RSS 2.0（含全文）
  sitemap.xml         指向站内全部页面
  robots.txt          指向 sitemap

依赖 env：GH_TOKEN、REPO（默认 wudanyang6/wiki）、BASE_URL（Pages 地址）。
可选 env：GOOGLE_SITE_VERIFICATION（Search Console 验证码，注入 meta 标签）。
"""
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import markdown

REPO = os.environ.get("REPO", "wudanyang6/wiki")
BASE_URL = os.environ.get("BASE_URL", "https://wudanyang6.github.io/wiki/").rstrip("/")
SITE_TITLE = os.environ.get("SITE_TITLE", "wudanyang's wiki")
SITE_DESC = "Personal notes on engineering and everyday life"
OUT = Path(os.environ.get("OUT_DIR", "public"))
VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")

CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif;
       max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; }
a { color: inherit; }
h1 a, h2 a { text-decoration: none; }
.meta { color: gray; font-size: 0.9rem; }
.tag { background: color-mix(in srgb, currentColor 12%, transparent);
       border-radius: 1em; padding: 0.1em 0.7em; font-size: 0.85rem; }
pre { overflow-x: auto; padding: 1em; border-radius: 0.5em;
      background: rgba(127,127,127,0.12); }
code { font-size: 0.9em; }
img { max-width: 100%; }
footer { margin-top: 3rem; color: gray; font-size: 0.85rem; }
"""


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


def md_to_html(text):
    return markdown.markdown(text or "", extensions=["fenced_code", "tables", "nl2br"])


def excerpt(body, limit=200):
    """正文纯文本摘要，用于 RSS description 和列表页。"""
    text = "".join(
        line.strip() for line in (body or "").splitlines() if line.strip()
    )
    # 粗去 markdown 标记，够列表展示即可
    for ch in "#*`>[]( #":
        text = text.replace(ch, "")
    return text[:limit] + ("…" if len(text) > limit else "")


def head(title, extra=""):
    meta = (f'<meta name="google-site-verification" content="{VERIFICATION}" />\n'
            if VERIFICATION else "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
{meta}{extra}<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
"""


def render_post(issue):
    """单篇文章页。"""
    n, title = issue["number"], issue["title"]
    created = parse_time(issue["createdAt"])
    tags = " ".join(f'<span class="tag">{html.escape(t)}</span>' for t in
                    sorted(l["name"] for l in issue["labels"]))
    github_link = f"https://github.com/{REPO}/issues/{n}"
    return f"""{head(title)}<article>
<h1>{html.escape(title)}</h1>
<p class="meta">{created.strftime('%Y-%m-%d')} &nbsp; {tags}</p>
{md_to_html(issue['body'])}
</article>
<footer>原文与评论：<a href="{github_link}">issue #{n}</a></footer>
</body>
</html>
"""


def render_index(issues):
    """文章列表页。"""
    items = "\n".join(
        f"""<li>
<a href="posts/{i['number']}.html">{html.escape(i['title'])}</a>
<span class="meta">{parse_time(i['createdAt']).strftime('%Y-%m-%d')}</span>
</li>"""
        for i in issues
    )
    return f"""{head(SITE_TITLE)}<h1><a href="./">{SITE_TITLE}</a></h1>
<p class="meta">{SITE_DESC} · <a href="feed.xml">RSS</a></p>
<ul>
{items}
</ul>
<footer>由 <a href="https://github.com/{REPO}">{REPO}</a> 的 issues 自动生成</footer>
</body>
</html>
"""


def xml_escape(text):
    return html.escape(text, quote=False)


def render_feed(issues):
    """RSS 2.0，含全文（content:encoded）。"""
    now = format_datetime(datetime.now(timezone.utc))
    items = "\n".join(
        f"""    <item>
      <title>{xml_escape(i['title'])}</title>
      <link>{BASE_URL}/posts/{i['number']}.html</link>
      <guid isPermaLink="true">{BASE_URL}/posts/{i['number']}.html</guid>
      <pubDate>{format_datetime(parse_time(i['createdAt']))}</pubDate>
      <description>{xml_escape(excerpt(i['body']))}</description>
      <content:encoded><![CDATA[{md_to_html(i['body'])}]]></content:encoded>
      {''.join(f'<category>{xml_escape(l["name"])}</category>' for l in i['labels'])}
    </item>"""
        for i in issues
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{xml_escape(SITE_TITLE)}</title>
    <link>{BASE_URL}</link>
    <description>{xml_escape(SITE_DESC)}</description>
    <language>zh-CN</language>
    <lastBuildDate>{now}</lastBuildDate>
{items}
  </channel>
</rss>
"""


def render_sitemap(issues):
    """sitemap：首页 + 全部文章页。"""
    urls = [f"""  <url>
    <loc>{BASE_URL}/</loc>
    <changefreq>daily</changefreq>
  </url>"""]
    urls += [
        f"""  <url>
    <loc>{BASE_URL}/posts/{i['number']}.html</loc>
    <lastmod>{parse_time(i['updatedAt']).date()}</lastmod>
  </url>"
""".rstrip('"\n ')
        for i in issues
    ]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
"""


def main():
    if "GH_TOKEN" not in os.environ:
        sys.exit("GH_TOKEN is required")
    issues = fetch_issues()
    print(f"fetched {len(issues)} open issue(s) from {REPO}")

    (OUT / "posts").mkdir(parents=True, exist_ok=True)
    for i in issues:
        (OUT / "posts" / f"{i['number']}.html").write_text(render_post(i), encoding="utf-8")
    (OUT / "index.html").write_text(render_index(issues), encoding="utf-8")
    (OUT / "feed.xml").write_text(render_feed(issues), encoding="utf-8")
    (OUT / "sitemap.xml").write_text(render_sitemap(issues), encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8"
    )
    print(f"site written to {OUT}/")


if __name__ == "__main__":
    main()
