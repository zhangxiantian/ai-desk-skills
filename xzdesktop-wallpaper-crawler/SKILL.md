---
name: xzdesktop-wallpaper-crawler
description: >
  Crawls wallpapers from XZDesktop Wallpaper Center API (api-wallpaper-xzdesktop.cqttech.com),
  covering 38 categories × 2 resolutions with multi-phase execution: metadata crawling, detail
  fetching, image downloading, and thumbnail compression. Outputs default_wallpaper_data.json.
  Use when the user asks to crawl, refresh, or update wallpaper data from XZDesktop/小熊桌面壁纸
  or when wallpaper data files need to be regenerated.
when-to-use: >
  User requests to crawl or update wallpaper data from XZDesktop, 小熊桌面,
  or cqttech.com. Trigger keywords include: XZ桌面, 小熊桌面, 壁纸爬取,
  壁纸数据更新, wallpaper crawl, default_wallpaper_data, crawl xzdesktop.
allowed-tools:
  - execute_command
  - read_file
  - write_to_file
disable: false
---

# XZDesktop 壁纸数据爬取 Skill

## 前提条件

- 工作目录必须在项目根目录（`ai-desk/`）
- Python 3.9+ 已安装
- 需要网络访问 `api-wallpaper-xzdesktop.cqttech.com`
- 缩略图压缩需额外安装 Pillow

## 概述

从 XZDesktop 壁纸中心 API（`api-wallpaper-xzdesktop.cqttech.com`）爬取壁纸数据。支持多阶段分步执行和断点续传，最终生成 `result/default_wallpaper_data.json`。

**数据覆盖范围**：
- **38 个分类** × 2 种分辨率（resolution=0, 1）
- 含主分类和子分类（如 "风景/湖海"、"动物/喵星人"）
- 可选：下载原图 + WebP 缩略图压缩

## 输出文件

| 文件 | 说明 |
|------|------|
| `result/default_wallpaper_data.json` | 最终 JSON 输出（壁纸元数据） |
| `checkpoint.json` | 断点文件（自动生成，支持续传） |
| `downloads/` | 图片下载目录（`--download` 后生成） |

## 工作流程

> **注意**：所有命令均在项目根目录（`ai-desk/`）下执行。脚本工作目录为 `scripts/`，输出文件写入上层 `result/`。

### 快速开始

```bash
cd ai-desk-skills/xzdesktop-wallpaper-crawler/scripts
pip install -r requirements.txt

# 仅爬取元数据 + 详情（最快，不下载图片）
python crawler.py

# 爬取 + 下载图片 + 生成缩略图（完整流程）
python crawler.py --download --compress
```

### 分步执行（推荐大数据量场景）

```bash
cd ai-desk-skills/xzdesktop-wallpaper-crawler/scripts

# 第 1 步：爬取元数据（约 3-5 分钟）
python crawler.py --metadata-only

# 第 2 步：获取详情（每张图片需一次 API 调用，耗时较长）
python crawler.py --detail-only

# 第 3 步：下载图片（可选）
python crawler.py --download-only

# 第 4 步：提取尺寸 + 生成 WebP 缩略图（可选，需要 Pillow）
python crawler.py --compress-only
```

### 中断续传

每一步都支持 `Ctrl+C` 中断，重跑自动续传：

```bash
cd ai-desk-skills/xzdesktop-wallpaper-crawler/scripts

# 中断后直接重跑即可续传
python crawler.py --download --compress

# 完全重新开始
python crawler.py --reset
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `python crawler.py` | 完整爬取（元数据 → 详情 → 导出） |
| `python crawler.py --download` | 爬取 + 下载图片到本地 |
| `python crawler.py --download --compress` | 爬取 + 下载 + 尺寸提取 + WebP 缩略图 |
| `python crawler.py --metadata-only` | 仅爬取元数据，保存 checkpoint |
| `python crawler.py --detail-only` | 仅获取详情（需已有 checkpoint） |
| `python crawler.py --download-only` | 仅下载图片（需已有 checkpoint） |
| `python crawler.py --compress-only` | 仅压缩缩略图（需已有下载文件） |
| `python crawler.py --reset` | 清除 checkpoint，重新开始 |

## 核心流程

```
获取版本号 (GET /api/v2/vs/info)
    │
    ▼
