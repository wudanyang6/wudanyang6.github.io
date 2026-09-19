#!/usr/bin/env bash
# 给 issue 打技术标签 + 内容审核：读 issue -> pi 单轮分类审核 -> 打标签 + 问题评论
# 依赖 env: GH_TOKEN, DEEPSEEK_API_KEY, ISSUE_NUMBER, GITHUB_REPOSITORY, MODEL
# 依赖命令: gh, jq, pi（npm install -g @earendil-works/pi-coding-agent）
set -euo pipefail

repo="$GITHUB_REPOSITORY"
issue_number="$ISSUE_NUMBER"
script_dir=$(cd "$(dirname "$0")" && pwd)

# 0. 部署 pi 的 DeepSeek provider 配置（apiKey 用 env 引用，密钥不落盘）
#    CI runner 一次性环境直接写；本地已有配置则跳过，不覆盖
pi_config="$HOME/.pi/agent/models.json"
if [ "${CI:-}" = "true" ] || [ ! -f "$pi_config" ]; then
  mkdir -p "$(dirname "$pi_config")"
  cp "$script_dir/../pi/models.json" "$pi_config"
fi

# 1. 取 issue 内容（用 gh 读，不把 webhook payload 内插进 shell，防注入）
issue_json=$(gh issue view "$issue_number" --repo "$repo" --json title,body)
title=$(jq -r '.title' <<<"$issue_json")
# 超长正文截断，控制 token 成本
body=$(jq -r '.body // ""' <<<"$issue_json" | head -c 20000)

# 2. 现有标签：一行一个，既供模型复用，也用于 create-if-missing 判断
existing_labels=$(gh label list --repo "$repo" --limit 200 --json name --jq '.[].name')

# 3. 拼 prompt：静态规则文件 + 动态上下文（printf %s 原样输出，防内容转义）
prompt_file=$(mktemp)
{
  cat "$script_dir/label-prompt.md" "$script_dir/review-prompt.md"
  printf '\nExisting labels in this repository (prefer these when they fit):\n\n%s\n\n' "$existing_labels"
  printf 'Issue title: %s\n\nIssue body:\n\n%s\n' "$title" "$body"
} > "$prompt_file"

# 4. pi 单轮调用完成分类 + 审核（-p 打印模式输出回复后退出，-na 跳过项目信任）
output=$(pi -p -na --model "$MODEL" "$(cat "$prompt_file")")
echo "pi output: $output"

# 5. 解析结果，三级宽容提取：纯 JSON -> 剥 ``` 围栏 -> 单行提取 {.*}
#    模型即使被要求 JSON only 也可能带说明文字，全部失败才报错，红叉可查
extract_json() {
  local text="$1"
  jq -er '.' <<<"$text" 2>/dev/null && return 0
  jq -er '.' <<<"$(sed '/^```/d' <<<"$text")" 2>/dev/null && return 0
  jq -er '.' <<<"$(grep -o '{.*}' <<<"$text")" 2>/dev/null && return 0
  return 1
}
content=$(extract_json "$output") || {
  echo "::error::Failed to parse result from pi output"
  exit 1
}

# 6. 打标签：规整格式、create-if-missing、上限 5 个
added=0
while IFS= read -r label && [ "$added" -lt 5 ]; do
  # 规整：ASCII 转小写、空白转连字符、去首尾连字符
  # 用 jq 而非 tr：tr 是字节级操作会删掉中文等非 ASCII 字符
  label=$(jq -rR 'ascii_downcase | gsub("\\s+"; "-") | gsub("^-+|-+$"; "")' <<<"$label")
  [ -z "$label" ] && continue

  if ! grep -qx "$label" <<<"$existing_labels"; then
    gh label create "$label" --repo "$repo" --color c5def5 2>/dev/null || true
  fi
  gh issue edit "$issue_number" --repo "$repo" --add-label "$label"
  echo "Added label: $label"
  added=$((added + 1))
done < <(jq -r '.labels[]?' <<<"$content")

echo "Done: added $added label(s) to issue #$issue_number"

# 7. 审核结果：有问题时评论告知；评论带规范化标记，相同结论只评一次
#    （issue 反复编辑触发多次运行，避免重复刷屏）
#    判断依据是 problems 数量而非 status 字符串——模型对枚举值的输出不完全可靠
review_json=$(jq -c '.review // empty' <<<"$content")
problem_count=$(jq -r '.problems // [] | length' <<<"$review_json" 2>/dev/null || echo 0)
if [ "${problem_count:-0}" -eq 0 ]; then
  echo "Review: pass, no comment needed"
  exit 0
fi

# 查重标记：规范化 problems 的 JSON，作为 HTML 注释藏在评论末尾
marker="issue-review:$(jq -cS '.problems' <<<"$review_json")"

existing_comments=$(gh issue view "$issue_number" --repo "$repo" --json comments --jq '[.comments[].body] | join("\n")')
if grep -qF "<!-- $marker -->" <<<"$existing_comments"; then
  echo "Review: unchanged problems, skip duplicate comment"
  exit 0
fi

category_cn() {
  case "$1" in
    secrets) echo "密钥泄露" ;;
    security) echo "安全性问题" ;;
    inappropriate-wording) echo "措辞不当" ;;
    political) echo "政治敏感" ;;
    porn) echo "涉黄" ;;
    gambling) echo "涉赌" ;;
    *) echo "$1" ;;
  esac
}

comment_file=$(mktemp)
{
  echo "⚠️ **内容审核发现以下问题**（自动审核，[Issue Labeler](https://github.com/wudanyang6/wudanyang6.github.io/actions/workflows/issue-labeler.yml)）"
  echo ""
  n=0
  while IFS= read -r problem; do
    n=$((n + 1))
    category=$(jq -r '.category' <<<"$problem")
    quote=$(jq -r '.quote' <<<"$problem")
    reason=$(jq -r '.reason' <<<"$problem")
    suggestion=$(jq -r '.suggestion' <<<"$problem")
    echo "$n. **$(category_cn "$category")**（${category}）"
    echo "   > $quote"
    echo "   - 原因：$reason"
    echo "   - 建议：$suggestion"
    echo ""
  done < <(jq -c '.problems[]?' <<<"$review_json")
  echo "<!-- $marker -->"
} > "$comment_file"

gh issue comment "$issue_number" --repo "$repo" --body-file "$comment_file"
echo "Review: commented with $(jq '.problems | length' <<<"$review_json") problem(s)"
