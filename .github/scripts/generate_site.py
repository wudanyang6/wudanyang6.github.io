#!/usr/bin/env python3
"""从 open issues 生成博客索引页与 RSS。

GitHub issues 是唯一内容源：文章正文、评论都在 GitHub 上，
本脚本只生成两个文件——

  index.html   文章列表（链接直接指向 GitHub issues）
  feed.xml     RSS 2.0（全文输出，标题链接指向 GitHub issues）

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


def head(title):
    meta = (f'<meta name="google-site-verification" content="{VERIFICATION}" />\n'
            if VERIFICATION else "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
{meta}<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif;
       max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; }}
a {{ color: inherit; }}
h1 a {{ text-decoration: none; }}
.meta {{ color: gray; font-size: 0.9rem; }}
.tag {{ background: rgba(127,127,127,0.15);
       border-radius: 1em; padding: 0.1em 0.7em; font-size: 0.85rem; }}
footer {{ margin-top: 3rem; color: gray; font-size: 0.85rem; }}
</style>
</head>
<body>
"""


def render_index(issues):
    """文章列表页，链接直接指向 GitHub issues。"""
    items = "\n".join(
        f"""<li>
<a href="{issue_url(i['number'])}">{html.escape(i['title'])}</a>
<span class="meta">{parse_time(i['createdAt']).strftime('%Y-%m-%d')}</span>
</li>"""
        for i in issues
    )
    return f"""{head(SITE_TITLE)}<h1><a href="./">{SITE_TITLE}</a></h1>
<p class="meta">{SITE_DESC} · <a href="feed.xml">RSS</a></p>
<ul>
{items}
</ul>
<footer>由 <a href="https://github.com/{REPO}">{REPO}</a> 的 issues 自动生成，正文与评论均在 GitHub</footer>
</body>
</html>
"""


def xml_escape(text):
    return html.escape(text, quote=False)


def render_feed(issues):
    """RSS 2.0：标题链接指向 GitHub issues，正文全文内嵌。"""
    now = format_datetime(datetime.now(timezone.utc))
    items = "\n".join(
        f"""    <item>
      <title>{xml_escape(i['title'])}</title>
      <link>{issue_url(i['number'])}</link>
      <guid isPermaLink="true">{issue_url(i['number'])}</guid>
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


def main():
    if "GH_TOKEN" not in os.environ:
        sys.exit("GH_TOKEN is required")
    issues = fetch_issues()
    print(f"fetched {len(issues)} open issue(s) from {REPO}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render_index(issues), encoding="utf-8")
    (OUT / "feed.xml").write_text(render_feed(issues), encoding="utf-8")
    print(f"index + feed written to {OUT}/")


if __name__ == "__main__":
    main()
