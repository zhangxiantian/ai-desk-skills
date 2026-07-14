---
name: yuanqi-wallpaper-crawler
description: >
  Crawls wallpapers from 元气桌面/海鸟壁纸 (wallpaper.zhhainiao.com), covering both
  live (动态) and static (静态) wallpapers across 14+ and 13+ categories respectively.
  Outputs structured JSON data files (live_wallpaper_data.json, static_wallpaper_data.json).
  Use when the user asks to crawl, refresh, or update wallpaper data from 元气桌面/海鸟壁纸
  or when wallpaper data files need to be regenerated.
when-to-use: >
  User requests to crawl or update wallpaper data from 元气桌面, 海鸟壁纸,
  or zhhainiao.com. Trigger keywords include: 元气壁纸, 海鸟壁纸, 动态壁纸爬取,
  静态壁纸爬取, wallpaper crawl, 更新壁纸数据, crawl zhhainiao.
allowed-tools:
  - execute_command
  - read_file
  - write_to_file
disable: false
---

# 元气桌面 / 海鸟壁纸数据爬取 Skill

## 前提条件

- 工作目录必须在项目根目录（`ai-desk/`）
- Python 3.8+ 已安装
- 需要网络访问 `pcwallpaper.zhhainiao.com`

## 概述

从海鸟壁纸（`zhhainiao.com`，又名元气桌面）平台爬取壁纸数据，生成结构化的 JSON 文件。数据直接通过内存 → JSON 一步到位，不依赖数据库。

**数据覆盖范围**：
- **动态壁纸 (Live)**：14 个分类，含 PC + Mobile 双端详情
- **静态壁纸 (Static)**：13 个分类，列表数据即完整详情

## 输出文件

| 文件 | 说明 |
|------|------|
| `result/live_wallpaper_data.json` | 动态壁纸数据（含 PC + Mobile 详情） |
| `result/static_wallpaper_data.json` | 静态壁纸数据（列表即完整详情） |

## 工作流程

> **注意**：所有命令均在项目根目录（`ai-desk/`）下执行。

### 第 1 步：安装依赖

```bash
cd ai-desk-skills/yuanqi-wallpaper-crawler/scripts
pip install -r requirements.txt
```

### 第 2 步：执行爬取

**完整爬取（推荐）**：
```bash
cd ai-desk-skills/yuanqi-wallpaper-crawler/scripts
python crawler.py
```

**仅爬取动态壁纸**：
```bash
cd ai-desk-skills/yuanqi-wallpaper-crawler/scripts
python crawler.py --live
```

**仅爬取静态壁纸**：
```bash
cd ai-desk-skills/yuanqi-wallpaper-crawler/scripts
python crawler.py --static
```

**测试模式（每分类限 3 页，减少延迟）**：
```bash
cd ai-desk-skills/yuanqi-wallpaper-crawler/scripts
python crawler.py --max-pages 3 --delay 0.2
```

**仅爬取列表，跳过详情（更快）**：
```bash
cd ai-desk-skills/yuanqi-wallpaper-crawler/scripts
python crawler.py --live --skip-detail
```

### 第 3 步：验证输出

爬取完成后，检查 `result/` 目录下的 JSON 文件是否生成成功，确认数据完整性。

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|------|
| `--live` | 仅爬取动态壁纸 | - |
| `--static` | 仅爬取静态壁纸 | - |
| `--max-pages N` | 每分类最大页数 (0=不限制) | 0 |
| `--max-empty-pages N` | 连续空页上限 | 3 |
| `--delay N` | 请求间隔(秒) | 0.5 |
| `--skip-detail` | 仅爬列表，跳过详情 (仅对 Live 有效) | - |

## 核心流程

```
1. 爬取列表 (14个Live分类 / 13个Static分类)
   ├── offset 分页: 精选类
   └── page 分页: 其余分类

2. 爬取详情
   ├── Live: PC详情 + Mobile详情 (逐壁纸)
   └── Static: 列表数据即完整详情 (无需额外请求)

3. 组装 JSON
   ├── 核心字段遴选
   ├── 重复壁纸按分类合并
   └── 按ID排序 + 去重
```

## JSON 数据结构

### Live (动态壁纸)

```json
{
  "type": "live",
  "categories": [
    {"id": 1, "name": "精选"},
    {"id": 2, "name": "最新"}
  ],
  "wallpapers": [
    {
      "wallpaper_id": 123456,
      "categories": [{"id": 1, "name": "精选"}],
      "created_time": "2026-07-05 04:19:00",
      "weight": 123,
      "pc_detail": {
        "name": "壁纸名称",
        "data": { "video": "...", "preview_jpg": "..." }
      },
      "mobile_detail": {
        "name": "壁纸名称",
        "data": { "mobile_video": "..." }
      }
    }
  ]
}
```

### Static (静态壁纸)

```json
{
  "type": "static",
  "categories": [
    {"id": 1, "name": "精选"}
  ],
  "wallpapers": [
    {
      "wallpaper_id": 300001,
      "categories": [{"id": 5, "name": "动漫"}],
      "created_time": "2026-07-05 04:19:00",
      "weight": 237,
      "pc_detail": {
        "name": "壁纸名称",
        "data": { "jpg_url": "...", "resolution": "3840x2160" }
      }
    }
  ]
}
```

## 依赖

- Python 3.8+
- `requests` (参见 `scripts/requirements.txt`)

## 注意事项

1. 爬取过程中会有 `REQUEST_DELAY` 间隔，避免触发反爬
2. 支持 3 次重试 + 超时处理
3. 不依赖数据库，不支持断点续传（建议用 `--max-pages` 分批爬取）
4. 无图片下载功能，仅获取元数据

## 参考文件

- `scripts/crawler.py` — 主爬虫脚本
- `scripts/requirements.txt` — Python 依赖
- `references/api-reference.md` — API 接口文档
