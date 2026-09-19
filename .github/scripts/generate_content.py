#!/usr/bin/env python3
"""把 open issues 转成 Hugo 站点内容，并提供访问统计数据。

产物：
  site/content/posts/<n>.md      每篇文章的 noindex 跳转页（frontmatter:
                                 title/date/tags/issue/externalURL/summary），
                                 站内列表条目均直链 issue，此页仅兜底旧 URL
  site/layouts/partials/verification.html
                                 Search Console 验证 meta（由 env 控制内容）
  site/data/traffic.json         访问统计数据，页面本体是仓库里的
                                 content/traffic.md + layouts/traffic.html，
                                 由 Hugo 模板统一渲染

文章正文仍外指 GitHub issues（Hugo 只做列表/标签/RSS 的数据源），
content 每次全量重建，已关闭 issue 的旧文件自然清除。

依赖 env：GH_TOKEN、REPO（默认 wudanyang6/wudanyang6.github.io）。
可选 env：GOOGLE_SITE_VERIFICATION。无第三方 Python 依赖（正文与
访问统计页的渲染都交给 Hugo）。
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = os.environ.get("REPO", "wudanyang6/wudanyang6.github.io")
VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITE = Path(os.environ.get("SITE_DIR") or REPO_ROOT / "site")
TRAFFIC_DATA = Path(os.environ.get("TRAFFIC_DATA") or REPO_ROOT / "traffic/history.json")


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


def write_traffic_data():
    """把 traffic 历史数据放进 Hugo data 目录，页面由模板渲染。"""
    out = SITE / "data" / "traffic.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if TRAFFIC_DATA.exists():
        out.write_text(TRAFFIC_DATA.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        # 采集失败或未开始时保证文件存在，模板据此显示"暂无数据"
        out.write_text('{"days": []}', encoding="utf-8")
    print(f"traffic data -> {out}")


def main():
    if "GH_TOKEN" not in os.environ:
        sys.exit("GH_TOKEN is required")
    issues = fetch_issues()
    write_content(issues)
    write_verification_partial()
    write_traffic_data()
    print("done")


if __name__ == "__main__":
    main()
