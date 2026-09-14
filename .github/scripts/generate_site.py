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
import re
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
# 数据文件相对脚本位置解析（.github/scripts/ -> 仓库根），不依赖运行时 cwd
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRAFFIC_DATA = Path(os.environ.get("TRAFFIC_DATA") or REPO_ROOT / "traffic/history.json")
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
.bars {{ display: flex; align-items: flex-end; gap: 2px; height: 120px; margin: 1rem 0; }}
.bar {{ flex: 1; min-height: 2px; background: rgba(127,127,127,0.4);
       border-radius: 2px 2px 0 0; }}
.bar:hover {{ background: rgba(127,127,127,0.7); }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
td, th {{ padding: 0.3rem 0.6rem; text-align: left; border-bottom: 1px solid rgba(127,127,127,0.25); }}
td.num, th.num {{ text-align: right; }}
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
<p class="meta">{SITE_DESC} · <a href="feed.xml">RSS</a> · <a href="traffic.html">访问统计</a></p>
<ul>
{items}
</ul>
<footer>由 <a href="https://github.com/{REPO}">{REPO}</a> 的 issues 自动生成，正文与评论均在 GitHub<br/>
<span id="busuanzi_container_site_pv" class="meta">本站总访问量 <span id="busuanzi_site_pv"></span> 次 · 总访客 <span id="busuanzi_site_uv"></span> 人</span></footer>
<script async src="https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js"></script>
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


def link_path(path):
    """热门路径转链接：issue 页链接化，其余保持文本。"""
    m = re.search(r"issues/(\d+)", path)
    if m:
        n = m.group(1)
        return f'<a href="{issue_url(n)}">{html.escape(path)}</a>'
    return html.escape(path)


def render_traffic(history):
    """访问统计报告页。

    数据口径：
    - 每日 views/uniques —— 自己累积的历史序列（首次采集日起）
    - 热门路径/来源 —— GitHub Traffic 当前快照（仅近 14 天）
    """
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
        rows = "\n".join(
            f"<tr><td>{link_path(p['path'])}</td><td>{html.escape(p.get('title') or '')}"
            f"</td><td class='num'>{p['count']}</td><td class='num'>{p['uniques']}</td></tr>"
            for p in history.get("paths", [])
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
{rows}
</table>
<h2>来源（近 14 天）</h2>
<p class="meta">{referrers or '（无）'}</p>
<p class="meta">注：每日趋势自首次采集日起累积；热门内容为 GitHub Traffic API 的
14 天滑动窗口，不含更早历史。文章页在 github.com 上，由 GitHub 统计；
Pages 首页另由不蒜子计数。</p>
"""
    return f"""{head("访问统计 · " + SITE_TITLE)}<h1>访问统计</h1>
<p class="meta"><a href="./">← {SITE_TITLE}</a></p>
{body}
</body>
</html>
"""


def main():
    if "GH_TOKEN" not in os.environ:
        sys.exit("GH_TOKEN is required")
    issues = fetch_issues()
    print(f"fetched {len(issues)} open issue(s) from {REPO}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render_index(issues), encoding="utf-8")
    (OUT / "feed.xml").write_text(render_feed(issues), encoding="utf-8")
    history = (json.loads(TRAFFIC_DATA.read_text(encoding="utf-8"))
               if TRAFFIC_DATA.exists() else {})
    (OUT / "traffic.html").write_text(render_traffic(history), encoding="utf-8")
    print(f"index + feed + traffic written to {OUT}/")


if __name__ == "__main__":
    main()
