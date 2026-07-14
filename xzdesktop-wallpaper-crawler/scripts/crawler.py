#!/usr/bin/env python3
"""
XZDesktop 壁纸数据爬取器 - 独立脚本版

基于原 xzdesktop-wallpaper 项目核心逻辑提取，不依赖 SQLite。
直接调用 XZDesktop API 获取壁纸元数据，生成 default_wallpaper_data.json。

核心流程:
  1. 获取壁纸库版本号 (API: /api/v2/vs/info)
  2. 遍历 38 个分类 × 2 种分辨率，分页获取图片列表 (API: /api/v2/cs/image)
  3. 按 image_id 去重，同一图片出现在多个分类时合并 classify_list
  4. 为每张图片获取详情 name + thumb_url (API: /api/v1/wp/wp_detail)
  5. [可选] 下载图片到本地 downloads/ 目录
  6. [可选] 提取尺寸 + 生成 WebP 缩略图 (需 Pillow)
  7. 过滤 class=0，构建分类名映射，导出 JSON

用法:
  python crawler.py                        # 完整爬取（元数据 + 详情 + 导出）
  python crawler.py --download              # 爬取 + 下载图片
  python crawler.py --download --compress   # 爬取 + 下载 + 缩略图
  python crawler.py --metadata-only         # 仅爬取元数据（保存断点）
  python crawler.py --reset                 # 重置进度重新开始
"""

import json
import os
import sys
import time
import io
import argparse
import logging
from collections import Counter

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===== 修复 Windows 控制台编码 =====
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ===== 配置常量 =====
BASE_URL = "https://api-wallpaper-xzdesktop.cqttech.com"
API_KEY = "6512bd43d9caa6e02c990b0a82652dca"
PAGE_SIZE = 26
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
REQUEST_INTERVAL = 0.3       # 列表请求间隔（秒）
DETAIL_INTERVAL = 0.15       # 详情请求间隔（秒）
CHECKPOINT_SAVE_EVERY = 200  # 每获取N张详情保存一次断点

# 下载与压缩配置
DOWNLOAD_CHUNK_SIZE = 1024 * 64  # 64KB 分块下载
THUMB_WIDTH = 576
WEBP_QUALITY = 80

# 本地路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
RESULT_DIR = os.path.join(SKILL_DIR, "result")
DOWNLOAD_DIR = os.path.join(SKILL_DIR, "downloads")
CHECKPOINT_FILE = os.path.join(SKILL_DIR, "checkpoint.json")
OUTPUT_FILE = os.path.join(RESULT_DIR, "default_wallpaper_data.json")

# ===== 分类数据（与 xzdesktop-wallpaper/scraper/config.py 一致） =====
CATEGORIES = [
    {"name": "精选", "value": 593, "sub_node": None},
    {"name": "AI绘图", "value": 596, "sub_node": [
        {"name": "静物风景", "value": 597},
        {"name": "卡通动漫", "value": 598},
        {"name": "美女帅哥", "value": 599},
    ]},
    {"name": "风景", "value": 1, "sub_node": [
        {"name": "湖海", "value": 437},
        {"name": "山川", "value": 438},
        {"name": "日月星辰", "value": 439},
        {"name": "绿色护眼", "value": 440},
        {"name": "宇宙星空", "value": 441},
        {"name": "其他景观", "value": 442},
    ]},
    {"name": "动漫", "value": 559, "sub_node": None},
    {"name": "动物", "value": 2, "sub_node": [
        {"name": "喵星人", "value": 450},
        {"name": "汪星人", "value": 451},
        {"name": "鸟类", "value": 452},
        {"name": "海底世界", "value": 453},
        {"name": "野生动物", "value": 454},
        {"name": "其他", "value": 455},
    ]},
    {"name": "植物", "value": 11, "sub_node": [
        {"name": "花花世界", "value": 447},
        {"name": "绿色植物", "value": 448},
        {"name": "唯美意境", "value": 449},
    ]},
    {"name": "建筑", "value": 10, "sub_node": [
        {"name": "都市风光", "value": 548},
        {"name": "异域风采", "value": 550},
    ]},
    {"name": "创意", "value": 4, "sub_node": None},
    {"name": "静物", "value": 13, "sub_node": None},
    {"name": "体育", "value": 16, "sub_node": [
        {"name": "篮球", "value": 357},
        {"name": "足球", "value": 370},
        {"name": "其他", "value": 459},
    ]},
    {"name": "美食", "value": 19, "sub_node": None},
    {"name": "其他", "value": 24, "sub_node": None},
    {"name": "分区", "value": 594, "sub_node": None},
    {"name": "文字", "value": 595, "sub_node": None},
    {"name": "可爱", "value": 2124, "sub_node": None},
]


