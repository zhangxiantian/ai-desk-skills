---
name: deal-hunter-crawler
description: >
  Searches the internet for the latest AI product deals, free tokens, new user
  promotions, and discount offers from major AI companies. This skill combines
  automated Python web scraping of official AI company websites with manual
  web search and deep page reading. Uploads results directly to the backend API
  which feeds the AI Desk "AI羊毛党" (AI Deal Hunter) desktop panel.
  Use when the user asks to refresh, crawl, or update AI deal/promotion data.
when-to-use: >
  User requests to crawl, search, or update AI product deals, free tiers,
  API token promotions, new model releases, or discount campaigns. Trigger
  keywords include: 羊毛, deals, 免费额度, 优惠, 爬取AI优惠, 更新deals,
  crawl AI deals, refresh deals.json, AI羊毛党.
allowed-tools:
  - execute_command
  - web_search
  - web_fetch
  - read_file
  - write_to_file
---

# AI Deal Hunter Crawler — 爬取 + API 上传

## 概述

你是 AI Desk 平台的"AI羊毛党"数据采集 Skill。通过**官网爬虫** + **互联网搜索** + **深度页面阅读**三管齐下，采集各大 AI 厂商最新的优惠、免费额度、折扣活动和新品发布信息，**最终通过 API 直接上传到后端数据库**。

**数据源由 `scripts/targets.json` 管理**，你应当在使用过程中动态维护它：
- 发现新 AI 厂商或新的定价页面时，**添加到 targets.json**
- 发现 URL 失效或页面改版时，**更新或删除对应 entry**
- 每次执行前先 `read_file: targets.json` 了解当前数据源状态

## 完整工作流程

### 第 0 步：检查数据源配置（可选但建议）

在执行爬取前，先读取数据源文件确认其完整性和时效性：

```
read_file: .agents/skills/deal-hunter-crawler/scripts/targets.json
```

如果需要补充新厂商（如最近热门的新 AI 平台），先编辑 `targets.json` 添加对应的 `company`、`urls`、`extract_hints` 等字段，然后再执行爬虫。

### 第 1 步：运行 Python 官网爬虫

**必须先执行这一步**。爬虫从 `targets.json` 加载数据源，逐个访问各 AI 厂商官网，爬取完成后直接 POST 到后端 API。

```bash
cd .agents/skills/deal-hunter-crawler/scripts
pip install -r requirements.txt -q
python crawler.py
```

**当前数据源覆盖的厂商**（由 `targets.json` 定义，可动态增减）：
- 国内：智谱AI、阿里云百炼/通义千问、火山引擎/豆包、DeepSeek、腾讯混元、讯飞星火、Kimi/月之暗面、硅基流动、MiniMax、百川智能、超算互联网
- 国际：Google AI、Anthropic/Claude、OpenAI、Mistral AI、xAI/Grok、NVIDIA、GitHub Copilot、Cursor、Cloudflare

### 第 2 步：阅读爬虫输出

爬虫运行完毕后会在控制台输出爬取结果摘要（公司名、分类、截取的文本片段等）。分析哪些厂商的数据充实、哪些需要补充。

### 第 3 步：对爬虫覆盖不到的厂商进行网络搜索补充

针对爬虫未获取到有效数据的厂商，逐一搜索：

```
web_search: "{公司名} API pricing free tier tokens 2026"
或
web_search: "{公司名} 免费额度 新用户 API 2026"
```

**重点补充**：
- 具体的免费 Tokens 数量（如"200万/日"、"1000万/月"）
- 新模型发布时间和名称
- 限时活动截止日期
- 是否需要实名认证

### 第 4 步：深度阅读关键页面

对搜索结果中的官方页面，使用 `web_fetch` 获取完整内容，提取免费额度数字、可用模型列表、速率限制、有效期、认证要求。

### 第 5 步：汇总优化并上传到后端

整合所有数据（爬虫 + 搜索 + 深度阅读），构造符合下方 Schema 的 JSON，调用上传接口写入 `dataset_config` 表：

```
POST http://localhost:8080/api/v1/ai/dataset/deals/upload
Content-Type: application/json
Body: { "categories": [...], "deals": [...] }
```

**成功响应**：`{ "code": 200, "message": "success", "data": { "datasetKey": "deals", "version": 5 } }`

要求：
1. 至少 24 条 deals，覆盖全部 5 个分类
2. 标题和摘要中的数字必须来自实际爬取/搜索到的信息
3. 未被爬虫覆盖但被搜索证实的，使用搜索到的 URL 作为 sourceUrl

## deals.json Schema