遍历 38 个分类 × 2 种分辨率 (resolution=0, 1)
  └─ 分页获取图片列表 (GET /api/v2/cs/image)
    │
    ├─ 按 image_id 去重
    └─ 同一图片出现在多个分类时合并 categories
    │
    ▼ (保存 checkpoint)
    │
为每张图片获取详情 (GET /api/v1/wp/wp_detail?id=IMAGE_ID)
  └─ 提取 name + thumb_url
    │
    ▼ (保存 checkpoint)
    │
[可选] 下载图片 (HTTP GET thumb_url → downloads/{id}.{ext})
  └─ 断点续传：文件已存在则跳过
    │
    ▼ (保存 checkpoint)
    │
[可选] 压缩处理 (需 Pillow)
  ├─ 提取 width, height, aspect_ratio, file_size
  └─ 生成 WebP 缩略图 (宽 576px) → downloads/{id}-thumbnail.webp
    │
    ▼ (保存 checkpoint)
    │
导出 JSON
  ├─ 过滤 class=0（无效分类）
  ├─ 构建分类名映射（如 437 → "风景/湖海"）
  └─ 按 image_id 升序输出
```

## JSON 输出格式

### 基础格式（仅爬取元数据 + 详情）

```json
[
  {
    "id": 178145,
    "describe": "Pristine waters and white sand in Boracay, Philippines",
    "categories": [1, 437],
    "category_names": ["风景", "风景/湖海"],
    "name": "Pristine waters and white sand in Boracay, Philippines",
    "thumb_url": "http://xzwallpaper-file.cqttech.com/..."
  }
]
```

### 完整格式（含下载 + 压缩）

基础字段基础上增加：
```json
{
  "width": 4096,
  "height": 2304,
  "aspect_ratio": 1.7809,
  "file_size": 1234567,
  "thumbnail": "178145-thumbnail.webp"
}
```

## 分类覆盖（共 38 个）

| 分类 | ID | 子分类 |
|------|----|----|
| 精选 | 593 | — |
| AI绘图 | 596 | 静物风景(597), 卡通动漫(598), 美女帅哥(599) |
| 风景 | 1 | 湖海(437), 山川(438), 日月星辰(439), 绿色护眼(440), 宇宙星空(441), 其他景观(442) |
| 动漫 | 559 | — |
| 动物 | 2 | 喵星人(450), 汪星人(451), 鸟类(452), 海底世界(453), 野生动物(454), 其他(455) |
| 植物 | 11 | 花花世界(447), 绿色植物(448), 唯美意境(449) |
| 建筑 | 10 | 都市风光(548), 异域风采(550) |
| 创意 | 4 | — |
| 静物 | 13 | — |
| 体育 | 16 | 篮球(357), 足球(370), 其他(459) |
| 美食 | 19 | — |
| 其他 | 24 | — |
| 分区 | 594 | — |
| 文字 | 595 | — |
| 可爱 | 2124 | — |

## 断点续传机制

| 阶段 | 断点标记方式 |
|------|------------|
| 元数据爬取 | 记录已完成的分类 ID（`done_classify_values`） |
| 详情获取 | 图片 `name` 字段非空则跳过，每 200 张自动保存 |
| 图片下载 | 图片 `download_path` 字段非空则跳过，已存在文件自动跳过 |
| 缩略图压缩 | 已有 `width/height` 的跳过尺寸提取，已存在 `.webp` 文件跳过压缩 |

## 依赖

- Python 3.9+
- 基础依赖：`requests`, `urllib3`（参见 `scripts/requirements.txt`）
- 压缩缩略图需要：`Pillow`（仅 `--compress` 时需要）

## 注意事项

1. XZDesktop API 需要 `API_KEY` 鉴权，脚本已内置
2. 分页 PageSize=26，每个分类 × 2 种分辨率分页爬取
3. 同一图片出现在多个分类时，categories 自动合并
4. 下载图片使用 `.tmp` 后缀 + 原子 rename，防止半截文件
5. 连续失败超过 `MAX_RETRIES(3)` 次自动跳过或停止

## 参考文件

- `scripts/crawler.py` — 主爬虫脚本
- `scripts/requirements.txt` — Python 依赖
- `references/api-reference.md` — XZDesktop API 接口文档
