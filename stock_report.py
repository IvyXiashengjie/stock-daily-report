"""
独立版股市日报生成器 - 用于 GitHub Actions 定时运行
直接抓取新闻 + 调用通义千问 API 生成报告
支持微信推送（Server酱）+ GitHub Pages 详情页
"""

import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime


# ============ 指数行情抓取 ============

def fetch_index_quotes():
    """从新浪财经抓取主要指数实时行情"""
    symbols = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "int_hangseng": "恒生指数",
        "int_dji": "道琼斯",
        "int_nasdaq": "纳斯达克",
        "int_sp500": "标普500",
    }
    results = []
    for code, name in symbols.items():
        try:
            url = f"https://hq.sinajs.cn/list={code}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("gbk")
            parts = raw.split('"')[1].split(",")
            if code.startswith("sh") or code.startswith("sz"):
                price = float(parts[3])
                prev_close = float(parts[2])
                change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0
                results.append({"name": name, "code": code, "price": f"{price:.2f}", "change": f"{change_pct:+.2f}%"})
            elif code.startswith("int_"):
                price = float(parts[1])
                change = float(parts[4]) if len(parts) > 4 else 0
                change_pct = float(parts[5].replace("%", "")) if len(parts) > 5 else 0
                results.append({"name": name, "code": code, "price": f"{price:.2f}", "change": f"{change_pct:+.2f}%"})
        except Exception:
            results.append({"name": name, "code": code, "price": "--", "change": "--"})
    return results


# ============ 新闻抓取部分 ============

def fetch_cls_news(market_filter=None):
    """从财联社抓取快讯"""
    url = "https://www.cls.cn/nodeapi/updateTelegraphList?app=CailianpressWeb&os=web&sv=8.4.6&rn=50"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", "Referer": "https://www.cls.cn/"}
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
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=350&order=1&needInteractData=0&page_index=1&page_size=15&req_trace=a"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return [{"title": item.get("title", ""), "summary": item.get("digest", "")[:200], "time": item.get("showTime", ""), "source": "东方财富", "market": "A股"} for item in data.get("data", {}).get("list", [])[:15]]
    except Exception as e:
        return [{"error": str(e), "source": "东方财富", "market": "A股"}]


def fetch_eastmoney_kuaixun(type_id="111", market="美股"):
    url = f"https://newsapi.eastmoney.com/kuaixun/v1/getlist_{type_id}_ajaxResult_15_1_.html"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            json_str = raw[raw.index("{"):raw.rindex("}") + 1]
            data = json.loads(json_str)
        return [{"title": item.get("title", ""), "summary": item.get("digest", item.get("title", ""))[:200], "time": item.get("showtime", ""), "source": "东方财富", "market": market} for item in data.get("LivesList", [])[:15]]
    except Exception as e:
        return [{"error": str(e), "source": "东方财富", "market": market}]


def fetch_sina_us_stock():
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
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=351&order=1&needInteractData=0&page_index=1&page_size=15&req_trace=a"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://hk.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return [{"title": item.get("title", ""), "summary": item.get("digest", "")[:200], "time": item.get("showTime", ""), "source": "东方财富", "market": "港股"} for item in data.get("data", {}).get("list", [])[:15]]
    except Exception as e:
        return [{"error": str(e), "source": "东方财富", "market": "港股"}]


def fetch_all_news():
    news = []
    news.extend(fetch_cls_news(market_filter="A"))
    news.extend(fetch_eastmoney_news())
    news.extend(fetch_sina_us_stock())
    news.extend(fetch_eastmoney_kuaixun(type_id="111", market="美股"))
    news.extend(fetch_cls_news(market_filter="HK"))
    news.extend(fetch_eastmoney_hk())
    return news


def format_news(news_list):
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
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
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


# ============ HTML 详情页生成 ============