def build_classify_name_map():
    """构建 分类ID -> 分类名称 的映射。

    子分类格式: "父分类名/子分类名"，如 "风景/湖海"、"动物/喵星人"
    """
    name_map = {}
    for cat in CATEGORIES:
        name_map[cat["value"]] = cat["name"]
        if cat["sub_node"]:
            for sub in cat["sub_node"]:
                name_map[sub["value"]] = f"{cat['name']}/{sub['name']}"
    return name_map


def get_all_classify_values():
    """获取所有需要爬取的分类ID列表（共38个，排除class=0"全部"）"""
    result = []
    for cat in CATEGORIES:
        if cat["value"] != 0:
            result.append(cat["value"])
        if cat["sub_node"]:
            for sub in cat["sub_node"]:
                result.append(sub["value"])
    return result


# =====================================================================
#  API 客户端
# =====================================================================

class APIClient:
    """XZDesktop 壁纸 API 客户端，封装请求重试与指数退避"""

    def __init__(self):
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        return session

    def _request(self, url, params=None, timeout=None):
        """统一请求方法，带指数退避重试"""
        timeout = timeout or REQUEST_TIMEOUT
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout as e:
                last_error = f"请求超时: {e}"
            except requests.exceptions.ConnectionError as e:
                last_error = f"连接错误: {e}"
            except requests.exceptions.HTTPError as e:
                raise
            except requests.exceptions.RequestException as e:
                last_error = str(e)
            except ValueError as e:
                last_error = f"JSON解析失败: {e}"
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * (2 ** attempt)
                logger.debug(f"重试 {attempt + 1}/{MAX_RETRIES}，等待 {wait}s...")
                time.sleep(wait)
        raise Exception(f"请求失败(重试{MAX_RETRIES}次): {last_error}")

    def get_version(self):
        """获取壁纸库版本号

        请求: GET /api/v2/vs/info
        返回: {"code":200, "data":{"data":{"Version": 1781200801, ...}}}
        """
        url = f"{BASE_URL}/api/v2/vs/info"
        data = self._request(url)
        if data.get("code") == 200:
            version = data.get("data", {}).get("data", {}).get("Version", "")
            return str(version) if version else ""
        raise Exception(f"获取版本失败: {data.get('msg', '未知错误')}")

    def get_image_list(self, classify_value, page_index=1, wv="", resolution="0"):
        """获取指定分类的壁纸列表（分页）

        请求: GET /api/v2/cs/image?classify=X&pageIndex=N&resolution=0/1&wv=VERSION
        返回: {"total": 5256, "images": [{"ID": 182698, "Describe": "...", ...}]}
        """
        url = f"{BASE_URL}/api/v2/cs/image"
        params = {
            "classify": str(classify_value),
            "search": "",
            "resolution": resolution,
            "pageIndex": str(page_index),
            "pageSize": str(PAGE_SIZE),
            "wv": wv,
            "p": API_KEY,
        }
        data = self._request(url, params=params)
        if data.get("code") == 200:
            inner = data.get("data", {}).get("data", {})
            images = inner.get("SubNode") or []
            total = inner.get("Total", 0)
            return {"total": total, "images": images}
        else:
            raise Exception(
                f"获取图片列表失败(classify={classify_value}, page={page_index}): "
                f"code={data.get('code')}, msg={data.get('msg')}"
            )

    def get_image_detail(self, image_id):
        """获取单张图片详情（包含 thumb 下载地址）

        请求: GET /api/v1/wp/wp_detail?id=IMAGE_ID
        返回: {"name": "...", "thumb": "http://...", "nick_name": "...", ...}
        """
        url = f"{BASE_URL}/api/v1/wp/wp_detail"
        params = {"id": str(image_id)}
        data = self._request(url, params=params)
        if data.get("code") == 200:
            return data.get("data", {})
        else:
            raise Exception(
                f"获取图片详情失败(id={image_id}): "
                f"code={data.get('code')}, msg={data.get('msg')}"
            )

    def download_image(self, url, save_path):
        """下载图片到本地

        Args:
            url: 图片URL
            save_path: 保存路径
        Returns:
            int: 文件大小(字节)
        """
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        resp = self.session.get(url, stream=True, timeout=60)
        resp.raise_for_status()

        downloaded = 0
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        return downloaded

    def close(self):
        self.session.close()


