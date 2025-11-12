import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
from datetime import datetime
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
    """返回当前纽约时间（美东时间）"""
    tz = pytz.timezone('America/New_York')
    return datetime.now(tz)

def market_status():
    """判断当前美股市场时段"""
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

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()

    status = market_status()

    fh = fetch_finnhub_quote(symbol)
    price_to_show = None
    change_amount = None
    change_pct = None

    if fh and fh["c"] != 0:
        price_to_show = fh["c"]
        prev_close = fh["pc"]
        change_amount = price_to_show - prev_close
        change_pct = (change_amount / prev_close) * 100 if prev_close != 0 else 0

    else:
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
        else:
            await interaction.followup.send("未找到该股票，或当前无实时数据")
            return

    emoji = "Up" if change_amount >= 0 else "Down"

    label_map = {
        "pre_market": "盘前",
        "open": "盘中",
        "aftermarket": "盘后",
        "closed_night": "收盘"
    }
    label = label_map.get(status, "未知")

    msg = f"{emoji} **{symbol}** ({label})\n"
    msg += f"当前价: `${price_to_show:.2f}`\n"
    msg += f"涨跌: `${change_amount:+.2f}` (`{change_pct:+.2f}`%)"

    if status == "closed_night":
        msg += "\nSleeping 夜间收盘，无法获取实时波动。"

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
