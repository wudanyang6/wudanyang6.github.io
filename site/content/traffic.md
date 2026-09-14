---
# 页面主体由 layouts/page/traffic.html 渲染（数据来自 site/data/traffic.json），
# 这里只提供路由与元信息
title: 访问统计
url: traffic.html  # 保持既有地址，避免外链失效
layout: traffic
_build:
  list: false  # 统计页不进首页文章列表与 RSS
  render: true
---
