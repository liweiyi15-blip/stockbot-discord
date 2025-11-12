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

# ===== 其他函数: get_ny_time, market_status, fetch_fmp_stock, fetch_fmp_aftermarket, fetch_finnhub_quote =====

# FMP 查询函数
def fetch_fmp_stock(symbol):
    try:
        url = f"https://financialmodelingprep.com/stable/quote?symbol={symbol}&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"FMP 请求失败，状态码: {response.status_code}")
            return None
        data = response.json()
        if not data:
            return None
        return data[0]
    except Exception as e:
        print(f"FMP 查询失败: {e}")
        return None

# Finnhub 查询函数
def fetch_finnhub_quote(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Finnhub 请求失败，状态码: {response.status_code}")
            return None
        data = response.json()
        if not data:
            return None
        return data
    except Exception as e:
        print(f"Finnhub 查询失败: {e}")
        return None

# ===== 市场时段判断 =====
def market_status():
    now = get_ny_time()
    weekday = now.weekday()
    if weekday >= 5:
        return "closed_night"
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    aftermarket_end = now.replace(hour=20, minute=0, second=0, microsecond=0)

    if now < open_time:
        return "pre_market"
    elif open_time <= now <= close_time:
        return "open"
    elif close_time < now <= aftermarket_end:
        return "aftermarket"
    else:
        return "closed_night"

# ===== stock 命令 =====
@bot.tree.command(name="stock", description="查询美股价格")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    # 处理大写字母
    symbol = symbol.upper()

    # 初始状态
    price_to_show = None
    change_amount = None
    change_pct = None
    emoji = "📈"
    label = ""

    # 查询市场时段
    status = market_status()

    # 首先尝试用 FMP 查询
    stock = fetch_fmp_stock(symbol)
    
    if stock:
        stock_price = stock["price"]
        prev_close = stock["previousClose"]
        price_to_show = stock_price
        change_amount = stock["change"]
        change_pct = stock["changePercentage"]

        # 盘前/盘后使用 aftermarket
        if status in ["pre_market", "aftermarket"]:
            after = fetch_fmp_aftermarket(symbol)
            if after and after.get("bidPrice"):
                bid_price = after["bidPrice"]
                price_to_show = bid_price
                change_amount = bid_price - stock_price
                change_pct = (change_amount / stock_price) * 100
    else:
        # FMP 查询不到数据，尝试用 Finnhub 查询
        fh = fetch_finnhub_quote(symbol)
        if fh:
            stock_price = fh["c"]
            prev_close = fh["pc"]
            price_to_show = stock_price
            change_amount = stock_price - prev_close
            change_pct = (change_amount / prev_close) * 100
        else:
            # 如果 FMP 和 Finnhub 都查不到
            await interaction.followup.send("😭 此代码不支持该时段查询")
            return

    # 判断涨跌 emoji
    emoji = "📈" if change_amount >= 0 else "📉"

    # 时段标签
    if status == "pre_market":
        label = "盘前"
    elif status == "open":
        label = "盘中"
    elif status == "aftermarket":
        label = "盘后"
    else:
        label = "收盘"

    # 构建消息
    msg = f"{emoji} {symbol} ({label})\n当前价: ${price_to_show:.2f}\n涨跌: ${change_amount:+.2f} ({change_pct:+.2f}%)"
    if status == "closed_night":
        msg += "\n💤 收盘阶段，无法查询实时数据。"

    # 发送消息
    await interaction.followup.send(msg)

# ===== 启动事件 =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 已登录为 {bot.user}，Slash Command 已同步到 Discord")

# ===== 启动 Bot =====
bot.run(DISCORD_TOKEN)
