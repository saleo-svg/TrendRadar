# coding=utf-8
"""
URL 处理工具模块

提供 URL 标准化功能，用于去重时消除动态参数的影响：
- normalize_url: 标准化 URL，去除动态参数
- parse_url_resource: 解析 URL 推断资源类型（关键词搜索/问题/文章/热榜条目等）
"""

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from typing import Dict, Set, Optional, Tuple


# 各平台需要移除的特定参数
#   - weibo: 有 band_rank（排名）和 Refer（来源）动态参数
#   - 其他平台: URL 为路径格式或简单关键词查询，无需处理
PLATFORM_PARAMS_TO_REMOVE: Dict[str, Set[str]] = {
    # 微博：band_rank 是动态排名参数，Refer 是来源参数，t 是时间范围参数
    # 示例：https://s.weibo.com/weibo?q=xxx&t=31&band_rank=1&Refer=top
    # 保留：q（关键词）
    # 移除：band_rank, Refer, t
    "weibo": {"band_rank", "Refer", "t"},
}

# 通用追踪参数（适用于所有平台）
# 这些参数通常由分享链接或广告追踪添加，不影响内容识别
COMMON_TRACKING_PARAMS: Set[str] = {
    # UTM 追踪参数
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    # 常见追踪参数
    "ref", "referrer", "source", "channel",
    # 时间戳和随机参数
    "_t", "timestamp", "_", "random",
    # 分享相关
    "share_token", "share_id", "share_from",
}


def normalize_url(url: str, platform_id: str = "") -> str:
    """
    标准化 URL，去除动态参数

    用于数据库去重，确保同一条新闻的不同 URL 变体能被正确识别为同一条。

    处理规则：
    1. 去除平台特定的动态参数（如微博的 band_rank）
    2. 去除通用追踪参数（如 utm_*）
    3. 保留核心查询参数（如搜索关键词 q=, wd=, keyword=）
    4. 对查询参数按字母序排序（确保一致性）

    Args:
        url: 原始 URL
        platform_id: 平台 ID，用于应用平台特定规则

    Returns:
        标准化后的 URL

    Examples:
        >>> normalize_url("https://s.weibo.com/weibo?q=test&band_rank=6&Refer=top", "weibo")
        'https://s.weibo.com/weibo?q=test'

        >>> normalize_url("https://example.com/page?id=1&utm_source=twitter", "")
        'https://example.com/page?id=1'
    """
    if not url:
        return url

    try:
        # 解析 URL
        parsed = urlparse(url)

        # 如果没有查询参数，直接返回
        if not parsed.query:
            return url

        # 解析查询参数
        params = parse_qs(parsed.query, keep_blank_values=True)

        # 收集需要移除的参数（使用小写进行比较）
        params_to_remove: Set[str] = set()

        # 添加通用追踪参数
        params_to_remove.update(COMMON_TRACKING_PARAMS)

        # 添加平台特定参数
        if platform_id and platform_id in PLATFORM_PARAMS_TO_REMOVE:
            params_to_remove.update(PLATFORM_PARAMS_TO_REMOVE[platform_id])

        # 过滤参数（参数名转小写进行比较）
        filtered_params = {
            key: values
            for key, values in params.items()
            if key.lower() not in {p.lower() for p in params_to_remove}
        }

        # 如果过滤后没有参数了，返回不带查询字符串的 URL
        if not filtered_params:
            return urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                "",  # 空查询字符串
                ""   # 移除 fragment
            ))

        # 重建查询字符串（按字母序排序以确保一致性）
        sorted_params = []
        for key in sorted(filtered_params.keys()):
            for value in filtered_params[key]:
                sorted_params.append((key, value))

        new_query = urlencode(sorted_params)

        # 重建 URL（移除 fragment）
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            ""  # 移除 fragment
        ))

        return normalized

    except Exception:
        # 解析失败时返回原始 URL
        return url