# =====================================================================
#  断点续传（checkpoint）
# =====================================================================

def load_checkpoint():
    """加载保存的断点数据"""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            cp = json.load(f)
            # 恢复 images 时，categories 是 list
            images = {}
            for k, v in cp.get("images", {}).items():
                img_id = int(k)
                v["categories"] = set(v.get("categories", []))
                images[img_id] = v
            cp["images"] = images
            return cp
    return None


def save_checkpoint(state):
    """保存断点数据（categories set 转换为 list 以便 JSON 序列化）"""
    saveable = dict(state)
    # 序列化 images
    images_for_save = {}
    for img_id, info in state.get("images", {}).items():
        info_copy = dict(info)
        info_copy["categories"] = sorted(list(info.get("categories", set())))
        images_for_save[str(img_id)] = info_copy
    saveable["images"] = images_for_save
    # 序列化 done_classify_values（set → list）
    if "done_classify_values" in saveable:
        saveable["done_classify_values"] = sorted(
            list(saveable["done_classify_values"])
        )
    os.makedirs(os.path.dirname(CHECKPOINT_FILE) or ".", exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(saveable, f, ensure_ascii=False, indent=2)


# =====================================================================
#  阶段 1：爬取元数据
# =====================================================================

def crawl_metadata(api, wv, classify_values, class_name_map,
                   done_classify_values=None):
    """遍历所有分类 × 两种分辨率，分页获取图片列表并去重合并。

    Args:
        api: APIClient 实例
        wv: 壁纸库版本号
        classify_values: 需要爬取的分类ID列表
        class_name_map: 分类ID→名称映射
        done_classify_values: 已完成的分类ID集合（断点续传跳过）

    Returns:
        dict: {image_id: {"describe": str, "categories": set}}
              同一图片出现在多个分类时 categories 自动合并
    """
    images = {}  # image_id -> {"describe": str, "categories": set}
    total_cats = len(classify_values)
    done_set = set(done_classify_values or [])

    for idx, classify_value in enumerate(classify_values, 1):
        cat_name = class_name_map.get(classify_value, str(classify_value))

        # 断点续传：跳过已完成的分类
        if classify_value in done_set:
            logger.info(
                f"[分类 {idx}/{total_cats}] [{classify_value}] {cat_name} "
                f"(已完成，跳过)"
            )
            continue

        logger.info(
            f"\n[分类 {idx}/{total_cats}] [{classify_value}] {cat_name}"
        )

        for resolution in ("0", "1"):
            page = 1
            res_img_count = 0
            consecutive_errors = 0
            logger.info(f"  resolution={resolution} 开始...")

            while True:
                try:
                    result = api.get_image_list(
                        classify_value, page_index=page,
                        wv=wv, resolution=resolution
                    )
                    img_list = result.get("images", [])
                    total_for_res = result.get("total", 0)

                    if not img_list:
                        logger.info(
                            f"  resolution={resolution} 第{page}页无数据，完成"
                        )
                        break

                    for img in img_list:
                        img_id = img.get("ID", 0)
                        describe = img.get("Describe", "")

                        if img_id in images:
                            # 图片已存在：追加分类
                            images[img_id]["categories"].add(classify_value)
                        else:
                            # 新图片：创建记录
                            images[img_id] = {
                                "describe": describe,
                                "categories": {classify_value},
                            }

                    res_img_count += len(img_list)
                    total_pages = (
                        total_for_res + PAGE_SIZE - 1
                    ) // PAGE_SIZE
                    logger.info(
                        f"  resolution={resolution} "
                        f"第{page}/{total_pages}页: "
                        f"{len(img_list)}张 | "
                        f"分辨率累计: {res_img_count}/{total_for_res}"
                    )

                    if page >= total_pages:
                        break
                    page += 1
                    consecutive_errors = 0  # 成功则重置错误计数
                    time.sleep(REQUEST_INTERVAL)

                except KeyboardInterrupt:
                    logger.info(
                        f"\n用户中断，已收集 {len(images)} 张图片"
                    )
                    # 不标记当前分类完成，下次重新抓
                    raise
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"  resolution={resolution} 第{page}页失败: {e} "
                        f"(连续失败 {consecutive_errors}/{MAX_RETRIES})"
                    )
                    if consecutive_errors >= MAX_RETRIES:
                        logger.error(
                            f"  连续失败 {consecutive_errors} 次，跳过"
                            f" resolution={resolution}"
                        )
                        break
                    wait = RETRY_DELAY * (2 ** (consecutive_errors - 1))
                    logger.info(f"  {wait}秒后重试...")
                    time.sleep(wait)

        # 标记当前分类完成
        done_set.add(classify_value)
        logger.info(
            f"  [{classify_value}] {cat_name} 完成，"
            f"当前总图片数: {len(images)}"
        )

    return images


