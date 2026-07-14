# XZDesktop 壁纸 API 参考

## 基础信息

| 项目 | 值 |
|------|-----|
| 域名 | `api-wallpaper-xzdesktop.cqttech.com` |
| 协议 | HTTPS |
| 请求方式 | GET |
| API Key | 脚本内置（保密，通过 `p` 参数传递） |
| 通用参数 | `p=<API_KEY>` |

## API 列表

| API | 端点 | 说明 |
|-----|------|------|
| 版本信息 | `GET /api/v2/vs/info` | 获取壁纸库版本号 |
| 图片列表 | `GET /api/v2/cs/image` | 分页获取分类图片 |
| 图片详情 | `GET /api/v1/wp/wp_detail` | 获取单张图片详情 |

---

## 1. 版本信息

```
GET https://api-wallpaper-xzdesktop.cqttech.com/api/v2/vs/info
```

**Response:**
```json
{
  "code": 200,
  "data": {
    "data": {
      "Version": 1781200801
    }
  }
}
```

---

## 2. 图片列表（分页）

```
GET https://api-wallpaper-xzdesktop.cqttech.com/api/v2/cs/image?
    classify=<分类ID>&
    search=&
    resolution=<0|1>&
    pageIndex=<页码>&
    pageSize=26&
    wv=<版本号>&
    p=<API_KEY>
```

**参数说明:**

| 参数 | 类型 | 说明 |
|------|------|------|
| `classify` | int | 分类ID（共38个有效分类） |
| `search` | string | 搜索关键字（留空） |
| `resolution` | string | 分辨率过滤："0"=全部, "1"=高清 |
| `pageIndex` | int | 页码（从1开始） |
| `pageSize` | int | 每页数量（固定26） |
| `wv` | string | 壁纸库版本号（从 `/api/v2/vs/info` 获取） |
| `p` | string | API Key |

**Response:**
```json
{
  "code": 200,
  "data": {
    "data": {
      "Total": 5256,
      "SubNode": [
        {
          "ID": 182698,
          "Describe": "Pristine waters and white sand...",
          ...
        }
      ]
    }
  }
}
```

**分页计算:**
```
totalPages = ceil(total / PAGE_SIZE)
其中 PAGE_SIZE = 26
```

**每个分类爬取 2 种分辨率:**
- `resolution=0` — 全部
- `resolution=1` — 高清

---

## 3. 图片详情

```
GET https://api-wallpaper-xzdesktop.cqttech.com/api/v1/wp/wp_detail?id=<IMAGE_ID>
```

**Response:**
```json
{
  "code": 200,
  "data": {
    "name": "Pristine waters and white sand in Boracay, Philippines",
    "thumb": "http://xzwallpaper-file.cqttech.com/...",
    "nick_name": "摄影师名称",
    ...
  }
}
```

**核心字段:**
- `name` — 壁纸名称/标题
- `thumb` — 缩略图/原图下载地址

---

## 通用响应结构

```json
{
  "code": 200,
  "data": { ... }
}
```

- `code=200` 表示成功
- 错误响应会包含 `msg` 字段

---

## 分类数据

共 **38 个有效分类**（排除 class=0）：

| 主分类 | ID | 子分类 |
|---------|----|--------|
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

**分类名映射规则:**
- 主分类: `name` 字段，如 "风景"
- 子分类: `"{主分类名}/{子分类名}"` 格式，如 "风景/湖海"

---

## 断点续传数据格式

断点文件 `checkpoint.json` 结构：
```json
{
  "phase": "metadata_done",
  "wv": "1781200801",
  "done_classify_values": [1, 2, 437, 438, ...],
  "images": {
    "182698": {
      "describe": "...",
      "categories": [1, 437],
      "name": "...",
      "thumb_url": "..."
    }
  }
}
```

**阶段说明:**
| phase | 说明 |
|-------|------|
| `metadata_done` | 元数据爬取完成 |
| `details_done` | 详情获取完成 |
| `downloads_done` | 图片下载完成 |
| `compress_done` | 压缩处理完成 |
| `interrupted` | 用户中断 |

## 请求限制与重试策略

| 配置项 | 值 |
|--------|-----|
| 请求超时 | 30 秒 |
| 最大重试次数 | 3 |
| 重试延迟 | 2 秒（指数退避） |
| 列表请求间隔 | 0.3 秒 |
| 详情请求间隔 | 0.15 秒 |
| 下载分块大小 | 64KB |
| 断点保存间隔 | 每 200 张 |

**重试条件:**
- 状态码: 429, 500, 502, 503, 504
- 连接超时
- 连接错误
- 非 HTTP 错误直接抛出不重试

## 缩略图压缩参数

| 参数 | 值 |
|------|-----|
| 缩略图宽度 | 576px |
| WebP 质量 | 80 |
| 缩放算法 | LANCZOS |
| 输出格式 | WebP |
| 文件名规则 | `{image_id}-thumbnail.webp` |
