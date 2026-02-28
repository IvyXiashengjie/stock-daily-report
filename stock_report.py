"""
独立版股市日报生成器 - 用于 GitHub Actions 定时运行
直接抓取新闻 + 调用通义千问 API 生成报告
不依赖 Dify，可在任何环境运行
"""

import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime


# ============ 新闻抓取部分 ============

def fetch_cls_news(market_filter=None):
    """从财联社抓取快讯"""
    url = "https://www.cls.cn/nodeapi/updateTelegraphList?app=CailianpressWeb&os=web&sv=8.4.6&rn=50"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.cls.cn/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        articles = []
        for item in data.get("data", {}).get("roll_data", []):
            content = re.sub(r"<[^>]+>", "", item.get("content", ""))
            ctime = item.get("ctime", 0)
            time_str = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M") if ctime else ""
            subjects = [s.get("subject_name", "") for s in item.get("subjects", [])]
            subject_str = " ".join(subjects)
            is_hk = any(kw in subject_str for kw in ["港股", "港交所", "HK"]) or any(kw in content for kw in ["港股", "恒生", "港交所", "恒指"])
            is_us = any(kw in subject_str for kw in ["美股", "美联储", "纳斯达克"]) or any(kw in content for kw in ["美股", "纳指", "标普", "道指"])
            if market_filter == "HK" and not is_hk:
                continue
            if market_filter == "A" and (is_hk or is_us):
                continue
            market_label = "港股" if is_hk else ("美股" if is_us else "A股")
            title = item.get("title", "") or content[:50]
            articles.append({"title": title, "summary": content[:200], "time": time_str, "source": "财联社", "market": market_label})
            if len(articles) >= 15:
                break
        return articles
    except Exception as e:
        return [{"error": str(e), "source": "财联社", "market": "A股"}]


def fetch_eastmoney_news():
    """从东方财富抓取A股新闻"""
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=350&order=1&needInteractData=0&page_index=1&page_size=15&req_trace=a"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        articles = []
        for item in data.get("data", {}).get("list", [])[:15]:
            articles.append({"title": item.get("title", ""), "summary": item.get("digest", "")[:200], "time": item.get("showTime", ""), "source": "东方财富", "market": "A股"})
        return articles
    except Exception as e:
        return [{"error": str(e), "source": "东方财富", "market": "A股"}]


def fetch_eastmoney_kuaixun(type_id="111", market="美股"):
    """从东方财富快讯API抓取"""
    url = f"https://newsapi.eastmoney.com/kuaixun/v1/getlist_{type_id}_ajaxResult_15_1_.html"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            json_str = raw[raw.index("{"):raw.rindex("}") + 1]
            data = json.loads(json_str)
        articles = []
        for item in data.get("LivesList", [])[:15]:
            articles.append({"title": item.get("title", ""), "summary": item.get("digest", item.get("title", ""))[:200], "time": item.get("showtime", ""), "source": "东方财富", "market": market})
        return articles
    except Exception as e:
        return [{"error": str(e), "source": "东方财富", "market": market}]


def fetch_sina_us_stock():
    """从新浪财经抓取美股新闻"""
    url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=15&page=1"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        articles = []
        for item in data.get("result", {}).get("data", [])[:15]:
            title = re.sub(r"<[^>]+>", "", item.get("title", "").replace("&nbsp;", " ").replace("&amp;", "&"))
            ctime = item.get("ctime", "")
            time_str = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M") if ctime else ""
            intro = re.sub(r"<[^>]+>", "", item.get("intro", ""))
            articles.append({"title": title, "summary": (intro or title)[:200], "time": time_str, "source": "新浪财经", "market": "美股"})
        return articles
    except Exception as e:
        return [{"error": str(e), "source": "新浪财经", "market": "美股"}]


def fetch_eastmoney_hk():
    """从东方财富抓取港股新闻"""
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=351&order=1&needInteractData=0&page_index=1&page_size=15&req_trace=a"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://hk.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        articles = []
        for item in data.get("data", {}).get("list", [])[:15]:
            articles.append({"title": item.get("title", ""), "summary": item.get("digest", "")[:200], "time": item.get("showTime", ""), "source": "东方财富", "market": "港股"})
        return articles
    except Exception as e:
        return [{"error": str(e), "source": "东方财富", "market": "港股"}]