# =====================================================================
#  阶段 2：获取详情
# =====================================================================

def fetch_details(api, images, done_classify_values=None):
    """为每张图片调用详情 API，获取 name 和 thumb_url。

    支持断点续传：已获取详情的图片（有 name 字段）自动跳过。
    每 CHECKPOINT_SAVE_EVERY 张保存一次 checkpoint。

    Args:
        api: APIClient 实例
        images: {image_id: {"describe": str, "categories": set}}
               详情字段（name, thumb_url）会直接写入此字典
        done_classify_values: 已完成的分类ID集合（用于 checkpoint 持久化）
    """
    total = len(images)
    image_ids = sorted(images.keys())

    # 统计已获取详情的数量
    done_count = sum(1 for img_id in image_ids if images[img_id].get("name") is not None)
    if done_count > 0:
        logger.info(f"断点续传: 已获取 {done_count}/{total} 张详情，跳过")
    else:
        logger.info(f"开始获取详情，共 {total} 张图片")

    success = 0
    skip = 0
    fail = 0
    consecutive_errors = 0
    done_since_save = 0

    for idx, img_id in enumerate(image_ids, 1):
        # 已获取详情的跳过
        if images[img_id].get("name") is not None:
            skip += 1
            continue

        try:
            detail = api.get_image_detail(img_id)
            images[img_id]["name"] = detail.get("name", "")
            images[img_id]["thumb_url"] = detail.get("thumb", "")
            success += 1
            consecutive_errors = 0
            done_since_save += 1
        except Exception as e:
            consecutive_errors += 1
            logger.error(
                f"  [id={img_id}] 详情获取失败: {e} "
                f"(连续失败 {consecutive_errors}/{MAX_RETRIES})"
            )
            # 失败也写入空值避免重复请求
            images[img_id]["name"] = images[img_id].get("describe", "")
            images[img_id]["thumb_url"] = ""
            fail += 1
            done_since_save += 1

            if consecutive_errors >= MAX_RETRIES:
                logger.error(
                    f"  连续失败 {consecutive_errors} 次，"
                    f"停止详情获取（已处理 {idx}/{total}）"
                )
                break
            time.sleep(RETRY_DELAY)

        # 定时保存断点（保留 done_classify_values）
        if done_since_save >= CHECKPOINT_SAVE_EVERY:
            save_checkpoint({
                "phase": "details",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            done_since_save = 0

        # 进度输出
        if idx % 50 == 0 or idx == total:
            done = success + skip + fail
            logger.info(
                f"  详情进度: {done}/{total} ({done/total*100:.1f}%) "
                f"✓{success} ⊘{skip} ✗{fail}"
            )

        time.sleep(DETAIL_INTERVAL)

    logger.info(f"详情获取完成: 成功={success} 跳过={skip} 失败={fail}")


# =====================================================================
#  阶段 3：下载图片
# =====================================================================

def _get_ext(url):
    """从URL提取扩展名"""
    base = url.split("?")[0].lower()
    _, ext = os.path.splitext(base)
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return ext
    return ".jpg"


def download_images(api, images, done_classify_values=None):
    """逐张下载壁纸图片到本地 DOWNLOAD_DIR 目录。

    支持断点续传：文件已存在且非空则跳过。
    失败超过 MAX_RETRIES 次的图片不再重试。
    每 CHECKPOINT_SAVE_EVERY 张保存一次 checkpoint。

    Args:
        api: APIClient 实例
        images: {image_id: {..., "thumb_url": str, ...}}
               下载状态（download_path, download_retries）
               会写入此字典
        done_classify_values: 已完成的分类ID集合（用于 checkpoint 持久化）
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    total = len(images)
    image_ids = sorted(images.keys())

    # 统计已下载
    done_count = sum(
        1 for img_id in image_ids
        if images[img_id].get("download_path")
    )
    if done_count > 0:
        logger.info(
            f"断点续传: 已下载 {done_count}/{total} 张，跳过"
        )

    success = 0
    skip = 0
    fail = 0
    consecutive_errors = 0
    done_since_save = 0

    for idx, img_id in enumerate(image_ids, 1):
        info = images[img_id]

        # 已下载成功的跳过
        if info.get("download_path"):
            skip += 1
            continue

        # 失败次数超限则跳过
        retries = info.get("download_retries", 0)
        if retries >= MAX_RETRIES:
            logger.debug(
                f"  [id={img_id}] 已失败 {retries} 次，不再重试"
            )
            skip += 1
            continue

        thumb_url = info.get("thumb_url", "")
        if not thumb_url:
            logger.debug(f"  [id={img_id}] 无 thumb_url，跳过")
            info["download_path"] = ""
            info["download_retries"] = MAX_RETRIES
            fail += 1
            done_since_save += 1
            continue

        # 确定文件路径
        ext = _get_ext(thumb_url)
        filename = f"{img_id}{ext}"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        # 文件已存在 → 直接标记完成
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            size = os.path.getsize(filepath)
            info["download_path"] = filepath
            info["file_size"] = size
            skip += 1
            done_since_save += 1
            if skip <= 5 or skip % 200 == 0:
                logger.debug(
                    f"  [id={img_id}] 文件已存在，跳过 "
                    f"(已跳过 {skip} 张)"
                )
            continue

        # 下载
        try:
            tmp_path = filepath + ".tmp"
            file_size = api.download_image(thumb_url, tmp_path)
            if file_size > 0:
                os.replace(tmp_path, filepath)
                info["download_path"] = filepath
                info["file_size"] = file_size
                info["download_retries"] = 0
                success += 1
                consecutive_errors = 0
                done_since_save += 1
            else:
                _handle_download_fail(info, img_id)
                fail += 1
                done_since_save += 1
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as e:
            consecutive_errors += 1
            logger.error(
                f"  [id={img_id}] 下载失败: {e} "
                f"(连续失败 {consecutive_errors}/{MAX_RETRIES})"
            )
            _handle_download_fail(info, img_id)
            fail += 1
            done_since_save += 1
            for p in (filepath, filepath + ".tmp"):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            if consecutive_errors >= MAX_RETRIES:
                logger.error(
                    f"  连续失败 {consecutive_errors} 次，"
                    f"停止下载（已处理 {idx}/{total}）"
                )
                break
            time.sleep(RETRY_DELAY)

        # 定时保存断点
        if done_since_save >= CHECKPOINT_SAVE_EVERY:
            save_checkpoint({
                "phase": "downloads",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            done_since_save = 0

        # 进度输出
        if idx % 20 == 0 or idx == total:
            done = success + skip + fail
            logger.info(
                f"  下载进度: {done}/{total} ({done/total*100:.1f}%) "
                f"✓{success} ⊘{skip} ✗{fail}"
            )

    logger.info(f"下载完成: 成功={success} 跳过={skip} 失败={fail}")


def _handle_download_fail(info, image_id):
    """记录下载失败并递增重试计数"""
    retries = info.get("download_retries", 0) + 1
    info["download_path"] = ""
    info["download_retries"] = retries
    if retries >= MAX_RETRIES:
        logger.warning(
            f"  [id={image_id}] 已达到最大重试次数 ({retries})"
        )


# =====================================================================
#  阶段 4：压缩缩略图 & 提取尺寸
# =====================================================================

def _find_local_file(image_id):
    """根据 image_id 查找已下载的本地图片文件"""
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        path = os.path.join(DOWNLOAD_DIR, f"{image_id}{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None


def compress_thumbnails(images, done_classify_values=None):
    """提取图片尺寸 + 生成 WebP 缩略图。

    两步操作（顺序执行）：
      1. 读取本地图片 → 提取 width, height, aspect_ratio, file_size
      2. 按 THUMB_WIDTH 等比缩放 → 输出 {image_id}-thumbnail.webp

    支持断点续传：已有数据的图片自动跳过。
    每 CHECKPOINT_SAVE_EVERY 张保存一次 checkpoint。

    Args:
        images: {image_id: {...}}
               尺寸和缩略图字段会写入此字典
        done_classify_values: 已完成的分类ID集合（用于 checkpoint 持久化）
    """
    try:
        from PIL import Image
    except ImportError:
        logger.error(
            "压缩缩略图需要 Pillow 库，请执行: pip install Pillow"
        )
        sys.exit(1)

    total = len(images)
    image_ids = sorted(images.keys())
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # ===== 第一步：提取尺寸和文件大小 =====
    logger.info("\n--- 第一步：提取尺寸 & 文件大小 ---")
    dim_done = 0
    dim_skip = 0
    dim_miss = 0
    done_since_save = 0

    for idx, img_id in enumerate(image_ids, 1):
        info = images[img_id]

        # 已有尺寸的跳过
        if (
            info.get("width") and info.get("height")
            and info.get("file_size")
        ):
            dim_skip += 1
            continue

        filepath = _find_local_file(img_id)

        if filepath:
            try:
                with Image.open(filepath) as img:
                    w, h = img.size
                fsize = os.path.getsize(filepath)
                ratio = round(w / h, 4) if h else 0
                info["width"] = w
                info["height"] = h
                info["aspect_ratio"] = ratio
                info["file_size"] = fsize
                if not info.get("download_path"):
                    info["download_path"] = filepath
                dim_done += 1
                done_since_save += 1
            except Exception as e:
                logger.debug(
                    f"  [id={img_id}] 读取尺寸失败: {e}"
                )
                dim_miss += 1
        else:
            dim_miss += 1

        # 定时保存
        if done_since_save >= CHECKPOINT_SAVE_EVERY:
            save_checkpoint({
                "phase": "compress_dimensions",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            done_since_save = 0

        if (idx + 1) % 500 == 0:
            logger.info(
                f"  尺寸提取进度: {idx}/{total} "
                f"✓{dim_done} ⊘{dim_skip} ✗{dim_miss}"
            )

    logger.info(
        f"尺寸提取完成: 成功={dim_done} 跳过={dim_skip} 缺失={dim_miss}"
    )

    # ===== 第二步：批量压缩 WebP 缩略图 =====
    logger.info(
        f"\n--- 第二步：批量压缩 WebP 缩略图 (宽{THUMB_WIDTH}px) ---"
    )
    ok = 0
    cp_skip = 0
    cp_fail = 0
    cp_miss = 0
    done_since_save = 0

    for idx, img_id in enumerate(image_ids, 1):
        info = images[img_id]
        filepath = _find_local_file(img_id)

        if not filepath:
            cp_miss += 1
            continue

        # 缩略图命名: {image_id}-thumbnail.webp
        thumb_name = f"{img_id}-thumbnail.webp"
        thumb_path = os.path.join(DOWNLOAD_DIR, thumb_name)

        # 已存在 → 断点续传跳过
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            info["thumbnail"] = thumb_name
            cp_skip += 1
            done_since_save += 1
            continue

        try:
            with Image.open(filepath) as img:
                orig_w, orig_h = img.size
                new_h = int(THUMB_WIDTH * orig_h / orig_w)

                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")

                img = img.resize(
                    (THUMB_WIDTH, new_h), Image.LANCZOS
                )
                img.save(thumb_path, "WEBP", quality=WEBP_QUALITY)

            info["thumbnail"] = thumb_name
            ok += 1
            done_since_save += 1

        except Exception as e:
            logger.debug(f"  [id={img_id}] 压缩失败: {e}")
            cp_fail += 1
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass

        # 定时保存
        if done_since_save >= CHECKPOINT_SAVE_EVERY:
            save_checkpoint({
                "phase": "compress_thumbnails",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            done_since_save = 0

        if (idx + 1) % 200 == 0:
            logger.info(
                f"  压缩进度: {idx}/{total} "
                f"✓{ok} ⊘{cp_skip} ✗{cp_fail}"
            )

    logger.info(
        f"压缩完成: 成功={ok} 跳过={cp_skip} "
        f"失败={cp_fail} 缺失={cp_miss}"
    )


# =====================================================================
#  阶段 5：导出 JSON
# =====================================================================

def export_json(images, class_name_map):
    """将爬取数据导出为 default_wallpaper_data.json。

    格式示例:
    {
      "id": 178145,
      "describe": "Pristine waters...",
      "categories": [1, 437],
      "category_names": ["风景", "风景/湖海"],
      "name": "Pristine waters...",
      "thumb_url": "http://..."
    }

    如果完成了下载和压缩阶段，还会包含:
      "width": 4096, "height": 2304, "aspect_ratio": 1.7809,
      "file_size": 1234567, "thumbnail": "178145-thumbnail.webp"

    注意：categories 已过滤 class=0（无效分类）
    """
    result = []
    for img_id in sorted(images.keys()):
        info = images[img_id]

        # 过滤 class=0 的无效分类
        categories = sorted([
            c for c in info.get("categories", set()) if c != 0
        ])

        category_names = [class_name_map.get(c, str(c)) for c in categories]

        item = {
            "id": img_id,
            "describe": (info.get("describe") or "").strip(),
            "categories": categories,
            "category_names": category_names,
            "name": (info.get("name") or "").strip(),
            "thumb_url": info.get("thumb_url") or "",
        }

        # 可选字段：仅在完成对应阶段后输出
        if info.get("width") and info.get("height"):
            item["width"] = info["width"]
            item["height"] = info["height"]
            item["aspect_ratio"] = info.get("aspect_ratio")
            item["file_size"] = info.get("file_size", 0)
        if info.get("thumbnail"):
            item["thumbnail"] = info["thumbnail"]

        result.append(item)

    os.makedirs(RESULT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"\n导出完成: {len(result)} 条记录 -> {OUTPUT_FILE}")

    # 输出分类分布统计
    all_cats = Counter()
    for item in result:
        for cid in item["categories"]:
            all_cats[cid] += 1

    logger.info("分类分布:")
    for cid, cnt in all_cats.most_common():
        name = class_name_map.get(cid, str(cid))
        logger.info(f"  [{cid:>5}] {name:<20} {cnt} 张")


# =====================================================================
#  主函数
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="XZDesktop 壁纸数据爬取器 - 生成 default_wallpaper_data.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                      # 完整爬取（元数据 + 详情 + 导出）
  %(prog)s --download            # 爬取 + 下载图片
  %(prog)s --download --compress # 爬取 + 下载 + 尺寸提取 + 缩略图
  %(prog)s --metadata-only       # 仅爬取元数据，保存 checkpoint
  %(prog)s --detail-only         # 仅获取详情（需 checkpoint）
  %(prog)s --download-only       # 仅下载图片（需已完成详情）
  %(prog)s --compress-only       # 仅压缩缩略图（需已下载）
  %(prog)s --reset               # 清除断点，重新开始
        """
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="清除 checkpoint 重新开始"
    )
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="仅爬取元数据，保存 checkpoint"
    )
    parser.add_argument(
        "--detail-only", action="store_true",
        help="仅获取详情（需先有 checkpoint）"
    )
    parser.add_argument(
        "--download", action="store_true",
        help="完整模式中包含图片下载阶段"
    )
    parser.add_argument(
        "--download-only", action="store_true",
        help="仅下载图片（需已完成详情获取）"
    )
    parser.add_argument(
        "--compress", action="store_true",
        help="完整模式中包含尺寸提取 + 缩略图压缩阶段"
    )
    parser.add_argument(
        "--compress-only", action="store_true",
        help="仅压缩缩略图（需已下载图片）"
    )
    args = parser.parse_args()

    # 重置
    if args.reset and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        logger.info("已清除 checkpoint")

    # 初始化
    class_name_map = build_classify_name_map()
    classify_values = get_all_classify_values()
    logger.info(f"分类总数: {len(classify_values)} 个")
    logger.info(f"输出目录: {RESULT_DIR}")
    logger.info(f"输出文件: {OUTPUT_FILE}")
    if args.download or args.download_only:
        logger.info(f"下载目录: {DOWNLOAD_DIR}")

    api = APIClient()
    images = {}
    done_classify_values = set()

    try:
        # 获取壁纸库版本
        logger.info("正在获取壁纸库版本号...")
        try:
            wv = api.get_version()
            logger.info(f"壁纸版本号: {wv}")
        except Exception as e:
            logger.warning(f"获取版本号失败: {e}，使用空版本号继续")
            wv = ""

        # 加载 checkpoint
        checkpoint = load_checkpoint()
        if checkpoint:
            if checkpoint.get("images"):
                images = checkpoint["images"]
                logger.info(
                    f"加载 checkpoint: 已有 {len(images)} 张图片元数据"
                )
            if checkpoint.get("done_classify_values"):
                done_classify_values = set(
                    checkpoint["done_classify_values"]
                )
                logger.info(
                    f"加载 checkpoint: {len(done_classify_values)} "
                    f"个分类已完成"
                )

        # ---- 分步模式 ----

        if args.detail_only:
            if not images:
                logger.error("detail-only 需要已有 checkpoint")
                sys.exit(1)
            fetch_details(api, images, done_classify_values)
            save_checkpoint({
                "phase": "details_done",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            export_json(images, class_name_map)

        elif args.metadata_only:
            images = crawl_metadata(
                api, wv, classify_values, class_name_map,
                done_classify_values=done_classify_values,
            )
            done_classify_values = set(classify_values)
            save_checkpoint({
                "phase": "metadata_done",
                "wv": wv,
                "images": images,
                "done_classify_values": done_classify_values,
            })
            logger.info(
                f"\n元数据爬取完成: {len(images)} 张图片，"
                f"checkpoint 已保存"
            )

        elif args.download_only:
            if not images:
                logger.error("download-only 需要已有 checkpoint")
                sys.exit(1)
            download_images(api, images, done_classify_values)
            save_checkpoint({
                "phase": "downloads_done",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            export_json(images, class_name_map)

        elif args.compress_only:
            if not images:
                logger.error("compress-only 需要已有 checkpoint")
                sys.exit(1)
            compress_thumbnails(images, done_classify_values)
            save_checkpoint({
                "phase": "compress_done",
                "images": images,
                "done_classify_values": done_classify_values,
            })
            export_json(images, class_name_map)

        # ---- 完整流程模式 ----
        else:
            # 阶段 1: 元数据
            if not images or len(done_classify_values) < len(classify_values):
                logger.info(
                    f"继续爬取元数据: 已完成 "
                    f"{len(done_classify_values)}/{len(classify_values)} 个分类"
                )
                images = crawl_metadata(
                    api, wv, classify_values, class_name_map,
                    done_classify_values=done_classify_values,
                )
                done_classify_values = set(classify_values)
                save_checkpoint({
                    "phase": "metadata_done",
                    "wv": wv,
                    "images": images,
                    "done_classify_values": done_classify_values,
                })

            # 阶段 2: 详情
            fetch_details(api, images, done_classify_values)
            save_checkpoint({
                "phase": "details_done",
                "images": images,
                "done_classify_values": done_classify_values,
            })

            # 阶段 3: 下载（可选）
            if args.download or args.compress:
                download_images(api, images, done_classify_values)
                save_checkpoint({
                    "phase": "downloads_done",
                    "images": images,
                    "done_classify_values": done_classify_values,
                })

            # 阶段 4: 压缩（可选）
            if args.compress:
                compress_thumbnails(images, done_classify_values)
                save_checkpoint({
                    "phase": "compress_done",
                    "images": images,
                    "done_classify_values": done_classify_values,
                })

            export_json(images, class_name_map)

    except KeyboardInterrupt:
        logger.info("\n用户中断，进度已保存至 checkpoint")
        if images:
            save_checkpoint({
                "phase": "interrupted",
                "images": images,
                "done_classify_values": done_classify_values,
            })
    finally:
        api.close()


if __name__ == "__main__":
    main()
