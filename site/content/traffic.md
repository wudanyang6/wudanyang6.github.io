---
# 页面主体由 layouts/traffic.html 渲染（数据来自 site/data/traffic.json），
# 这里只提供路由与元信息
title: 访问统计
url: traffic.html  # 保持既有地址，避免外链失效
layout: traffic
# 别加 build.list: false——那会让本页从 sitemap 消失；不进列表/RSS 由模板按 section 过滤保证
---
