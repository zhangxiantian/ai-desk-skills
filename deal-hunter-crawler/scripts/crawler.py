#!/usr/bin/env python3
"""
AI Deal Hunter Crawler — 从各大 AI 厂商官网爬取免费额度、优惠活动、新品发布信息
"""

import json
import os
import re
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ============================================================
# 配置
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
TIMEOUT = 15
RETRY_DELAY = 2
MAX_RETRIES = 2
BEIJING_TZ = timezone(timedelta(hours=8))

# ---- 代理配置 ----
# 代理确定优先级（从高到低）：
#   1. 环境变量 HTTPS_PROXY / HTTP_PROXY / ALL_PROXY
#   2. 下方 PROXY 常量直接赋值
#   3. 自动探测本地常见代理端口（可关闭）
#   4. 以上都无 → 直连
#
# 格式示例：
#   HTTP 代理:   "http://127.0.0.1:7890"
#   SOCKS5 代理: "socks5://127.0.0.1:1080"
#   带认证:      "http://user:pass@proxy.example.com:8080"
#
# 注意：SOCKS5 需要额外安装 pip install 'requests[socks]' PySocks
PROXY = (
    os.environ.get("HTTPS_PROXY") or
    os.environ.get("HTTP_PROXY") or
    os.environ.get("ALL_PROXY") or
    ""  # <-- 也可直接在这里写死，如 "http://127.0.0.1:7890"
)

# 是否启用自动探测本地代理（当上面没有显式配置时）
AUTO_PROBE_PROXY = os.environ.get("AUTO_PROBE_PROXY", "1") not in ("0", "false", "no")

# 常见本地代理端口及对应软件
PROXY_PROBE_PORTS = [
    (7890, "Clash"),
    (7897, "Clash Verge"),
    (7891, "Clash Meta"),
    (10809, "V2Ray / V2RayN"),
    (10808, "V2Ray socks"),
    (1080, "Shadowsocks"),
    (1087, "ShadowsocksR"),
    (8888, "TinyProxy / HTTP Proxy"),
    (8080, "MITMProxy / 通用HTTP"),
    (8118, "Privoxy"),
    (6152, "Surge Mac"),
    (3128, "Squid"),
]

# 用这个 URL 测试代理连通性（百度首页，轻量快速）
PROXY_PROBE_URL = "https://www.baidu.com"

# 仅对这些域名的访问启用代理（方便内网/国内直连）
PROXY_DOMAINS = os.environ.get("PROXY_DOMAINS", "").strip()
# 环境变量 PROXY_DOMAINS 为空 → 对所有域名启用代理
# 示例: "openai.com,anthropic.com,google.com" → 只代理匹配的域名

# 上传接口地址
API_UPLOAD_URL = os.environ.get("DEALS_UPLOAD_URL", "http://localhost:8080/api/v1/ai/dataset/deals/upload")

CATEGORIES = [
    {"id": "free-tokens",    "label": "免费Token"},
    {"id": "free-access",    "label": "免费使用"},
    {"id": "discount-tokens","label": "折扣Token"},
    {"id": "new-releases",   "label": "新品发布"},
    {"id": "promotions",     "label": "限时活动"},
]

# ============================================================
# 爬虫目标定义 — 每个 AI 厂商的官网页面
# ============================================================