# ============================================================
# 资源类型推断
#
# 不同新闻平台的 URL 格式不同，从 URL 路径可以推断这条新闻的"资源类型"：
#   - 关键词搜索: s.weibo.com/weibo?q=xxx        → 微博关键词搜索结果
#   - 问题/问答:   zhihu.com/question/123         → 知乎问题 ID 123
#   - 文章:        wallstreetcn.com/articles/123 → 文章 ID 123
#   - 热榜条目:    douyin.com/hot/123             → 抖音热榜条目 ID 123
#   - 话题:        tieba.baidu.com/...topic_id=123 → 百度贴吧话题
#
# 返回 (resource_type, resource_id, search_keyword) 三元组。
# 例如:
#   parse_url_resource("https://s.weibo.com/weibo?q=AI", "weibo")
#   → ("关键词搜索", None, "AI")
#
#   parse_url_resource("https://www.zhihu.com/question/123456", "zhihu")
#   → ("问题", "123456", None)
# ============================================================

# 各平台的资源类型识别规则（按 (path 前缀, query 参数) → 资源类型 顺序匹配）
# 规则格式: (path_match, query_match, resource_type, id_param_or_path_part)
URL_RESOURCE_RULES = [
    # 微博 - 关键词搜索
    ("weibo.com/weibo", "q", "关键词搜索", "query"),
    # 知乎 - 问题（优先匹配，可能附带 answer 路径）
    ("zhihu.com/question", None, "问题", "path_id"),
    # 知乎 - 视频
    ("zhihu.com/video", None, "视频", "path_id"),
    ("zhihu.com/zvideo", None, "视频", "path_id"),
    # 知乎 - 回答（必须以 /answer 开头，避免误伤 /question/123/answer/456）
    ("zhihu.com/answer", None, "回答", "path_id_strip_prefix:"),
    # 抖音 - 热榜条目
    ("douyin.com/hot", None, "热榜条目", "path_id"),
    # 头条 - 热榜条目
    ("toutiao.com/trending", None, "热榜条目", "path_id"),
    # 贴吧 - 话题
    ("tieba.baidu.com/hottopic/browse/hottopic", "topic_id", "热议话题", "query"),
    # 百度 - 关键词搜索
    ("baidu.com/s", "wd", "关键词搜索", "query"),
    # B站 - 关键词搜索
    ("bilibili.com/all", "keyword", "关键词搜索", "query"),
    ("bilibili.com/search", "keyword", "关键词搜索", "query"),
    # B站 - 视频
    ("bilibili.com/video", None, "视频", "path_id"),
    # 华尔街见闻 - 文章
    ("wallstreetcn.com/articles", None, "文章", "path_id"),
    # 澎湃 - 文章（ID 在路径里带前缀）
    ("thepaper.cn/newsDetail_forward_", None, "文章", "path_id_strip_prefix:newsDetail_forward_"),
    # 财联社 - 文章
    ("cls.cn/detail", None, "文章", "path_id"),
    # 凤凰 - 文章
    ("ifeng.com/c/", None, "文章", "path_id"),
    # GitHub - 仓库
    ("github.com/", None, "仓库/项目", "path"),
]