def markdown_to_html(md):
    """将 Markdown 转为结构化 HTML"""
    sections = []
    current_section = {"title": "", "content": []}

    for line in md.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 标题行 → 新 section
        h_match = re.match(r"^#{1,3}\s+(.+)$", line)
        if h_match:
            if current_section["title"] or current_section["content"]:
                sections.append(current_section)
            current_section = {"title": h_match.group(1), "content": []}
            continue
        # 加粗
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        # 有序列表
        ol_match = re.match(r"^(\d+)\.\s+(.+)$", line)
        if ol_match:
            current_section["content"].append(("ol", ol_match.group(1), ol_match.group(2)))
            continue
        # 无序列表
        ul_match = re.match(r"^[-*]\s+(.+)$", line)
        if ul_match:
            current_section["content"].append(("ul", ul_match.group(1)))
            continue
        # 分隔线
        if line == "---":
            continue
        # 普通段落
        current_section["content"].append(("p", line))

    if current_section["title"] or current_section["content"]:
        sections.append(current_section)

    # 渲染
    section_icons = {"市场总览": "🌍", "重要新闻": "📰", "新闻": "📰", "TOP": "📰",
                     "个股": "🔍", "情绪": "🎯", "展望": "🔮", "明日": "🔮"}
    html_parts = []
    for sec in sections:
        icon = "📊"
        for kw, ic in section_icons.items():
            if kw in sec["title"]:
                icon = ic
                break
        html_parts.append(f'<div class="report-section">')
        if sec["title"]:
            html_parts.append(f'<div class="report-section-title"><span class="section-icon">{icon}</span>{sec["title"]}</div>')
        for item in sec["content"]:
            if item[0] == "ol":
                num, text = item[1], item[2]
                num_int = int(num)
                badge_color = ["#e74c3c", "#e67e22", "#f39c12", "#3498db", "#9b59b6"][min(num_int - 1, 4)]
                html_parts.append(f'<div class="report-item"><span class="item-badge" style="background:{badge_color}">{num}</span><div class="item-text">{text}</div></div>')
            elif item[0] == "ul":
                html_parts.append(f'<div class="report-bullet"><span class="bullet-dot"></span><div class="bullet-text">{item[1]}</div></div>')
            else:
                html_parts.append(f'<p class="report-para">{item[1]}</p>')
        html_parts.append("</div>")

    return "\n".join(html_parts)


def generate_html_report(report, quotes, news_list):
    """生成精美的 HTML 详情页"""
    today = datetime.now().strftime("%Y-%m-%d")
    today_cn = datetime.now().strftime("%Y年%m月%d日")
    now_str = datetime.now().strftime("%H:%M")
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_names[datetime.now().weekday()]

    # 指数行情卡片
    quote_cards = ""
    for q in quotes:
        change_str = q["change"]
        is_up = change_str.startswith("+")
        is_down = change_str.startswith("-") and change_str != "--"
        bg = "linear-gradient(135deg, #fff5f5, #ffe8e8)" if is_up else ("linear-gradient(135deg, #f0fff4, #e6ffed)" if is_down else "linear-gradient(135deg, #f8f9fa, #f1f3f5)")
        color = "#e74c3c" if is_up else ("#16a34a" if is_down else "#868e96")
        border_color = "#fecaca" if is_up else ("#bbf7d0" if is_down else "#e9ecef")
        arrow = "▲" if is_up else ("▼" if is_down else "")
        quote_cards += f"""
        <div class="quote-card" style="background:{bg};border-color:{border_color}">
          <div class="quote-name">{q['name']}</div>
          <div class="quote-price" style="color:{color}">{q['price']}</div>
          <div class="quote-change" style="color:{color}">{arrow} {change_str}</div>
        </div>"""

    # 指数分时图
    chart_images = [
        ("上证指数", "https://image.sinajs.cn/newchart/min/n/sh000001.gif"),
        ("深证成指", "https://image.sinajs.cn/newchart/min/n/sz399001.gif"),
        ("恒生指数", "https://image.sinajs.cn/newchart/min/n/int_hangseng.gif"),
        ("纳斯达克", "https://image.sinajs.cn/newchart/min/n/int_nasdaq.gif"),
    ]
    chart_html = ""
    for name, img_url in chart_images:
        chart_html += f"""
        <div class="chart-item">
          <div class="chart-label">{name}</div>
          <img src="{img_url}" alt="{name}" onerror="this.parentElement.style.display='none'">
        </div>"""

    # 新闻来源统计
    valid_news = [n for n in news_list if "error" not in n]
    a_count = sum(1 for n in valid_news if n.get("market") == "A股")
    us_count = sum(1 for n in valid_news if n.get("market") == "美股")
    hk_count = sum(1 for n in valid_news if n.get("market") == "港股")
    total = len(valid_news)

    # Markdown → 结构化 HTML
    report_html = markdown_to_html(report)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日股市简报 - {today}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700;900&display=swap');

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Noto Sans SC', -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
  background: #0f0f1a; color: #333; line-height: 1.8; -webkit-font-smoothing: antialiased;
}}