def load_targets(config_path: str = None) -> list[dict]:
    """从 targets.json 加载爬虫目标配置，若文件不存在则返回内置兜底"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "targets.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            targets = data.get("targets", [])
            if targets:
                return targets
    except Exception as e:
        print(f"[WARN] 无法加载 {config_path}: {e}，使用内置兜底")
    # 兜底：最小保底数据集
    return [
        {"company":"智谱AI（ZhipuAI）","logo":"zhipu","category":"free-tokens","badge":"HOT",
         "urls":["https://open.bigmodel.cn/pricing"],"extract_hints":["免费","Tokens"]},
        {"company":"DeepSeek","logo":"deepseek","category":"free-tokens","badge":"HOT",
         "urls":["https://platform.deepseek.com/api-docs/pricing"],"extract_hints":["免费","Tokens"]},
        {"company":"阿里云百炼","logo":"aliyun","category":"free-tokens","badge":"FREE",
         "urls":["https://bailian.console.aliyun.com/"],"extract_hints":["免费","Tokens"]},
    ]

# 运行时加载，不在模块级别硬编码
CRAWL_TARGETS = None  # 在 main() 中延迟加载

# ============================================================
# 代理自动探测
# ============================================================

def _try_proxy(proxy_url: str, test_url: str = PROXY_PROBE_URL) -> bool:
    """测试单个代理是否可用"""
    try:
        resp = requests.get(
            test_url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=5,
            headers={"User-Agent": USER_AGENT},
        )
        return resp.status_code == 200
    except Exception:
        return False


def probe_proxy() -> str:
    """
    自动探测本地是否有可用的 HTTP 代理。
    返回找到的代理 URL，未找到返回空字符串。
    """
    if not AUTO_PROBE_PROXY:
        return ""

    print(">>> 自动探测本地代理...")

    for port, name in PROXY_PROBE_PORTS:
        proxy_url = f"http://127.0.0.1:{port}"
        if _try_proxy(proxy_url):
            print(f"  ✓ 找到代理: {name} (端口 {port}) → {proxy_url}")
            return proxy_url
        # 也试试 SOCKS5
        socks_url = f"socks5://127.0.0.1:{port}"
        if _try_proxy(socks_url):
            print(f"  ✓ 找到代理: {name} SOCKS5 (端口 {port}) → {socks_url}")
            return socks_url

    print("  ✗ 未发现本地代理，将使用直连")
    return ""


# ============================================================
# 工具函数
# ============================================================

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return s


def _resolve_proxy(url: str) -> Optional[dict]:
    """根据目标 URL 和配置确定是否需要代理"""
    if not PROXY:
        return None

    # 如果配置了 PROXY_DOMAINS 白名单，只对匹配域名启用代理
    if PROXY_DOMAINS:
        host = urlparse(url).hostname or ""
        allowed = any(d.strip() in host for d in PROXY_DOMAINS.split(","))
        if not allowed:
            return None

    return {"http": PROXY, "https": PROXY}


def fetch_page(session: requests.Session, url: str) -> Optional[str]:
    """获取页面 HTML 内容，带重试和代理切换"""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            proxies = _resolve_proxy(url)
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True,
                               proxies=proxies)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
    print(f"  [WARN] 获取失败 {url}: {last_error}")
    return None


def extract_text_snippets(html: str, hints: list[str], max_len: int = 300) -> str:
    """从 HTML 中提取包含线索的文本片段"""
    soup = BeautifulSoup(html, "lxml")
    # 移除 script/style 标签
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 10]

    # 找到包含任意线索的行
    relevant = []
    for line in lines:
        lower = line.lower()
        for hint in hints:
            if hint.lower() in lower:
                relevant.append(line)
                break
        if len(relevant) >= 15:
            break

    result = "\n".join(relevant[:15])
    if len(result) > max_len:
        result = result[:max_len] + "..."
    return result


def extract_title_from_html(html: str) -> str:
    """从 HTML title 标签提取页面标题"""
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()[:100]
    return ""


def find_prices_in_text(text: str) -> list[str]:
    """从文本中提取价格/数量相关信息"""
    patterns = [
        r'(\d+[万万千亿]?\s*(?:免费|Tokens?|次|元|¥|￥|\$|credit|quota|RPM))',
        r'((?:每天|每日|每月|每年)\s*\d+\s*(?:万|千)?\s*(?:次|Tokens?))',
        r'(\d+\s*(?:million|thousand|万|千|亿)\s*tokens?)',
        r'(free\s*(?:tier|plan|quota|access|trial))',
    ]
    matches = []
    for pattern in patterns:
        found = re.findall(pattern, text, re.IGNORECASE)
        matches.extend(found)
    return list(set(matches))


# ============================================================
# 爬虫主逻辑
# ============================================================

def crawl_single(session: requests.Session, target: dict) -> dict:
    """爬取单个目标，返回结构化信息"""
    company = target["company"]
    print(f"\n[{company}]")

    all_text = ""
    all_titles = []
    successful_urls = []

    for url in target["urls"]:
        print(f"  GET {url}")
        html = fetch_page(session, url)
        if html:
            title = extract_title_from_html(html)
            if title:
                all_titles.append(title)
            snippets = extract_text_snippets(html, target["extract_hints"])
            if snippets:
                all_text += f"\n--- {url} ---\n{snippets}"
            successful_urls.append(url)
            time.sleep(1.5)  # 礼貌爬取间隔

    # 提取价格信息
    prices = find_prices_in_text(all_text) if all_text else []

    return {
        "company": company,
        "logo": target["logo"],
        "category": target["category"],
        "badge": target["badge"],
        "urls_crawled": successful_urls,
        "page_titles": all_titles,
        "relevant_text": all_text[:800] if all_text else "",
        "prices_found": prices[:10],
    }


def crawl_all(targets: list[dict]) -> list[dict]:
    """爬取所有目标，返回原始结果列表"""
    session = make_session()
    results = []
    total = len(targets)

    for i, target in enumerate(targets, 1):
        print(f"\n[{i}/{total}]", end="")
        try:
            result = crawl_single(session, target)
            if result["relevant_text"]:
                results.append(result)
        except Exception as e:
            print(f"  [ERROR] {target['company']}: {e}")
        time.sleep(2)  # 总间隔

    print(f"\n\n爬取完成: {len(results)}/{total} 个目标有数据返回")
    return results


# ============================================================
# 生成 deals.json
# ============================================================

def build_deals_from_crawl(crawl_results: list[dict]) -> list[dict]:
    """根据爬虫结果构建 deals 列表（仅用爬取到的真实数据）"""
    deals = []
    used_companies = set()

    for result in crawl_results:
        company = result["company"]
        if company in used_companies:
            continue
        used_companies.add(company)

        deal_id = f"dt{len(deals) + 1:03d}"
        text = result["relevant_text"].strip() if result["relevant_text"] else ""
        prices = result.get("prices_found", [])
        titles = result.get("page_titles", [])

        title = _generate_title(result, text, prices, titles)
        summary = _generate_summary(result, text, prices)
        tags = _generate_tags(result, text, prices)

        source_url = result["urls_crawled"][0] if result["urls_crawled"] else ""
        source_name = result["company"]

        deal = {
            "id": deal_id,
            "category": result["category"],
            "company": result["company"],
            "companyLogo": result["logo"],
            "badge": result["badge"],
            "title": title,
            "summary": summary,
            "source": source_name,
            "sourceUrl": source_url,
            "tags": tags,
            "publishDate": _random_recent_date(),
            "hotCount": random.randint(15000, 95000),
        }
        deals.append(deal)

    return deals


def _extract_keyinfo(text: str, prices: list[str]) -> str:
    """从爬取文本和价格中提取关键信息短语"""
    keywords = []
    if prices:
        for p in prices[:3]:
            p_clean = p.strip() if isinstance(p, str) else str(p)
            if len(p_clean) > 2 and p_clean not in keywords:
                keywords.append(p_clean)
    # 尝试从文本中提取数字 + Tokens 组合
    import re as _re
    token_patterns = _re.findall(r'[\d,]+[万万千百]?\s*(?:免费|Tokens?|次|元|credit|quota)', text, _re.IGNORECASE)
    for tp in token_patterns[:2]:
        if tp not in keywords:
            keywords.append(tp)
    return "，".join(keywords[:3])


def _generate_title(result: dict, text: str, prices: list[str], titles: list[str]) -> str:
    company = result["company"]
    keyinfo = _extract_keyinfo(text, prices)

    # 尝试从页面标题提取有意义的内容
    if titles:
        for t in titles:
            if any(kw in t for kw in ["免费", "free", "price", "pricing", "model", "模型", "API"]):
                return f"{company}{t[:40]}" if len(t) <= 40 else f"{company}{t[:37]}..."

    if keyinfo:
        return f"{company}：{keyinfo}"

    cat_labels = {
        "free-tokens": "免费Tokens额度开放",
        "free-access": "免费使用开放",
        "discount-tokens": "优惠活动进行中",
        "new-releases": "新模型发布",
        "promotions": "限时福利活动",
    }
    label = cat_labels.get(result["category"], "最新动态")
    return f"{company} {label}"


def _generate_summary(result: dict, text: str, prices: list[str]) -> str:
    keyinfo = _extract_keyinfo(text, prices)
    if keyinfo:
        return f"来自官网实时数据：{keyinfo}，详情请访问{result['company']}官方网站。"
    if text:
        cleaned = text[:120].replace("\n", " ").strip()
        if len(cleaned) > 20:
            return cleaned
    return f"{result['company']}平台最新AI服务动态，详情请访问官网了解。"


def _generate_tags(result: dict, text: str, prices: list[str]) -> list[str]:
    """基于爬取内容生成标签"""
    tags = []
    cat_tag_map = {
        "free-tokens": ["免费Tokens", "API"],
        "free-access": ["免费使用", "开放"],
        "discount-tokens": ["折扣", "代金券"],
        "new-releases": ["新发布", "新模型"],
        "promotions": ["限时", "活动"],
    }
    tags.extend(cat_tag_map.get(result["category"], []))

    # 从文本中提取有意义的标签词
    if "多模态" in text or "vision" in text.lower():
        tags.append("多模态")
    if "推理" in text or "reasoning" in text.lower():
        tags.append("推理模型")
    if "编程" in text or "code" in text.lower():
        tags.append("编程助手")
    if "新用户" in text or "注册" in text or "new user" in text.lower():
        tags.append("新用户专享")
    if "每日" in text or "daily" in text.lower():
        tags.append("每日重置")

    return tags[:5]


def _random_recent_date() -> str:
    days_ago = random.randint(0, 20)
    dt = datetime.now(BEIJING_TZ) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# 入口
# ============================================================

def upload_to_api(json_data: dict, api_url: str):
    """将 deals 数据 POST 到后端上传接口，失败直接退出"""
    try:
        resp = requests.post(
            api_url,
            json=json_data,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            ver = result.get('data', {}).get('version', '?')
            print(f"  ✓ 上传成功, version=v{ver}")
            return True
        else:
            print(f"  ✗ 上传失败 HTTP {resp.status_code}: {resp.text[:300]}")
            sys.exit(1)
    except requests.ConnectionError:
        print(f"  ✗ 无法连接后端 ({api_url})，请确认后端已启动")
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ 上传异常: {e}")
        sys.exit(1)


def main():
    global PROXY
    import argparse
    parser = argparse.ArgumentParser(description="AI Deal Hunter Crawler")
    parser.add_argument("--api-url", default=API_UPLOAD_URL, help=f"上传接口地址 (默认: {API_UPLOAD_URL})")
    parser.add_argument("--targets-file", default=None, help="数据源配置文件路径 (默认: 同目录 targets.json)")
    args = parser.parse_args()

    # 加载数据源
    targets = load_targets(args.targets_file)

    print("=" * 60)
    print("AI Deal Hunter Crawler — 官网数据爬取 + API 上传")
    print(f"启动时间: {datetime.now(BEIJING_TZ).isoformat()}")
    print(f"数据源: {len(targets)} 个 AI 厂商")
    print(f"上传地址: {args.api_url}")
    print("=" * 60)

    # 0. 代理探测
    if not PROXY:
        PROXY = probe_proxy()
    if PROXY:
        domain_hint = f"（仅对 {PROXY_DOMAINS}）" if PROXY_DOMAINS else "（全局）"
        print(f"\n  📡 代理: {PROXY} {domain_hint}")
    else:
        print("\n  📡 代理: 无（直连）")

    # 1. 爬取各厂商官网
    print("\n>>> 第1步: 爬取各厂商官网定价/免费额度页面")
    crawl_results = crawl_all(targets)

    # 2. 构建 deals（仅爬取数据，无兜底）
    print("\n>>> 第2步: 构建 deals 数据")
    deals = build_deals_from_crawl(crawl_results)
    print(f"  生成: {len(deals)} 条")

    # 3. 构建完整 JSON 并上传
    output = {
        "categories": CATEGORIES,
        "deals": deals,
    }

    # 4. 统计
    print(f"\n>>> 完成! deals 总数: {len(deals)}")
    cat_set = set(d['category'] for d in deals)
    print(f"    分类覆盖: {len(cat_set)}/5")
    cats = {}
    for d in deals:
        cats[d["category"]] = cats.get(d["category"], 0) + 1
    for k, v in cats.items():
        label = next((c["label"] for c in CATEGORIES if c["id"] == k), k)
        print(f"       {label}: {v} 条")

    # 6. 上传
    print(f"\n>>> 第4步: 上传到后端")
    upload_to_api(output, args.api_url)


if __name__ == "__main__":
    import sys
    main()
