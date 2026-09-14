#!/usr/bin/env python3
"""拉取 GitHub Traffic 快照，合并进 traffic/history.json。

- 每日 views/uniques：views API 的按天数据是权威值，按日期去重合并，
  形成可长期保留的趋势序列
- 热门路径 / 来源：API 只提供当前快照（近 14 天窗口），整体覆盖存储

依赖 env：GH_TOKEN（需仓库 push 权限）、REPO。
退出码 1 时表示拉取失败，调用方应容忍（数据缺席只影响报告页，不影响站点）。
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ.get("REPO", "wudanyang6/wiki")
# 数据文件相对脚本位置解析（.github/scripts/ -> 仓库根），不依赖运行时 cwd
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = Path(os.environ.get("TRAFFIC_DATA") or REPO_ROOT / "traffic/history.json")


def gh_api(endpoint):
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/{endpoint}"],
            check=True, capture_output=True, text=True,
            env={**os.environ, "GH_TOKEN": os.environ["GH_TOKEN"]},
        )
    except subprocess.CalledProcessError as e:
        # stderr 里有 HTTP 状态与错误 message，必须让它出现在 CI 日志里
        sys.exit(f"gh api {endpoint} failed ({e.returncode}): {e.stderr.strip()}")
    return json.loads(result.stdout)


def main():
    if "GH_TOKEN" not in os.environ:
        sys.exit("GH_TOKEN is required")

    history = {"days": [], "paths": [], "referrers": [], "updated": None}
    if DATA.exists():
        history.update(json.loads(DATA.read_text(encoding="utf-8")))

    # 每日 views：timestamp 精确到小时，取日期做键，后写覆盖前写
    views = gh_api("traffic/views?per=day")
    days = {d["date"]: d for d in history.get("days", [])}
    for v in views.get("views", []):
        date = v["timestamp"][:10]
        days[date] = {"date": date, "views": v["count"], "uniques": v["uniques"]}
    history["days"] = sorted(days.values(), key=lambda d: d["date"])

    # 快照类数据：整体覆盖（API 只给当前窗口）
    history["paths"] = gh_api("traffic/popular/paths")
    history["referrers"] = gh_api("traffic/popular/referrers")
    history["updated"] = datetime.now(timezone.utc).isoformat()

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"traffic history updated: {len(history['days'])} days, "
          f"{len(history['paths'])} popular paths -> {DATA}")


if __name__ == "__main__":
    main()
