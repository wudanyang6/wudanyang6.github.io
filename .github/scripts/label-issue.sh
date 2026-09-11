#!/usr/bin/env bash
# 给 issue 打技术标签：读 issue -> pi 单轮调用 DeepSeek 分类 -> create-if-missing + add-label
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
  cat "$script_dir/label-prompt.md"
  printf '\nExisting labels in this repository (prefer these when they fit):\n\n%s\n\n' "$existing_labels"
  printf 'Issue title: %s\n\nIssue body:\n\n%s\n' "$title" "$body"
} > "$prompt_file"

# 4. pi 单轮调用完成分类（-p 打印模式输出回复后退出，-na 跳过项目信任）
output=$(pi -p -na --model "$MODEL" "$(cat "$prompt_file")")
echo "pi output: $output"

# 5. 解析标签列表，三级宽容提取：纯 JSON -> 剥 ``` 围栏 -> 单行提取 {.*}
#    模型即使被要求 JSON only 也可能带说明文字，全部失败才报错，红叉可查
extract_labels() {
  local text="$1"
  jq -er '.labels[]?' <<<"$text" 2>/dev/null && return 0
  jq -er '.labels[]?' <<<"$(sed '/^```/d' <<<"$text")" 2>/dev/null && return 0
  jq -er '.labels[]?' <<<"$(grep -o '{.*}' <<<"$text" | head -1)" 2>/dev/null && return 0
  return 1
}
labels=$(extract_labels "$output") || {
  echo "::error::Failed to parse labels from pi output"
  exit 1
}

# 6. 逐个打标签：规整格式、create-if-missing、上限 5 个
added=0
while IFS= read -r label && [ "$added" -lt 5 ]; do
  # 小写、空格转连字符、只留合法字符
  label=$(tr '[:upper:] ' '[:lower:]-' <<<"$label" | tr -cd 'a-z0-9-')
  [ -z "$label" ] && continue

  if ! grep -qx "$label" <<<"$existing_labels"; then
    gh label create "$label" --repo "$repo" --color c5def5 2>/dev/null || true
  fi
  gh issue edit "$issue_number" --repo "$repo" --add-label "$label"
  echo "Added label: $label"
  added=$((added + 1))
done <<<"$labels"

echo "Done: added $added label(s) to issue #$issue_number"
