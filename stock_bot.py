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

# ===== 数据源 =====
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
    """获取盘前/盘后最新的一笔交易"""
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol.upper()}&apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        
        # 【关键修改】确保按时间倒序，取最新的一笔
        # 加上这个防止API偶尔返回旧数据在第一个
        data.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        
        latest = data[0]
        if "price" not in latest or latest["price"] in (None, 0):
            return None
            
        return latest
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
    change_amount = 0.0
    change_pct = 0.0
    
    # 1. 获取 Quote 数据 (作为基准)
    quote_data = fetch_fmp_stock_quote(symbol)
    
    base_close = None
    if quote_data:
        # 【关键修改】优先取 previousClose (昨日收盘)，它是固定的
        base_close = quote_data.get("previousClose") or quote_data.get("price")
    else:
        # 备用 Finnhub
        fh = fetch_finnhub_quote(symbol)
        if fh and fh.get("pc"):
            base_close = fh["pc"]

    # 2. 根据时段计算
    if status == "open":
        # 盘中：直接用 quote 里的实时数据
        if quote_data:
            current_price = quote_data.get("price")
            change_amount = quote_data.get("change", 0)
            change_pct = quote_data.get("changesPercentage", 0)
        elif base_close:
            # Finnhub 备用
            fh = fetch_finnhub_quote(symbol)
            if fh:
                current_price = fh.get("c")
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)

    elif status in ["pre_market", "aftermarket"]:
        # 盘前/盘后：用 Trade 数据减去 Quote 基准
        extended_data = fetch_fmp_extended_trade(symbol)
        
        if extended_data and extended_data.get("price"):
            current_price = extended_data["price"]
            
            if base_close:
                change_amount = current_price - base_close
                change_pct = (change_amount / base_close) * 100
        else:
            # 无盘前成交，显示收盘价
            current_price = base_close
            change_amount = 0
            change_pct = 0

    else:  # closed_night
        current_price = base_close
        if quote_data:
            change_amount = quote_data.get("change", 0)
            change_pct = quote_data.get("changesPercentage", 0)

    # 3. 发送结果
    if current_price is None or current_price == 0:
        await interaction.followup.send(f"未找到 **{symbol}** 的有效数据")
        return

    label_map = {
        "pre_market": "(盘前)",
        "open": "",
        "aftermarket": "(盘后)",
        "closed_night": "(收盘)"
    }
    display_label = label_map.get(status, "")
    
    # 修正无涨跌时的标签
    if status != "open" and abs(change_amount) < 0.0001:
        display_label = "(收盘)"

    title = f"**{symbol}** {display_label}"
    color = 0xFF0000 if change_amount >= 0 else 0x00FF00

    embed = discord.Embed(title=title, color=color)
    embed.add_field(
        name="",
        value=f"**当前价** `${current_price:.2f}`  **涨跌** `${change_amount:+.2f} ({change_pct:+.2f}%)`",
        inline=False
    )

    if status == "closed_night":
        embed.set_footer(text="💤 此时段显示收盘价")

    await interaction.followup.send(embed=embed)

# ===== /crypto 命令 (不变) =====
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