/* ===== 封面头图 ===== */
.hero {{
  position: relative; overflow: hidden;
  background: linear-gradient(145deg, #0c1222 0%, #1a1040 40%, #2d1b69 70%, #1e3a5f 100%);
  padding: 50px 24px 40px; text-align: center; color: white;
}}
.hero::before {{
  content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
  background: radial-gradient(circle at 30% 50%, rgba(99,102,241,0.15) 0%, transparent 50%),
              radial-gradient(circle at 70% 30%, rgba(236,72,153,0.1) 0%, transparent 50%);
  animation: aurora 10s ease-in-out infinite alternate;
}}
@keyframes aurora {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(3deg); }} }}
.hero-content {{ position: relative; z-index: 1; }}
.hero-label {{
  display: inline-block; font-size: 11px; font-weight: 500; letter-spacing: 3px;
  text-transform: uppercase; color: rgba(255,255,255,0.6);
  border: 1px solid rgba(255,255,255,0.2); padding: 4px 16px; border-radius: 20px;
  margin-bottom: 20px;
}}
.hero h1 {{
  font-size: 36px; font-weight: 900; letter-spacing: 1px; margin-bottom: 8px;
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 50%, #f9a8d4 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.hero .date {{ font-size: 15px; color: rgba(255,255,255,0.6); font-weight: 300; }}
.hero-stats {{
  display: flex; justify-content: center; gap: 12px; margin-top: 24px; flex-wrap: wrap;
}}
.hero-stat {{
  background: rgba(255,255,255,0.08); backdrop-filter: blur(10px);
  border: 1px solid rgba(255,255,255,0.12); border-radius: 12px;
  padding: 8px 18px; font-size: 13px; color: rgba(255,255,255,0.85); font-weight: 500;
}}
.hero-stat em {{ font-style: normal; font-weight: 700; color: #c4b5fd; font-size: 16px; margin: 0 2px; }}

/* ===== 内容区 ===== */
.page-body {{ background: #f4f4f8; }}
.container {{ max-width: 680px; margin: 0 auto; padding: 0 16px 40px; }}

/* ===== 卡片 ===== */
.card {{
  background: white; border-radius: 16px; margin: 20px 0; padding: 28px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06);
  border: 1px solid rgba(0,0,0,0.04);
}}
.card-title {{
  font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px;
  color: #6366f1; margin-bottom: 20px;
  display: flex; align-items: center; gap: 8px;
}}
.card-title::after {{
  content: ''; flex: 1; height: 1px;
  background: linear-gradient(90deg, #e0e0e8, transparent);
}}

/* ===== 行情卡片 ===== */
.quotes-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px;
}}
.quote-card {{
  border-radius: 12px; padding: 14px 12px; text-align: center;
  border: 1px solid #eee; transition: transform 0.2s;
}}
.quote-card:hover {{ transform: translateY(-2px); }}
.quote-name {{ font-size: 11px; color: #888; font-weight: 500; letter-spacing: 1px; }}
.quote-price {{ font-size: 20px; font-weight: 800; margin: 4px 0 2px; font-variant-numeric: tabular-nums; }}
.quote-change {{ font-size: 12px; font-weight: 700; }}

/* ===== 走势图 ===== */
.charts-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }}
.chart-item {{
  background: #fafafe; border-radius: 10px; overflow: hidden;
  border: 1px solid #eee;
}}
.chart-label {{
  font-size: 12px; font-weight: 600; color: #555; text-align: center;
  padding: 10px 0 4px; letter-spacing: 1px;
}}
.chart-item img {{ width: 100%; display: block; }}

/* ===== 报告内容 ===== */
.report-section {{ margin-bottom: 24px; }}
.report-section:last-child {{ margin-bottom: 0; }}
.report-section-title {{
  font-size: 17px; font-weight: 700; color: #1e1e2e; margin-bottom: 14px;
  padding: 10px 16px; border-radius: 10px;
  background: linear-gradient(135deg, #f8f7ff, #f0f0ff);
  border-left: 4px solid #6366f1;
  display: flex; align-items: center; gap: 8px;
}}
.section-icon {{ font-size: 20px; }}

.report-item {{
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px 16px; margin: 8px 0; border-radius: 10px;
  background: #fafafe; border: 1px solid #f0f0f5;
  transition: background 0.2s;
}}
.report-item:hover {{ background: #f5f3ff; }}
.item-badge {{
  flex-shrink: 0; width: 26px; height: 26px; line-height: 26px; text-align: center;
  border-radius: 8px; color: white; font-size: 13px; font-weight: 800; margin-top: 2px;
}}
.item-text {{ font-size: 14.5px; line-height: 1.7; color: #2d2d3a; }}
.item-text strong {{ color: #6366f1; }}

.report-bullet {{
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 16px; margin: 4px 0;
}}
.bullet-dot {{
  flex-shrink: 0; width: 6px; height: 6px; border-radius: 50%;
  background: #6366f1; margin-top: 10px;
}}
.bullet-text {{ font-size: 14.5px; line-height: 1.7; color: #2d2d3a; }}
.bullet-text strong {{ color: #6366f1; }}

.report-para {{
  font-size: 14.5px; line-height: 1.9; color: #444; margin: 8px 0;
  padding: 0 4px;
}}
.report-para strong {{ color: #6366f1; }}

/* ===== 页脚 ===== */
.footer {{
  text-align: center; padding: 30px 20px 50px; color: #aaa; font-size: 11px;
  letter-spacing: 0.5px; line-height: 2;
}}
.footer-brand {{
  font-size: 13px; font-weight: 600; color: #888; margin-bottom: 4px;
}}
.footer-divider {{
  width: 40px; height: 2px; background: linear-gradient(90deg, #6366f1, #ec4899);
  margin: 12px auto; border-radius: 1px;
}}

/* ===== 响应式 ===== */
@media (max-width: 480px) {{
  .hero h1 {{ font-size: 28px; }}
  .card {{ padding: 20px 16px; margin: 12px 0; border-radius: 12px; }}
  .quotes-grid {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
  .charts-grid {{ grid-template-columns: 1fr; }}
  .hero-stats {{ gap: 8px; }}
  .hero-stat {{ padding: 6px 12px; font-size: 12px; }}
  .report-section-title {{ font-size: 15px; padding: 8px 12px; }}
  .report-item {{ padding: 10px 12px; }}
}}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-content">
    <div class="hero-label">Daily Market Brief</div>
    <h1>每日股市简报</h1>
    <div class="date">{today_cn} {weekday} {now_str} 更新</div>
    <div class="hero-stats">
      <div class="hero-stat">🇨🇳 A股 <em>{a_count}</em> 条</div>
      <div class="hero-stat">🇺🇸 美股 <em>{us_count}</em> 条</div>
      <div class="hero-stat">🇭🇰 港股 <em>{hk_count}</em> 条</div>
      <div class="hero-stat">共 <em>{total}</em> 条新闻</div>
    </div>
  </div>
</div>

<div class="page-body">
<div class="container">

  <div class="card">
    <div class="card-title">实时行情</div>
    <div class="quotes-grid">{quote_cards}</div>
  </div>

  <div class="card">
    <div class="card-title">大盘走势</div>
    <div class="charts-grid">{chart_html}</div>
  </div>

  <div class="card">
    <div class="card-title">AI 分析报告</div>
    {report_html}
  </div>

</div>
</div>

<div class="footer">
  <div class="footer-divider"></div>
  <div class="footer-brand">Stock Daily Report Agent</div>
  数据来源：财联社 / 东方财富 / 新浪财经<br>
  AI 分析由通义千问生成 · 仅供参考，不构成投资建议
</div>

</body>
</html>"""
    return html


# ============ GitHub Pages 部署 ============

def deploy_github_pages(html_content):
    """将 HTML 报告写入 docs/ 目录供 GitHub Pages 使用"""
    today = datetime.now().strftime("%Y%m%d")
    os.makedirs("docs", exist_ok=True)

    # 写入当天报告
    report_path = f"docs/report_{today}.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 写入 index.html（始终指向最新报告）
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    page_url = os.environ.get("GITHUB_PAGES_URL", "")
    if page_url:
        full_url = f"{page_url}/report_{today}.html"
    else:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo:
            owner = repo.split("/")[0].lower()
            repo_name = repo.split("/")[1]
            full_url = f"https://{owner}.github.io/{repo_name}/report_{today}.html"
        else:
            full_url = ""

    print(f"详情页已生成: {report_path}")
    if full_url:
        print(f"GitHub Pages URL: {full_url}")
    return full_url


# ============ Server酱微信推送（公众号风格）============

def send_wechat(report, quotes, page_url):
    """通过 Server酱 推送精美的微信消息"""
    send_key = os.environ.get("SERVERCHAN_KEY", "")
    if not send_key:
        print("未设置 SERVERCHAN_KEY，跳过微信推送")
        return

    today = datetime.now().strftime("%Y年%m月%d日")
    title = f"📈 每日股市简报 | {today}"

    # 构建公众号风格的 Markdown 内容
    lines = []

    # 行情概览表格
    lines.append("## 📊 今日行情一览\n")
    lines.append("| 指数 | 最新价 | 涨跌幅 |")
    lines.append("|:---:|:---:|:---:|")
    for q in quotes:
        change = q["change"]
        if change.startswith("+"):
            emoji = "🔴"
        elif change.startswith("-") and change != "--":
            emoji = "🟢"
        else:
            emoji = "⚪"
        lines.append(f"| {q['name']} | {q['price']} | {emoji} {change} |")
    lines.append("")

    # 大盘分时走势图
    lines.append("## 📈 大盘走势\n")
    lines.append("![上证指数](https://image.sinajs.cn/newchart/min/n/sh000001.gif)")
    lines.append("")
    lines.append("![恒生指数](https://image.sinajs.cn/newchart/min/n/int_hangseng.gif)")
    lines.append("")

    # 分隔线
    lines.append("---\n")

    # AI 分析报告
    lines.append("## 🤖 AI 分析报告\n")
    lines.append(report)
    lines.append("")

    # 详情链接
    lines.append("---\n")
    if page_url:
        lines.append(f"### 🔗 [点击查看完整图文报告]({page_url})\n")
    lines.append(f"> 📅 {today} · 数据来自财联社/东方财富/新浪财经 · AI分析仅供参考")

    desp = "\n".join(lines)

    url = f"https://sctapi.ftqq.com/{send_key}.send"
    payload = urllib.parse.urlencode({
        "title": title,
        "desp": desp,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if data.get("code") == 0:
            print("微信推送成功")
        else:
            print(f"微信推送失败: {data.get('message', '')}")
    except Exception as e:
        print(f"微信推送失败: {e}")


# ============ Webhook 推送 ============

def send_webhook(text):
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

    # 1. 抓取指数行情
    print("正在抓取指数行情...")
    quotes = fetch_index_quotes()
    for q in quotes:
        print(f"  {q['name']}: {q['price']} ({q['change']})")

    # 2. 抓取新闻
    print("正在抓取新闻...")
    news = fetch_all_news()
    valid = [n for n in news if "error" not in n]
    errors = [n for n in news if "error" in n]
    print(f"  抓取完成: {len(valid)} 条新闻, {len(errors)} 个错误")

    if not valid:
        print("没有抓取到任何新闻，退出")
        return

    # 3. 格式化 & 调用 LLM
    news_text = format_news(news)
    print("正在生成分析报告...")
    report = call_tongyi(news_text)

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)

    # 4. 生成 HTML 详情页
    print("\n正在生成详情页...")
    html = generate_html_report(report, quotes, news)
    page_url = deploy_github_pages(html)

    # 5. 保存 Markdown
    report_file = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# 每日股市简报 - {datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write(report)
    print(f"Markdown 报告: {report_file}")

    # 6. GitHub Actions 输出
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"report_file={report_file}\n")
            f.write(f"page_url={page_url}\n")

    # 7. 推送微信
    send_wechat(report, quotes, page_url)

    # 8. 推送 Webhook
    send_webhook(report)

    print(f"\n[{datetime.now()}] 完成")


if __name__ == "__main__":
    main()