```json
{
  "categories": [
    { "id": "free-tokens",     "label": "免费Token" },
    { "id": "free-access",     "label": "免费使用" },
    { "id": "discount-tokens", "label": "折扣Token" },
    { "id": "new-releases",    "label": "新品发布" },
    { "id": "promotions",      "label": "限时活动" }
  ],
  "deals": [
    {
      "id": "dt001",
      "category": "free-tokens",
      "company": "智谱AI（ZhipuAI）",
      "companyLogo": "zhipu",
      "badge": "HOT",
      "title": "智谱AI开放平台新用户注册即享2000万Tokens免费额度",
      "summary": "GLM模型家族覆盖视觉、推理、代码多场景，新用户注册即享免费Tokens，国内低延迟访问。",
      "source": "智谱AI开放平台",
      "sourceUrl": "https://bigmodel.cn",
      "tags": ["GLM", "多模态", "视觉模型", "新用户专享"],
      "publishDate": "2026-07-01T10:00:00Z",
      "hotCount": 46200
    }
  ]
}
```

## 字段约束速查表

| 字段 | 必填 | 格式/约束 |
|------|------|-----------|
| `id` | ✅ | `dt` + 3位数字，从001递增无重复 |
| `category` | ✅ | 5个分类之一 |
| `company` | ✅ | 中文名优先，如"智谱AI（ZhipuAI）" |
| `companyLogo` | ✅ | 仅限下方映射表中的 key |
| `badge` | ✅ | `HOT` / `FREE` / `DISCOUNT` / `NEW` / `PROMO` |
| `title` | ✅ | 30字内 |
| `summary` | ✅ | 80字左右 |
| `source` | ✅ | 来源名称 |
| `sourceUrl` | ✅ | 真实可访问的完整 URL |
| `tags` | ✅ | 3~5个，相关度高 |
| `publishDate` | ✅ | ISO 8601，近一个月内 |
| `hotCount` | ✅ | 10000~100000 |

## 公司 Logo Key 映射表

```
zhipu       → 智谱AI
aliyun      → 阿里云百炼 / 阿里通义千问
bytedance   → 火山引擎 / 字节跳动 / 豆包
deepseek    → DeepSeek
tencent     → 腾讯云混元
google      → Google AI
nvidia      → NVIDIA
anthropic   → Anthropic / Claude
github      → GitHub Copilot
cursor      → Cursor
moonshot    → 月之暗面 / Kimi
siliconflow → 硅基流动
minimax     → MiniMax / 稀宇科技
iflytek     → 讯飞星火
baichuan    → 百川智能
xai         → xAI / Grok
cloudflare  → Cloudflare
mistral     → Mistral AI
scnet       → 超算互联网
openai      → OpenAI
baidu       → 百度文心
meta        → Meta
01ai        → 零一万物
```

## Badge 分配规则

- **HOT**：热度极高（hotCount > 80000）或当前最受关注的福利
- **FREE**：免费 Tokens / 免费使用类（默认）
- **NEW**：新品发布、新模型上线
- **DISCOUNT**：折扣 Token、代金券类
- **PROMO**：限时活动类

## 常用标签（按场景选3~5个）

`新用户专享` `永久免费` `每日重置` `多模态` `视觉模型` `推理模型`
`编程助手` `SDK` `长上下文` `学生免费` `Agent` `图片生成`
`语音API` `开源` `限时活动` `充值赠送` `代金券` `低延迟` `无限调用`

## 输出质量要求

1. **≥24 条 deals**，覆盖全部 5 个分类，每个分类至少 2 条
2. `sourceUrl` 必须是**当前可访问**的真实 URL（优先用爬虫验证过的）
3. `publishDate` 必须是**近一个月内**的合理日期
4. 同一公司**最多 2 条**，确保多样性
5. `hotCount` 合理：新品 50000~100000 / 免费福利 20000~90000 / 促销 10000~50000
6. 标题和摘要中的数字必须来自爬虫或搜索结果，不能凭空编造

## 完成检查清单

- [ ] 已运行 `python crawler.py` 爬取官网数据
- [ ] 已用 web_search + web_fetch 补充爬虫未覆盖的厂商
- [ ] `categories` 包含全部 5 个分类
- [ ] `deals` ≥24 条
- [ ] 每条 deal 包含全部 11 个必填字段
- [ ] `id` 格式正确，无重复，无间断
- [ ] `companyLogo` 值在映射表中存在
- [ ] `badge` 值合法
- [ ] `sourceUrl` 有效且可访问
- [ ] `publishDate` 格式正确，在近一个月内
- [ ] JSON 格式有效
- [ ] 同一公司最多出现 2 次
- [ ] 已通过 API 上传到 `dataset_config` 表

## 参考文件

- `reference/deals-schema.md` — 详细 Schema 文档
- `scripts/crawler.py` — Python 爬虫脚本（爬取后自动上传 API）
- `scripts/targets.json` — **数据源配置文件**（可动态增删改，爬虫从此文件加载爬取目标）
- `scripts/requirements.txt` — Python 依赖
