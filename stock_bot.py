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
        url = f"https://financialmodelingprep.com/stable/quote/{symbol}?apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or len(data) == 0:
            return None
        print(f"[DEBUG] FMP stock quote raw: {data[0]}")
        return data[0]
    except Exception as e:
        print(f"FMP stock 查询失败: {e}")
        return None

def fetch_fmp_aftermarket_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-quote?symbol={symbol}&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"[DEBUG] FMP aftermarket-quote API 失败: {response.status_code}")
            return None
        data = response.json()
        if not data or len(data) == 0:
            print(f"[DEBUG] FMP aftermarket-quote 无数据")
            return None
        item = data[0]
        print(f"[DEBUG] FMP aftermarket-quote raw: {item}")
        if 'bidPrice' in item and item['bidPrice'] is not None and item['bidPrice'] > 0:
            print(f"[DEBUG] FMP aftermarket-quote 使用 bidPrice: {item['bidPrice']}")
            return {"bidPrice": item['bidPrice']}
        print(f"[DEBUG] FMP aftermarket-quote 无有效 bidPrice")
        return None
    except Exception as e:
        print(f"FMP aftermarket-quote 查询失败: {e}")
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

    # FMP Stock Quote for regular_price
    fmp = fetch_fmp_stock(symbol)
    regular_price = None
    prev_close = None
    if fmp:
        regular_price = fmp.get("price") or fmp.get("lastPrice")
        prev_close = fmp.get("previousClose") or fmp.get("prevClose")
        if not regular_price or not prev_close:
            fmp = None

    # 兜底 regular_price: 如果 FMP 无，用 Finnhub c (latest close)
    if not regular_price:
        fh_temp = fetch_finnhub_quote(symbol)
        if fh_temp:
            regular_price = fh_temp.get("c")  # 用 c 作为 latest close
            print(f"[DEBUG] FMP 无 regular_price，用 Finnhub c: {regular_price}")

    if status == "open":
        # 开盘用 Stock Quote
        if fmp:
            price_to_show = regular_price
            change_amount = fmp.get("change") or (regular_price - prev_close)
            change_pct = fmp.get("changesPercentage") or ((change_amount / prev_close) * 100 if prev_close != 0 else 0)
            print(f"使用 FMP 开盘数据: {symbol} - {price_to_show} (change={change_amount:+.2f} ({change_pct:+.2f}%)")
        else:
            use_fallback = True
    else:
        # 其他时段用 Aftermarket Quote (包括 pre_market)
        extended = fetch_fmp_aftermarket_quote(symbol)
        extended_price = None
        if extended and extended.get("bidPrice"):
            extended_price = extended["bidPrice"]

        if extended_price:
            price_to_show = extended_price
            # 涨跌相对 regular_price (Stock Quote price 或 Finnhub c 兜底)
            if regular_price:
                change_amount = extended_price - regular_price
                change_pct = (change_amount / regular_price) * 100
            else:
                change_amount = 0
                change_pct = 0
            print(f"使用 FMP {status} aftermarket-quote 数据: {symbol} - {price_to_show} (vs Stock Quote price {regular_price}, change={change_amount:+.2f} ({change_pct:+.2f}%)")
            use_fallback = False
        elif fmp and regular_price:
            # 无 extended，用 regular (e.g., closed_night)
            price_to_show = regular_price
            change_amount = regular_price - prev_close
            change_pct = (change_amount / prev_close) * 100 if prev_close != 0 else 0
            print(f"使用 FMP {status} regular 数据: {symbol} - {price_to_show} (vs prev {prev_close}, change={change_amount:+.2f} ({change_pct:+.2f}%)")
            use_fallback = True  # 加备注，因为非 extended
        else:
            use_fallback = True

    # Fallback to Finnhub
    if use_fallback and not price_to_show:
        print(f"[DEBUG] FMP 失败，回退 Finnhub")
        fh = fetch_finnhub_quote(symbol)
        if fh and fh["c"] != 0:
            price_to_show = fh["c"]
            change_amount = fh.get("d", 0)
            change_pct = fh.get("dp", 0)
            print(f"使用 Finnhub fallback: {symbol} - {price_to_show} (d={change_amount}, dp={change_pct}%)")
        else:
            await interaction.followup.send("未找到该股票，或当前无数据")
            return

    # 表情
    emoji = "📈" if change_amount >= 0 else "📉"

    # 标签
    label_map = {
        "pre_market": "盘前",
        "open": "盘中",
        "aftermarket": "盘后",
        "closed_night": "收盘"
    }
    label = label_map.get(status, "未知")

    # 消息
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
