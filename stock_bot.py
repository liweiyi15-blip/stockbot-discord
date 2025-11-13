import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
from datetime import datetime, timedelta
import pytz

# ===== 环境变量 =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# ===== Bot 对象定义 =====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="$", intents=intents)

# ===== 工具函数 =====
def get_ny_time():
    tz = pytz.timezone('America/New_York')
    return datetime.now(tz)

def market_status():
    now = get_ny_time()
    weekday = now.weekday()
    if weekday >= 5:
        return "closed_night"
    
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    aftermarket_end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    premarket_start = now.replace(hour=4, minute=0, second=0, microsecond=0)

    if premarket_start <= now < open_time:
        return "pre_market"
    elif open_time <= now <= close_time:
        return "open"
    elif close_time < now <= aftermarket_end:
        return "aftermarket"
    else:
        return "closed_night"

# ===== 数据源函数 =====
def fetch_finnhub_quote(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or data.get("c") == 0:
            return None
        return data
    except Exception as e:
        print(f"Finnhub 查询失败: {e}")
        return None

def fetch_fmp_stock(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v5/quote/{symbol}?apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or len(data) == 0:
            return None
        return data[0]
    except Exception as e:
        print(f"FMP 查询失败: {e}")
        return None

def fetch_fmp_aftermarket(symbol: str):
    try:
        data = fetch_fmp_stock(symbol)
        if not data:
            return None
        if "priceAfterHours" in data and data["priceAfterHours"] is not None:
            return {"bidPrice": data["priceAfterHours"]}
        if "afterHours" in data and data["afterHours"] is not None:
            return {"bidPrice": data["afterHours"]}
        return None
    except:
        return None

def fetch_fmp_premarket(symbol: str):
    try:
        data = fetch_fmp_stock(symbol)
        if not data:
            return None
        if "pricePreMarket" in data and data["pricePreMarket"] is not None:
            return {"bidPrice": data["pricePreMarket"]}
        if "preMarket" in data and data["preMarket"] is not None:
            return {"bidPrice": data["preMarket"]}
        return None
    except:
        return None

def fetch_finnhub_daily_close(symbol: str):
    """
    用 Finnhub daily candle 获取最新交易日 close + 前一交易日 close（适用于夜盘，计算涨跌）
    """
    try:
        from_time = int((get_ny_time() - timedelta(days=14)).timestamp())  # 最近14天，确保至少2个bar
        to_time = int(get_ny_time().timestamp())
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={symbol}&resolution=D&from={from_time}&to={to_time}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or data.get("c") is None or len(data["c"]) < 2:  # 至少2个bar计算涨跌
            return None
        latest_close = data["c"][-1]  # 最新交易日 close
        prev_close = data["c"][-2]    # 前一交易日 close
        print(f"[DEBUG] Finnhub daily closes: latest={latest_close}, prev={prev_close}")
        return {"latest": latest_close, "prev": prev_close}
    except Exception as e:
        print(f"Finnhub daily 查询失败: {e}")
        return None

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    print(f"[DEBUG] 查询 {symbol}，状态: {status}")

    price_to_show = change_amount = change_pct = None
    use_fallback = False
    fallback_note = "🚫 该时段不支持实时查询，使用前收盘价。"

    # 开盘优先 Finnhub
    if status == "open":
        fh = fetch_finnhub_quote(symbol)
        if fh and fh["c"] != 0:
            price_to_show = fh["c"]
            prev_close = fh["pc"]
            change_amount = price_to_show - prev_close
            change_pct = (change_amount / prev_close) * 100 if prev_close != 0 else 0
            print(f"使用 Finnhub 开盘数据: {symbol} - {price_to_show}")
        else:
            print(f"[DEBUG] Finnhub 开盘失败，回退 FMP")
            # 回退到 FMP
            fmp = fetch_fmp_stock(symbol)
            if fmp:
                stock_price = fmp.get("price") or fmp.get("lastPrice")
                prev_close = fmp.get("previousClose") or fmp.get("prevClose")
                if not stock_price or not prev_close:
                    await interaction.followup.send("未找到该股票数据")
                    return
                price_to_show = stock_price
                change_amount = fmp.get("change") or (stock_price - prev_close)
                change_pct = fmp.get("changesPercentage") or ((change_amount / prev_close) * 100)
                print(f"使用 FMP 开盘数据: {symbol} - {price_to_show}")
            else:
                await interaction.followup.send("未找到该股票，或当前无实时数据")
                return
    else:
        # 其余时段优先 FMP
        fmp = fetch_fmp_stock(symbol)
        if fmp:
            stock_price = fmp.get("price") or fmp.get("lastPrice")
            prev_close = fmp.get("previousClose") or fmp.get("prevClose")
            if not stock_price or not prev_close:
                fmp = None  # 标记失败

        extended_price = None
        if status == "pre_market":
            extended = fetch_fmp_premarket(symbol)
            if extended and extended.get("bidPrice"):
                extended_price = extended["bidPrice"]
        elif status == "aftermarket":
            extended = fetch_fmp_aftermarket(symbol)
            if extended and extended.get("bidPrice"):
                extended_price = extended["bidPrice"]

        if extended_price:
            price_to_show = extended_price
            # 对于 extended，change 相对于 regular close
            change_amount = fmp.get("change") or (extended_price - stock_price) if stock_price else 0
            change_pct = fmp.get("changesPercentage") or ((change_amount / stock_price) * 100) if stock_price else 0
            print(f"使用 FMP 扩展时段数据: {symbol} - {price_to_show}")
        elif fmp and stock_price:  # FMP 有 regular 数据，但非 extended 时段用 regular? 按要求，如果无 extended 则 fallback
            # 但按要求，其余时段优先 FMP，但如果无 extended 则 fallback
            # 假设如果 status 非 open 且无 extended，则 fallback
            use_fallback = True
        else:
            use_fallback = True

        if use_fallback:
            print(f"[DEBUG] FMP 其余时段失败，回退 Finnhub")
            if status == "closed_night":
                # 夜盘用 daily closes 计算涨跌
                daily_data = fetch_finnhub_daily_close(symbol)
                if daily_data is not None:
                    price_to_show = daily_data["latest"]
                    prev_close = daily_data["prev"]
                    change_amount = price_to_show - prev_close
                    change_pct = (change_amount / prev_close) * 100 if prev_close != 0 else 0
                    print(f"使用 Finnhub daily close (with change): {symbol} - {price_to_show} (vs {prev_close})")
                else:
                    # 最终fallback pc（无涨跌）
                    fh = fetch_finnhub_quote(symbol)
                    if fh and fh["pc"] != 0:
                        price_to_show = fh["pc"]
                        change_amount = 0
                        change_pct = 0
                        print(f"使用 Finnhub pc fallback: {symbol} - {price_to_show}")
                    else:
                        await interaction.followup.send("未找到该股票，或当前无数据")
                        return
            else:
                # 非夜盘 fallback 原逻辑（用 pc，change=0）
                fh = fetch_finnhub_quote(symbol)
                if fh and fh["pc"] != 0:
                    price_to_show = fh["pc"]
                    change_amount = 0
                    change_pct = 0
                    print(f"使用 Finnhub pc 数据: {symbol} - {price_to_show}")
                else:
                    await interaction.followup.send("未找到该股票，或当前无数据")
                    return

    # 根据涨跌选择表情
    emoji = "📈" if change_amount >= 0 else "📉"

    # 定义市场时段标签
    label_map = {
        "pre_market": "盘前",
        "open": "盘中",
        "aftermarket": "盘后",
        "closed_night": "收盘"
    }
    label = label_map.get(status, "未知")

    # 构建消息
    msg = f"{emoji} **{symbol}** ({label})\n"
    msg += f"当前价: `${price_to_show:.2f}`\n"
    msg += f"涨跌: `${change_amount:+.2f}` (`{change_pct:+.2f}`%)"

    if use_fallback:
        msg += f"\n{fallback_note}"

    await interaction.followup.send(msg)

# ===== 启动事件 =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    ny_time = get_ny_time().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"Bot 已上线: {bot.user}")
    print(f"纽约时间: {ny_time}")
    print(f"Slash 命令已同步")

# ===== 启动 Bot =====
bot.run(DISCORD_TOKEN)