def fetch_all_news():
    """抓取全部市场新闻"""
    news = []
    news.extend(fetch_cls_news(market_filter="A"))
    news.extend(fetch_eastmoney_news())
    news.extend(fetch_sina_us_stock())
    news.extend(fetch_eastmoney_kuaixun(type_id="111", market="美股"))
    news.extend(fetch_cls_news(market_filter="HK"))
    news.extend(fetch_eastmoney_hk())
    return news


def format_news(news_list):
    """将新闻列表格式化为文本"""
    markets = {"A股": [], "美股": [], "港股": []}
    for item in news_list:
        if "error" in item:
            continue
        market = item.get("market", "其他")
        if market in markets:
            markets[market].append(item)

    lines = [f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}", f"共抓取 {len(news_list)} 条新闻\n"]
    for market_name, articles in markets.items():
        if not articles:
            continue
        lines.append(f"\n## {market_name} ({len(articles)}条)")
        for i, a in enumerate(articles[:15], 1):
            lines.append(f"{i}. [{a.get('time','')}] {a.get('title','')}")
            summary = a.get("summary", "")
            if summary and summary != a.get("title", ""):
                lines.append(f"   {summary[:120]}")
    return "\n".join(lines)


# ============ LLM 分析部分 ============

SYSTEM_PROMPT = "你是一位资深金融分析师，擅长解读股市新闻并生成专业的每日市场简报。你的分析客观、专业、简洁。"

USER_PROMPT_TEMPLATE = """请根据以下今日股市新闻，生成一份专业的《每日股市简报》。

要求：
1. **市场总览**：用2-3句话概括今日A股、美股、港股的整体动向
2. **重要新闻TOP5**：提取最重要的5条新闻，简要说明其影响
3. **个股聚焦**：如有值得关注的个股动态，列出并简析
4. **市场情绪**：基于新闻判断当前市场情绪（乐观/中性/悲观），说明理由
5. **明日展望**：基于今日消息面，简要预判明日可能走向

格式：Markdown，结构清晰，语言专业简洁。

---
今日新闻数据：

{news_text}"""


def call_tongyi(news_text):
    """调用通义千问 API"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return "错误：未设置 DASHSCOPE_API_KEY 环境变量"

    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    payload = json.dumps({
        "model": "qwen-turbo",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(news_text=news_text)},
        ],
        "temperature": 0.5,
        "max_tokens": 4096,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return f"API 调用失败: HTTP {e.code} - {body[:300]}"
    except Exception as e:
        return f"API 调用失败: {str(e)}"


# ============ 推送部分 ============

def send_webhook(text):
    """推送到企业微信/钉钉/飞书 Webhook"""
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if not webhook_url:
        return

    if "qyapi.weixin" in webhook_url:
        payload = json.dumps({"msgtype": "markdown", "markdown": {"content": text[:4096]}})
    elif "dingtalk" in webhook_url:
        payload = json.dumps({"msgtype": "markdown", "markdown": {"title": "股市日报", "text": text[:4096]}})
    elif "feishu" in webhook_url or "larksuite" in webhook_url:
        payload = json.dumps({"msg_type": "text", "content": {"text": text[:4096]}})
    else:
        payload = json.dumps({"text": text[:4096]})

    req = urllib.request.Request(webhook_url, data=payload.encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Webhook 推送成功: {resp.status}")
    except Exception as e:
        print(f"Webhook 推送失败: {e}")


# ============ 主流程 ============

def main():
    print(f"[{datetime.now()}] 开始生成股市日报...")

    # 1. 抓取新闻
    print("正在抓取新闻...")
    news = fetch_all_news()
    valid = [n for n in news if "error" not in n]
    errors = [n for n in news if "error" in n]
    print(f"  抓取完成: {len(valid)} 条新闻, {len(errors)} 个错误")

    if not valid:
        print("没有抓取到任何新闻，退出")
        return

    # 2. 格式化
    news_text = format_news(news)

    # 3. 调用 LLM 生成报告
    print("正在生成分析报告...")
    report = call_tongyi(news_text)

    # 4. 输出
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)

    # 5. 写入文件（供 GitHub Actions artifact 保存）
    report_file = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# 每日股市简报 - {datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write(report)
    print(f"\n报告已保存至: {report_file}")

    # 6. 设置 GitHub Actions 输出
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"report_file={report_file}\n")

    # 7. 推送 Webhook
    send_webhook(report)

    print(f"\n[{datetime.now()}] 完成")


if __name__ == "__main__":
    main()
