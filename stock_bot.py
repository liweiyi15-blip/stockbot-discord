import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
from datetime import datetime, timedelta
import pytz

# ===== 环境变量 =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY")  # Massive.com API Key (免费申请)
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
def fetch_massive_quote(symbol: str):
    """
    使用 Massive Trades + Aggregates 获取实时报价（默认支持盘前/盘后）
    """
    try:
        # 1. 获取当前最新交易价 (默认含 extended hours)
        trade_url = f"https://api.polygon.io/v3/last/trade/{symbol}?apiKey={MASSIVE_API_KEY}"
        trade_resp = requests.get(trade_url, timeout=10)
        if trade_resp.status_code != 200:
            return None
        trade_data = trade_resp.json()
        if not trade_data or 'results' not in trade_data:
            return None
        current_price = trade_data['results']['price']

        # 2. 获取前收盘价 (昨日 aggregates)
        yesterday = (get_ny_time() - timedelta(days=1)).strftime('%Y-%m-%d')
        aggs_url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{yesterday}/{yesterday}?adjusted=true&sort=asc&limit=1&apiKey={MASSIVE_API_KEY}"
        aggs_resp = requests.get(aggs_url, timeout=10)
        if aggs_resp.status_code != 200:
            return None
        aggs_data = aggs_resp.json()
        if not aggs_data or 'results' not in aggs_data or not aggs_data['results']:
            return None
        prev_close = aggs_data['results'][0]['c']  # close

        # Extended 检查：如果盘前/盘后且 c ≈ pc，疑似无更新，fallback
        status = market_status()
        if status in ["pre_market", "aftermarket"] and abs(current_price - prev_close) < 0.01:
            print(f"Massive 疑似无 extended 更新 ({symbol})，fallback")
            return None

        # 返回类似 Finnhub 格式
        return {
            "c": current_price,
            "pc": prev_close,
            "t": trade_data['results'].get('sip_timestamp')  # 时间戳 (ms)
        }
    except Exception as e:
        print(f"Massive 查询失败: {e}")
        return None

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

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()

    price_to_show = change_amount = change_pct = None

    # 优先使用 Massive
    massive = fetch_massive_quote(symbol)
    if massive and massive["c"] is not None:
        price_to_show = massive["c"]
        prev_close = massive["pc"]
        change_amount = price_to_show - prev_close
        change_pct = (change_amount / prev_close) * 100 if prev_close != 0 else 0
        print(f"使用 Massive 数据: {symbol} - {price_to_show} (vs prev {prev_close})")
    else:
        # 回退到 Finnhub
        fh = fetch_finnhub_quote(symbol)
        if fh and fh["c"] != 0:
            price_to_show = fh["c"]
            prev_close = fh["pc"]
            change_amount = price_to_show - prev_close
            change_pct = (change_amount / prev_close) * 100 if prev_close != 0 else 0
            print(f"使用 Finnhub 数据: {symbol} - {price_to_show}")
        else:
            # 最终回退到 FMP
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

                if status in ["pre_market", "aftermarket"]:
                    after = fetch_fmp_aftermarket(symbol)
                    if after and after.get("bidPrice"):
                        price_to_show = after["bidPrice"]
                        change_amount = price_to_show - stock_price
                        change_pct = (change_amount / stock_price) * 100
                print(f"使用 FMP 数据: {symbol} - {price_to_show}")
            else:
                await interaction.followup.send("未找到该股票，或当前无实时数据")
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

    if status == "closed_night":
        msg += "\n💤 夜间收盘，无法获取实时股价。"

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
