"""
元气桌面 / 海鸟壁纸 数据爬取脚本
直接生成 result/live_wallpaper_data.json 和 result/static_wallpaper_data.json

用法:
  python crawler.py              # 爬取全部（live + static）
  python crawler.py --live       # 仅动态壁纸
  python crawler.py --static     # 仅静态壁纸
  python crawler.py --live --max-pages 3 --delay 0.2   # 限制页数和延迟
"""

import sys
import json
import time
import argparse
import requests
import logging
from pathlib import Path
from datetime import datetime

# ============================================================
# 基础设置
# ============================================================
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RESULT_DIR = SKILL_DIR / "result"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "cache-control": "no-cache",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://wallpaper.zhhainiao.com",
    "pragma": "no-cache",
    "referer": "https://wallpaper.zhhainiao.com/",
    "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
    "x-cf-device-id": "xxxx-xxx-xxx",
    "x-cf-platform": "webview",
}

REQUEST_DELAY = 0.5

# ============================================================
# 日志
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("yuanqi_crawler")


# ============================================================
# 工具函数
# ============================================================

def safe_post(url, json_body, timeout=30):
    """带重试的 POST 请求"""
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=HEADERS, json=json_body, timeout=timeout)
            if 400 <= resp.status_code < 500:
                return resp.json()
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning(f"  请求超时 (尝试 {attempt+1}/3)")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
        except requests.exceptions.RequestException as e:
            logger.warning(f"  请求失败 (尝试 {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    return None


def parse_list_response(data):
    """解析列表 API 响应，返回 (items, total)"""
    if not data:
        return [], 0
    ret = data.get("resp_common", {}).get("ret", -1)
    if ret != 0:
        msg = data.get("resp_common", {}).get("msg", "Unknown")
        logger.error(f"  API 返回错误: ret={ret}, msg={msg}")
        return [], 0
    d = data.get("data", {})
    if isinstance(d, list):
        items = d
        total = len(d)
    else:
        items = d.get("list", d.get("items", []))
        total = d.get("total", d.get("count", len(items)))
    return items, total


def pick_fields(data, core_fields):
    """从 data dict 中只保留 core_fields 中存在的 key"""
    if not data:
        return {}
    return {k: data[k] for k in core_fields if k in data}


def calc_weight(created_time_str, max_timestamp):
    """计算权重：时间越早权重越高"""
    if not created_time_str:
        return 0
    try:
        ts = int(datetime.strptime(created_time_str, "%Y-%m-%d %H:%M:%S").timestamp())
    except Exception:
        return 0
    return max_timestamp - ts


# ============================================================
# 动态壁纸 (Live) 配置
# ============================================================

# Live PC 详情核心字段
LIVE_PC_CORE = [
    "wname", "cate_id", "description",
    "duration", "format", "size", "resolution", "resolution_type", "md5",
    "video", "video_1920", "video_2k", "video_4k",
    "preview_jpg", "preview_gif", "preview_video", "preview_web",
    "encrypt_type", "tag", "voice_type",
    "flag_new", "theme_type", "sub_wtype", "cpack",
]

# Live Mobile 详情核心字段
LIVE_MOBILE_CORE = [
    "wname", "cid", "cname", "long_wname", "cpack",
    "tag", "tags", "tags_str",
    "mobile_duration", "mobile_format", "mobile_size", "mobile_resolution",
    "mobile_md5",
    "mobile_preview_jpg", "mobile_preview_video", "mobile_video",
    "mobile_mov", "mobile_mov_composite", "mobile_mov_compositev2", "mobile_mov_compositev3",
    "mobile_voice_type", "mobile_source_md5", "mobile_wtype",
    "mobile_check_code",
]

# 动态壁纸分类定义
LIVE_CATEGORIES = [
    (
        "精选",
        "https://pcwallpaper.zhhainiao.com/v20526/wplive/index",
        {
            "login_info": {}, "common": {"open_id": None, "token": None, "device_id": "", "player_version": 115, "platform": "pc"},
            "tid1": 165, "tid2": 266, "tod1": 266, "tod2": 1, "is_new_user": 1,
            "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
            "offset": 0, "count": 21, "flow_id": "3"
        },
        "offset", None, None  # is_offset=True, cate_id, tag_id
    ),
    (
        "最新",
        "https://pcwallpaper.zhhainiao.com/wplive/list/newest",
        {
            "login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
            "page": 1, "page_size": 24,
            "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}
        },
        "page", None, None
    ),
    (
        "互动",
        "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
        {
            "login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
            "page": 1, "page_size": 24, "cate_id": None, "tag_id": 21283, "sort_type": 2,
            "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}
        },
        "page", None, 21283
    ),
    (
        "4K",
        "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
        {
            "login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
            "page": 1, "page_size": 24, "cate_id": None, "tag_id": 109, "sort_type": 2,
            "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}
        },
        "page", None, 109
    ),
    ("风景", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 2, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 2, None),
    ("动漫", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 1, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 1, None),
    ("美女", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 3, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 3, None),
    ("动物", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 6, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 6, None),
    ("游戏", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 8, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 8, None),
    ("小清新", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 17, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 17, None),
    ("AI", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": None, "tag_id": 2196803, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", None, 2196803),
    ("IP专区", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 24, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 24, None),
    ("宽屏", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": None, "tag_id": 5331, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", None, 5331),
    ("其他", "https://pcwallpaper.zhhainiao.com/v20903/wplive/list",
     {"login_info": {}, "resolution_support": 0, "wtype_support": 1, "encrypt_support": "none_encrypt",
      "page": 1, "page_size": 24, "cate_id": 9, "tag_id": None, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 9, None),
]

# Live PC 详情 API
DETAIL_PC_URL = "https://pcwallpaper.zhhainiao.com/wallpaper/live/detail"
DETAIL_PC_BODY_TMPL = '{"login_info":{}, "wid":{wid}, "common":{"open_id":null,"token":null,"device_id":null,"player_version":115,"platform":"pc"}}'

# Live Mobile 详情 API
DETAIL_MOBILE_URL = "https://pcwallpaper.zhhainiao.com/mobile/wallpaper/live/detail"
DETAIL_MOBILE_BODY_TMPL = '{"login_info":{}, "wid":{wid}, "common":{"open_id":null,"token":null,"device_id":null,"player_version":115,"platform":"mobile"}}'


# ============================================================
# 静态壁纸 (Static) 配置
# ============================================================

# Static 详情核心字段
STATIC_CORE = [
    "wname", "wallpaper_id", "id", "wtype", "cid", "cname",
    "format", "size", "resolution", "md5",
    "jpg_url", "jpg_1920_url", "mid_jpg_url", "small_jpg_url",
    "tag_ids", "tags", "tags_str",
    "cpack",
]

# 静态壁纸分类定义
STATIC_CATEGORIES = [
    (
        "精选",
        "https://pcwallpaper.zhhainiao.com/wallpaper/static/index",
        {
            "login_info": {},
            "count": 60,
            "offset": 0,
            "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}
        },
        "offset", None, None
    ),
    ("4K", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": None, "tag_id": 93, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", None, 93),
    ("风景", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 1, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 1, None),
    ("小清新", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 8, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 8, None),
    ("动漫", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 2, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 2, None),
    ("明星", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 6, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 6, None),
    ("美女", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 5, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 5, None),
    ("科幻", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 9, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 9, None),
    ("动物", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 7, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 7, None),
    ("游戏", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 4, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 4, None),
    ("体育", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 12, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 12, None),
    ("汽车", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 10, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 10, None),
    ("其他", "https://pcwallpaper.zhhainiao.com/wallpaper/static/list",
     {"login_info": {}, "cate_id": 13, "tag_id": None, "page": 1, "page_size": 24, "sort_type": 2,
      "common": {"open_id": None, "token": None, "device_id": None, "player_version": 115, "platform": "pc"}},
     "page", 13, None),
]


# ============================================================
# 动态壁纸爬取
# ============================================================

def crawl_live_list(cat_id, cat_name, api_url, body_template, pagination_type, cate_id, tag_id, max_pages, max_empty_pages):
    """
    爬取动态壁纸列表，返回 {wallpaper_id: {"name": ..., "categories": [...], "created_time": ...}}
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"爬取 Live 分类: {cat_name} (ID={cat_id})")
    logger.info(f"{'='*50}")

    result = {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if pagination_type == "offset":
        page_size = 21
        offset = 0
        page = 0
        while True:
            page += 1
            body = dict(body_template)  # shallow copy OK: only mutate top-level keys
            body["offset"] = offset
            logger.info(f"  请求 page={page}, offset={offset}")
            data = safe_post(api_url, body)
            if not data:
                break
            items, total = parse_list_response(data)
            if not items:
                break
            logger.info(f"  -> 获取 {len(items)} 项")
            for item in items:
                wid = item.get("wid", item.get("id", 0))
                wname = item.get("wname", item.get("name", ""))
                if wid:
                    if wid not in result:
                        result[wid] = {
                            "wname": wname,
                            "categories": [],
                            "created_time": now_str,
                        }
                    # 同分类内去重，与 page 模式保持一致
                    if {"id": cat_id, "name": cat_name} not in result[wid]["categories"]:
                        result[wid]["categories"].append({"id": cat_id, "name": cat_name})
            offset += len(items)
            if total > 0 and offset >= total:
                break
            time.sleep(REQUEST_DELAY)
        logger.info(f"  完成: {len(result)} 个新增壁纸")
    else:
        # page 分页
        page_size = 24
        page = 1
        empty_count = 0
        while True:
            body = dict(body_template)
            body["page"] = page
            logger.info(f"  请求 page={page}")
            data = safe_post(api_url, body)
            if not data:
                break
            items, total = parse_list_response(data)
            if not items:
                empty_count += 1
                if empty_count >= max_empty_pages:
                    break
                page += 1
                time.sleep(REQUEST_DELAY)
                continue
            empty_count = 0
            logger.info(f"  -> 获取 {len(items)} 项")
            for item in items:
                wid = item.get("wid", item.get("id", 0))
                wname = item.get("wname", item.get("name", ""))
                if wid:
                    if wid not in result:
                        result[wid] = {
                            "wname": wname,
                            "categories": [],
                            "created_time": now_str,
                        }
                    if {"id": cat_id, "name": cat_name} not in result[wid]["categories"]:
                        result[wid]["categories"].append({"id": cat_id, "name": cat_name})
            if len(items) < page_size:
                break
            if total > 0 and page * page_size >= total:
                break
            page += 1
            if max_pages > 0 and page > max_pages:
                break
            time.sleep(REQUEST_DELAY)
        logger.info(f"  完成: {len(result)} 个新增壁纸")

    return result


def crawl_live_detail(wid, source_label="pc"):
    """爬取单个 Live 壁纸的 PC/Mobile 详情，返回 data 子对象或 None"""
    if source_label == "pc":
        url = DETAIL_PC_URL
        body = json.loads(DETAIL_PC_BODY_TMPL.replace("{wid}", str(wid)))
    else:
        url = DETAIL_MOBILE_URL
        body = json.loads(DETAIL_MOBILE_BODY_TMPL.replace("{wid}", str(wid)))
    data = safe_post(url, body)
    if not data:
        logger.warning(f"    [{source_label}] 请求失败: wid={wid}")
        return None
    ret = data.get("resp_common", {}).get("ret", -1)
    if ret != 0:
        msg = data.get("resp_common", {}).get("msg", "Unknown")
        logger.warning(f"    [{source_label}] API 错误: ret={ret}, msg={msg}")
        return None
    return data.get("data", {})


def crawl_live(args):
    """完整爬取动态壁纸"""
    logger.info("=" * 60)
    logger.info("  动态壁纸 (Live) 数据爬取")
    logger.info("=" * 60)

    # 步骤 1: 爬取所有分类的列表
    # all_data: {wallpaper_id: {wname, categories, created_time, pc_detail, mobile_detail}}
    all_data = {}

    for cat_id, (cat_name, api_url, body_template, pagination_type, cate_id, tag_id) in enumerate(LIVE_CATEGORIES):
        cat_id += 1  # 1-based
        cat_result = crawl_live_list(
            cat_id, cat_name, api_url, body_template, pagination_type,
            cate_id, tag_id, args.max_pages, args.max_empty_pages
        )
        for wid, info in cat_result.items():
            if wid not in all_data:
                all_data[wid] = info
            else:
                # 合并分类
                for cat in info["categories"]:
                    if cat not in all_data[wid]["categories"]:
                        all_data[wid]["categories"].append(cat)
                # 保留最早的时间
                if info["created_time"] < all_data[wid]["created_time"]:
                    all_data[wid]["created_time"] = info["created_time"]

    total = len(all_data)
    logger.info(f"\n列表汇总: {total} 个独立动态壁纸")

    if args.skip_detail:
        logger.info("跳过详情爬取")
    else:
        # 步骤 2: 爬取 PC + Mobile 详情
        logger.info(f"\n{'='*50}")
        logger.info(f"开始爬取 Live 详情 (PC + Mobile): {total} 个壁纸")
        logger.info(f"{'='*50}")

        pc_ok = mobile_ok = pc_fail = mobile_fail = 0
        wids = sorted(all_data.keys())

        for i, wid in enumerate(wids):
            wname = all_data[wid].get("wname", "")

            # PC 详情
            if "pc_detail" not in all_data[wid]:
                logger.info(f"  [{i+1}/{total}] PC详情 wid={wid} ({wname})")
                pc_data = crawl_live_detail(wid, "pc")
                if pc_data:
                    all_data[wid]["pc_detail"] = {
                        "name": pc_data.get("wname", wname),
                        "data": pick_fields(pc_data, LIVE_PC_CORE)
                    }
                    pc_ok += 1
                else:
                    pc_fail += 1
                time.sleep(REQUEST_DELAY)
            else:
                pc_ok += 1

            # Mobile 详情
            if "mobile_detail" not in all_data[wid]:
                logger.info(f"  [{i+1}/{total}] Mobile详情 wid={wid} ({wname})")
                mobile_data = crawl_live_detail(wid, "mobile")
                if mobile_data:
                    all_data[wid]["mobile_detail"] = {
                        "name": mobile_data.get("wname", wname),
                        "data": pick_fields(mobile_data, LIVE_MOBILE_CORE)
                    }
                    mobile_ok += 1
                else:
                    mobile_fail += 1
                time.sleep(REQUEST_DELAY)
            else:
                mobile_ok += 1

            if (pc_ok + mobile_ok) % 50 == 0 and (pc_ok + mobile_ok) > 0:
                logger.info(f"  进度: PC 新{pc_ok}/败{pc_fail} | Mobile 新{mobile_ok}/败{mobile_fail}")

        logger.info(f"  详情完成: PC 新{pc_ok} 败{pc_fail} | Mobile 新{mobile_ok} 败{mobile_fail}")

    # 步骤 3: 组装并保存 JSON
    # 分类列表
    categories = [{"id": i + 1, "name": LIVE_CATEGORIES[i][0]} for i in range(len(LIVE_CATEGORIES))]

    # 计算权重
    timestamps = []
    for wid, info in all_data.items():
        try:
            ts = int(datetime.strptime(info["created_time"], "%Y-%m-%d %H:%M:%S").timestamp())
            timestamps.append(ts)
        except Exception:
            pass
    max_ts = max(timestamps) if timestamps else 0

    wallpapers = []
    for wid in sorted(all_data.keys()):
        info = all_data[wid]
        entry = {
            "wallpaper_id": wid,
            "categories": info.get("categories", []),
            "created_time": info.get("created_time", ""),
            "weight": calc_weight(info.get("created_time", ""), max_ts),
        }
        if "pc_detail" in info:
            entry["pc_detail"] = info["pc_detail"]
        if "mobile_detail" in info:
            entry["mobile_detail"] = info["mobile_detail"]
        wallpapers.append(entry)

    result = {
        "type": "live",
        "categories": categories,
        "wallpapers": wallpapers,
    }

    output_path = RESULT_DIR / "live_wallpaper_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    file_size = output_path.stat().st_size / 1024 / 1024
    pc_detail_count = sum(1 for w in wallpapers if "pc_detail" in w)
    mobile_detail_count = sum(1 for w in wallpapers if "mobile_detail" in w)
    logger.info(f"\nLive 导出完成: {output_path}")
    logger.info(f"  分类: {len(categories)}, 壁纸: {len(wallpapers)}")
    logger.info(f"  PC详情: {pc_detail_count}, Mobile详情: {mobile_detail_count}")
    logger.info(f"  文件大小: {file_size:.2f} MB")


# ============================================================
# 静态壁纸爬取
# ============================================================

def crawl_static_list(cat_id, cat_name, api_url, body_template, pagination_type, cate_id, tag_id, max_pages, max_empty_pages):
    """
    爬取静态壁纸列表（列表数据即完整详情）
    返回 {wallpaper_id: {wname, categories, created_time, pc_detail}}
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"爬取 Static 分类: {cat_name} (ID={cat_id})")
    logger.info(f"{'='*50}")

    result = {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if pagination_type == "offset":
        page_size = 60
        offset = 0
        page = 0
        while True:
            page += 1
            body = dict(body_template)
            body["offset"] = offset
            logger.info(f"  请求 page={page}, offset={offset}")
            data = safe_post(api_url, body)
            if not data:
                break
            items, total = parse_list_response(data)
            if not items:
                break
            logger.info(f"  -> 获取 {len(items)} 项")
            for item in items:
                wid = item.get("wid", item.get("id", 0))
                wname = item.get("wname", item.get("name", ""))
                if wid:
                    if wid not in result:
                        result[wid] = {
                            "wname": wname,
                            "categories": [],
                            "created_time": now_str,
                            "pc_detail": {
                                "name": wname,
                                "data": pick_fields(item, STATIC_CORE)
                            }
                        }
                    if {"id": cat_id, "name": cat_name} not in result[wid]["categories"]:
                        result[wid]["categories"].append({"id": cat_id, "name": cat_name})
            offset += len(items)
            if total > 0 and offset >= total:
                break
            time.sleep(REQUEST_DELAY)
        logger.info(f"  完成: {len(result)} 个新增壁纸")
    else:
        # page 分页
        page_size = 24
        page = 1
        empty_count = 0
        while True:
            body = dict(body_template)
            body["page"] = page
            logger.info(f"  请求 page={page}")
            data = safe_post(api_url, body)
            if not data:
                break
            items, total = parse_list_response(data)
            if not items:
                empty_count += 1
                if empty_count >= max_empty_pages:
                    break
                page += 1
                time.sleep(REQUEST_DELAY)
                continue
            empty_count = 0
            logger.info(f"  -> 获取 {len(items)} 项")
            for item in items:
                wid = item.get("wid", item.get("id", 0))
                wname = item.get("wname", item.get("name", ""))
                if wid:
                    if wid not in result:
                        result[wid] = {
                            "wname": wname,
                            "categories": [],
                            "created_time": now_str,
                            "pc_detail": {
                                "name": wname,
                                "data": pick_fields(item, STATIC_CORE)
                            }
                        }
                    if {"id": cat_id, "name": cat_name} not in result[wid]["categories"]:
                        result[wid]["categories"].append({"id": cat_id, "name": cat_name})
            if len(items) < page_size:
                break
            if total > 0 and page * page_size >= total:
                break
            page += 1
            if max_pages > 0 and page > max_pages:
                break
            time.sleep(REQUEST_DELAY)
        logger.info(f"  完成: {len(result)} 个新增壁纸")

    return result


def crawl_static(args):
    """完整爬取静态壁纸"""
    logger.info("=" * 60)
    logger.info("  静态壁纸 (Static) 数据爬取")
    logger.info("  (列表即完整数据，无需额外 detail API)")
    logger.info("=" * 60)

    # 爬取所有分类的列表
    all_data = {}

    for cat_id, (cat_name, api_url, body_template, pagination_type, cate_id, tag_id) in enumerate(STATIC_CATEGORIES):
        cat_id += 1  # 1-based
        cat_result = crawl_static_list(
            cat_id, cat_name, api_url, body_template, pagination_type,
            cate_id, tag_id, args.max_pages, args.max_empty_pages
        )
        for wid, info in cat_result.items():
            if wid not in all_data:
                all_data[wid] = info
            else:
                # 合并分类
                for cat in info["categories"]:
                    if cat not in all_data[wid]["categories"]:
                        all_data[wid]["categories"].append(cat)
                if info["created_time"] < all_data[wid]["created_time"]:
                    all_data[wid]["created_time"] = info["created_time"]

    total = len(all_data)
    logger.info(f"\n列表汇总: {total} 个独立静态壁纸")

    # 组装并保存 JSON
    categories = [{"id": i + 1, "name": STATIC_CATEGORIES[i][0]} for i in range(len(STATIC_CATEGORIES))]

    # 计算权重
    timestamps = []
    for wid, info in all_data.items():
        try:
            ts = int(datetime.strptime(info["created_time"], "%Y-%m-%d %H:%M:%S").timestamp())
            timestamps.append(ts)
        except Exception:
            pass
    max_ts = max(timestamps) if timestamps else 0

    wallpapers = []
    for wid in sorted(all_data.keys()):
        info = all_data[wid]
        entry = {
            "wallpaper_id": wid,
            "categories": info.get("categories", []),
            "created_time": info.get("created_time", ""),
            "weight": calc_weight(info.get("created_time", ""), max_ts),
        }
        if "pc_detail" in info:
            entry["pc_detail"] = info["pc_detail"]
        wallpapers.append(entry)

    result = {
        "type": "static",
        "categories": categories,
        "wallpapers": wallpapers,
    }

    output_path = RESULT_DIR / "static_wallpaper_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    file_size = output_path.stat().st_size / 1024 / 1024
    detail_count = sum(1 for w in wallpapers if "pc_detail" in w)
    logger.info(f"\nStatic 导出完成: {output_path}")
    logger.info(f"  分类: {len(categories)}, 壁纸: {len(wallpapers)}")
    logger.info(f"  详情: {detail_count}")
    logger.info(f"  文件大小: {file_size:.2f} MB")


# ============================================================
# 命令行入口
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="元气桌面 / 海鸟壁纸 数据爬取脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python crawler.py                     # 爬取全部 (live + static)
  python crawler.py --live              # 仅动态壁纸
  python crawler.py --static            # 仅静态壁纸
  python crawler.py --live --max-pages 3  # 仅动态壁纸，每分类最多3页
  python crawler.py --delay 0.2         # 自定义请求延迟
  python crawler.py --live --skip-detail # 仅爬列表，跳过详情
        """,
    )
    parser.add_argument("--live", action="store_true", help="仅动态壁纸")
    parser.add_argument("--static", action="store_true", help="仅静态壁纸")
    parser.add_argument("--max-pages", type=int, default=0, help="每分类最大页数 (0=不限制)")
    parser.add_argument("--max-empty-pages", type=int, default=3, help="连续空页上限 (默认3)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help=f"请求延迟秒数 (默认{REQUEST_DELAY})")
    parser.add_argument("--skip-detail", action="store_true", help="跳过详情爬取 (仅爬列表)")
    return parser.parse_args()


def main():
    args = parse_args()
    global REQUEST_DELAY
    REQUEST_DELAY = args.delay

    both = not args.live and not args.static

    logger.info("=" * 60)
    logger.info("  元气桌面 / 海鸟壁纸 数据爬取脚本")
    logger.info(f"  输出目录: {RESULT_DIR}")
    logger.info(f"  请求延迟: {REQUEST_DELAY}s")
    if args.max_pages > 0:
        logger.info(f"  每分类最大页数: {args.max_pages}")
    logger.info("=" * 60)

    if both or args.live:
        crawl_live(args)

    if both or args.static:
        crawl_static(args)

    logger.info("\n" + "=" * 60)
    logger.info("  全部完成!")
    logger.info(f"  输出目录: {RESULT_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