def parse_url_resource(url: str, platform_id: str = "") -> Dict[str, Optional[str]]:
    """
    从 URL 推断新闻的资源类型

    Args:
        url: 新闻链接
        platform_id: 平台 ID（备用上下文，目前未直接使用）

    Returns:
        dict: {
            "type": 资源类型名称（如 "关键词搜索"/"问题"/"文章"），
                   若无法识别则为空字符串
            "id": 资源 ID（如问题 ID、文章 ID），无则为空字符串
            "keyword": 搜索关键词（关键词搜索类），无则为空字符串
            "url": 原始 URL
        }
    """
    result: Dict[str, Optional[str]] = {
        "type": "",
        "id": "",
        "keyword": "",
        "url": url or "",
    }

    if not url:
        return result

    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        path = "/" + path.strip("/") if path else "/"
        query = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        return result

    full_path_lower = path.lower()
    query_string = parsed.query or ""

    # 把 host 和 path 拼起来，得到完整小写 URL（不含 query/fragment）
    full_url_lower = (host + path).lower()

    # 收集所有命中规则，最后选择路径前缀最长的（更具体的规则胜出）
    # 例：/question/123/answer/456 同时匹配 "zhihu.com/question" 和 "zhihu.com/answer"
    # 让长 prefix 胜出
    candidates = []

    for path_match, query_param, resource_type, id_source in URL_RESOURCE_RULES:
        path_match_lower = path_match.lower()

        # 规则必须以 host 开头 或 包含 host（保证域名匹配）
        if path_match_lower not in full_url_lower:
            continue

        # 检查 query 参数
        if query_param is not None:
            if query_param not in query:
                continue

        # 规则得分：长度越长越具体
        score = len(path_match_lower)

        # 找到 path_match 在 full_url_lower 中的位置
        idx = full_url_lower.find(path_match_lower)
        if idx >= 0:
            # 如果 path_match 之后紧跟 / 或 URL 结尾，给额外分数（表示是完整路径段）
            after_idx = idx + len(path_match_lower)
            if after_idx >= len(full_url_lower) or full_url_lower[after_idx] in ("/", "?", "#"):
                score += 5000  # 完整路径段命中，强力优先
            # 位置越靠后，分数越低（path 前段的优先级更高）
            # idx 越大越靠后，扣分
            score -= idx * 2

        candidates.append((score, path_match_lower, path_match, query_param, resource_type, id_source))

    if not candidates:
        return result

    # 按 score 降序，score 相同时按规则列表顺序（保持稳定排序）
    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda x: (-x[1][0], x[0]))
    _, (score, path_match_lower, path_match, query_param, resource_type, id_source) = indexed[0]

    # 命中规则，提取 ID
    # 把 path 拆成段
    path_segments = [p for p in path.split("/") if p]
    # path_match 是 "host.com/some/path"，拆出尾部路径段
    path_match_tail = path_match_lower.split("/", 1)[1] if "/" in path_match_lower else path_match_lower

    if id_source == "query":
        # 从 URL 参数取值
        values = query.get(query_param, []) if query_param else []
        value = values[0] if values else ""
        if not value:
            return result
        if resource_type == "关键词搜索":
            result["keyword"] = value
        else:
            result["id"] = value
    elif id_source == "path_id":
        # 从 path_match 之后紧跟的那段路径取 ID
        # 例如 path_match = "zhihu.com/question", path = "/question/123/answer/456"
        # 尾部路径段 = "question"，找到它在 path_segments 中的位置，取下一段 "123"
        try:
            seg_idx = path_segments.index(path_match_tail)
            if seg_idx + 1 < len(path_segments):
                result["id"] = path_segments[seg_idx + 1]
            else:
                # 没有下一段，回退到最后一段
                result["id"] = path_segments[-1] if path_segments else ""
        except ValueError:
            # path_match_tail 不在 path 中（异常情况），回退到最后一段
            result["id"] = path_segments[-1] if path_segments else ""
    elif id_source == "path":
        # 整个路径作为标识
        result["id"] = path.strip("/")
    elif id_source.startswith("path_id_strip_prefix:"):
        # 从 path_match 之后紧跟的那段路径取 ID，并去掉前导前缀
        prefix = id_source.split(":", 1)[1]
        try:
            seg_idx = path_segments.index(path_match_tail)
            if seg_idx + 1 < len(path_segments):
                value = path_segments[seg_idx + 1]
            else:
                value = path_segments[-1] if path_segments else ""
        except ValueError:
            value = path_segments[-1] if path_segments else ""
        if not value:
            return result
        if value.startswith(prefix):
            value = value[len(prefix):]
        result["id"] = value

    result["type"] = resource_type
    return result


def format_resource_label(meta: Dict[str, Optional[str]]) -> str:
    """
    把资源类型 dict 格式化成简短标签，例如：
    {"type":"关键词搜索","keyword":"AI"} → "搜索:AI"
    {"type":"问题","id":"123"} → "问题#123"
    {"type":"文章","id":"456"} → "文章#456"
    {"type":"", ...} → ""
    """
    rtype = meta.get("type") or ""
    if not rtype:
        return ""

    if rtype == "关键词搜索":
        kw = meta.get("keyword") or ""
        if kw:
            # 截短长关键词
            display = kw if len(kw) <= 16 else kw[:15] + "…"
            return f"搜索:{display}"
        return "搜索"
    if meta.get("id"):
        return f"{rtype}#{meta['id']}"
    return rtype
