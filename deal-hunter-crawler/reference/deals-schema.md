# deals.json 完整 Schema 参考

## 数据结构总览

```json
{
  "categories": [
    { "id": "free-tokens", "label": "免费Token" },
    { "id": "free-access", "label": "免费使用" },
    { "id": "discount-tokens", "label": "折扣Token" },
    { "id": "new-releases", "label": "新品发布" },
    { "id": "promotions", "label": "限时活动" }
  ],
  "deals": [
    {
      "id": "string (dtXXX)",
      "category": "string (category id)",
      "company": "string",
      "companyLogo": "string (logo key)",
      "badge": "string (HOT|FREE|DISCOUNT|NEW|PROMO)",
      "title": "string",
      "summary": "string",
      "source": "string",
      "sourceUrl": "string (URL)",
      "tags": ["string array"],
      "publishDate": "string (ISO 8601)",
      "hotCount": "number"
    }
  ]
}
```

## 字段约束

| 字段 | 必填 | 最大长度 | 格式要求 |
|------|------|----------|----------|
| id | ✅ | 5 | `dt` + 3位数字 |
| category | ✅ | 50 | 必须是5个分类之一 |
| company | ✅ | 100 | 中文名优先 |
| companyLogo | ✅ | 50 | 预定义key |
| badge | ✅ | 10 | HOT/FREE/DISCOUNT/NEW/PROMO |
| title | ✅ | 100 | 简洁准确 |
| summary | ✅ | 200 | 80字以内 |
| source | ✅ | 100 | 来源名称 |
| sourceUrl | ✅ | 500 | 完整URL |
| tags | ✅ | 数组 | 3-5个元素 |
| publishDate | ✅ | 30 | ISO 8601 |
| hotCount | ✅ | number | 10000-100000 |

## 支持的公司 Logo Key

```
zhipu, aliyun, bytedance, deepseek, tencent, google,
nvidia, anthropic, github, cursor, moonshot, siliconflow,
minimax, iflytek, baichuan, xai, cloudflare, mistral,
scnet, openai, meta, baidu, sensetime, 01ai
```
