# 元气桌面 / 海鸟壁纸 API 参考

## 基础信息

| 项目 | 值 |
|------|-----|
| 域名 | `pcwallpaper.zhhainiao.com` |
| 官网 | `https://wallpaper.zhhainiao.com/` |
| 请求方式 | POST (JSON Body) |
| Content-Type | `application/json;charset=UTF-8` |
| 平台参数 | `platform: "pc"` / `platform: "mobile"` |

## 通用请求头

```
Content-Type: application/json;charset=UTF-8
Origin: https://wallpaper.zhhainiao.com
Referer: https://wallpaper.zhhainiao.com/
```

## 动态壁纸 (Live) API

### 1. 精选列表

```
POST https://pcwallpaper.zhhainiao.com/v20526/wplive/index
```

**Request Body:**
```json
{
  "login_info": {},
  "common": {"open_id": null, "token": null, "device_id": "", "player_version": 115, "platform": "pc"},
  "tid1": 165, "tid2": 266, "tod1": 266, "tod2": 1, "is_new_user": 1,
  "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
  "offset": 0, "count": 21, "flow_id": "3"
}
```
- 分页方式: offset
- PageSize: 21

### 2. 最新列表

```
POST https://pcwallpaper.zhhainiao.com/wplive/list/newest
```

**Request Body:**
```json
{
  "login_info": {},
  "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
  "page": 1, "page_size": 24,
  "common": {"open_id": null, "token": null, "device_id": null, "player_version": 115, "platform": "pc"}
}
```
- 分页方式: page
- PageSize: 24

### 3. 分类列表（互动/4K/风景/动漫/美女/动物/游戏/小清新/AI/IP专区/宽屏/其他）

```
POST https://pcwallpaper.zhhainiao.com/v20903/wplive/list
```

**Request Body 通用模板:**
```json
{
  "login_info": {},
  "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
  "page": 1, "page_size": 24,
  "cate_id": <category_id>, "tag_id": <tag_id>, "sort_type": 2,
  "common": {"open_id": null, "token": null, "device_id": null, "player_version": 115, "platform": "pc"}
}
```

**分类参数对照表:**

| 分类名 | cate_id | tag_id |
|--------|---------|--------|
| 互动 | null | 21283 |
| 4K | null | 109 |
| 风景 | 2 | null |
| 动漫 | 1 | null |
| 美女 | 3 | null |
| 动物 | 6 | null |
| 游戏 | 8 | null |
| 小清新 | 17 | null |
| AI | null | 2196803 |
| IP专区 | 24 | null |
| 宽屏 | null | 5331 |
| 其他 | 9 | null |

### 4. PC 详情

```
POST https://pcwallpaper.zhhainiao.com/wallpaper/live/detail
```

**Request Body:**
```json
{"login_info":{}, "wid": <wallpaper_id>, "common":{"open_id":null,"token":null,"device_id":null,"player_version":115,"platform":"pc"}}
```

**Response `data` 核心字段:**
- `wname` — 壁纸名称
- `cate_id` — 分类ID
- `description` — 描述
- `duration` — 时长
- `format` — 格式
- `size` — 大小
- `resolution` — 分辨率
- `resolution_type` — 分辨率类型
- `md5`
- `video` — 视频地址
- `video_1920` / `video_2k` / `video_4k` — 多分辨率视频
- `preview_jpg` — JPG预览
- `preview_gif` — GIF预览
- `preview_video` — 视频预览
- `preview_web` — Web预览
- `encrypt_type` — 加密类型
- `tag`
- `voice_type`
- `flag_new` — 新品标记
- `theme_type` — 主题类型
- `sub_wtype` — 子类型
- `cpack` — 包信息

### 5. Mobile 详情

```
POST https://pcwallpaper.zhhainiao.com/mobile/wallpaper/live/detail
```

**Request Body:**
```json
{"login_info":{}, "wid": <wallpaper_id>, "common":{"open_id":null,"token":null,"device_id":null,"player_version":115,"platform":"mobile"}}
```

**Response `data` 核心字段:**
- `wname`, `cid`, `cname`, `long_wname`, `cpack`
- `tag`, `tags`, `tags_str`
- `mobile_duration`, `mobile_format`, `mobile_size`, `mobile_resolution`, `mobile_md5`
- `mobile_preview_jpg`, `mobile_preview_video`, `mobile_video`
- `mobile_mov`, `mobile_mov_composite`, `mobile_mov_compositev2`, `mobile_mov_compositev3`
- `mobile_voice_type`, `mobile_source_md5`, `mobile_wtype`
- `mobile_check_code`

## 静态壁纸 (Static) API

### 1. 精选列表

```
POST https://pcwallpaper.zhhainiao.com/wallpaper/static/index
```

**Request Body:**
```json
{
  "login_info": {},
  "count": 60,
  "offset": 0,
  "common": {"open_id": null, "token": null, "device_id": null, "player_version": 115, "platform": "pc"}
}
```
- 分页方式: offset
- PageSize: 60

### 2. 分类列表（4K/风景/小清新/动漫/明星/美女/科幻/动物/游戏/体育/汽车/其他）

```
POST https://pcwallpaper.zhhainiao.com/wallpaper/static/list
```

**Request Body 通用模板:**
```json
{
  "login_info": {},
  "cate_id": <category_id>, "tag_id": <tag_id>, "page": 1, "page_size": 24, "sort_type": 2,
  "common": {"open_id": null, "token": null, "device_id": null, "player_version": 115, "platform": "pc"}
}
```

**分类参数对照表:**

| 分类名 | cate_id | tag_id |
|--------|---------|--------|
| 4K | null | 93 |
| 风景 | 1 | null |
| 小清新 | 8 | null |
| 动漫 | 2 | null |
| 明星 | 6 | null |
| 美女 | 5 | null |
| 科幻 | 9 | null |
| 动物 | 7 | null |
| 游戏 | 4 | null |
| 体育 | 12 | null |
| 汽车 | 10 | null |
| 其他 | 13 | null |

**注意:** 静态壁纸的列表 API 响应即包含完整详情数据，无需额外 detail API。

**Response `data` 核心字段:**
- `wname`, `wallpaper_id`, `id`, `wtype`, `cid`, `cname`
- `format`, `size`, `resolution`, `md5`
- `jpg_url`, `jpg_1920_url`, `mid_jpg_url`, `small_jpg_url`
- `tag_ids`, `tags`, `tags_str`
- `cpack`

## 通用响应结构

```json
{
  "resp_common": {
    "ret": 0,
    "msg": ""
  },
  "data": {
    "list": [...],
    "total": 100
  }
}
```

- `ret=0` 表示成功，非0表示错误
- 列表响应中 `data` 可能为数组或包含 `list`/`items` 的对象
- 精选类 API 返回 `data` 可能为直接数组

## 请求限制与重试策略

- 请求间隔: 默认 0.5 秒
- 超时时间: 30 秒
- 重试次数: 3 次（指数退避）
- 4xx 状态码不重试（直接解析响应）
