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

# ===== 关键：解决 FMP 裸请求返回空的问题 =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# ===== Bot 定义 =====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="$", intents=intents)

# ===== 时间工具 =====
def get_ny_time():
    tz = pytz.timezone('America/New_York')
    return datetime.now(tz)

def market_status():
    now = get_ny_time()
    weekday = now.weekday()
    if weekday >= 5:  # 周六周日
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

# ===== 数据源（全部加 headers）=====
def fetch_fmp_stock_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol.upper()}?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10, headers=HEADERS)
        if r.status_code != 200 or not r.json():
            return None
        return r.json()[0]
    except:
        return None

def fetch_fmp_crypto_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/quote?symbol={symbol}&apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10, headers=HEADERS)
        if r.status_code != 200 or not r.json():
            return None
        return r.json()[0]
    except:
        return None

def fetch_finnhub_quote(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()
        if not data or data.get("c") in (0, None):
            return None
        return data
    except:
        return None

def fetch_fmp_extended_trade(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol.upper()}&apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()
        if not data or "price" not in data[0] or data[0]["price"] in (None, 0):
            return None
        return data[0]
    except:
        return None

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()

    current_price = None
    change_amount = change_pct = 0.0
    base_close = None

    # 1. 获取基准昨收（优先 FMP）
    fmp_data = fetch_fmp_stock_quote(symbol)
    if fmp_data and fmp_data.get("price"):
        base_close = fmp_data["price"]
    else:
        fh = fetch_finnhub_quote(symbol)
        if fh and fh.get("pc"):
            base_close = fh["pc"]

    # 2. 根据时段取实时价
    if status == "open":
        if fmp_data and fmp_data.get("price"):
            current_price = fmp_data["price"]
            change_amount = fmp_data.get("change") or fmp_data.get("changes") or 0
            change_pct = fmp_data.get("changesPercentage") or fmp_data.get("changeP") or 0
        else:
            fh = fetch_finnhub_quote(symbol)
            if fh and fh.get("c"):
                current_price = fh["c"]
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)

    elif status in ["pre_market", "aftermarket"]:
        extended = fetch_fmp_extended_trade(symbol)
        if extended and extended.get("price"):
            current_price = extended["price"]
            if base_close:
                change_amount = current_price - base_close
                change_pct = (change_amount / base_close) * 100
        else:
            # 无成交 → 显示昨收或今日收盘
            current_price = base_close or 0
            change_amount = change_pct = 0

    else:  # closed_night
        current_price = base_close or 0
        if fmp_data:
            change_amount = fmp_data.get("change") or fmp_data.get("changes") or 0
            change_pct = fmp_data.get("changesPercentage") or 0
        else:
            fh = fetch_finnhub_quote(symbol)
            if fh:
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)

    if current_price is None or current_price == 0:
        await interaction.followup.send("未找到该股票，或当前所有数据源均无数据")
        return

    # 标签
    label_map = {
        "pre_market": "(盘前)",
        "open": "",
        "aftermarket": "(盘后)",
        "closed_night": "(收盘)"
    }
    display_label = label_map[status]
    if status != "open" and change_amount == 0 and change_pct == 0:
        display_label = "(收盘)"

    title = f"**{symbol}** {display_label}" if display_label else f"**{symbol}**"
    color = 0xFF0000 if change_amount >= 0 else 0x00FF00

    embed = discord.Embed(title=title, color=color)
    embed.add_field(
        name="",
        value=f"**当前价** `${current_price:.2f}`  **涨跌** `${change_amount:+.2f} ({change_pct:+.2f}%)`",
        inline=False
    )

    # 唯一脚注：只有夜盘/周末/节假日显示
    if status == "closed_night":
        embed.set_footer(text="💤 此时段不支持查询，显示收盘价")

    await interaction.followup.send(embed=embed)

# ===== /crypto 命令（保持干净）=====
@bot.tree.command(name="crypto", description="查询数字货币实时价格")
@app_commands.describe(symbol="数字货币代码，例如 btc 或 doge")
async def crypto(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    original = symbol.strip().upper()
    symbol = original + "USD" if not original.endswith("USD") else original

    data = fetch_fmp_crypto_quote(symbol)
    if not data or not data.get("price"):
        await interaction.followup.send("未找到该数字货币，或当前无数据")
        return

    price = data["price"]
    change = data.get("change", 0)
    pct = data.get("changePercentage", 0)

    embed = discord.Embed(title=f"**{original}**", color=0xFF0000 if change >= 0 else 0x00FF00)
    embed.add_field(
        name="",
        value=f"**当前价** `${price:.2f}`  **涨跌** `${change:+.2f} ({pct:+.2f}%)`",
        inline=False
    )
    await interaction.followup.send(embed=embed)

# ===== 启动 =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot 已上线: {bot.user} | 纽约时间: {get_ny_time().strftime('%Y-%m-%d %H:%M')}")

bot.run(DISCORD_TOKEN)
