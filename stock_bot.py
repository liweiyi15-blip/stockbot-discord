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

# ===== 全局请求头（关键！解决 FMP 裸请求返回空的问题）=====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

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

# ===== 数据源函数（全部加上 headers）=====
def fetch_fmp_stock_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol.upper()}?apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10, headers=HEADERS)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or len(data) == 0:
            return None
        return data[0]
    except Exception as e:
        print(f"FMP stock quote 查询失败: {e}")
        return None

def fetch_fmp_crypto_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/quote?symbol={symbol}&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10, headers=HEADERS)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or len(data) == 0:
            return None
        return data[0]
    except Exception as e:
        print(f"FMP crypto quote 查询失败: {e}")
        return None

def fetch_finnhub_quote(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10, headers=HEADERS)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or data.get("c") in (0, None):
            return None
        return data
    except Exception as e:
        print(f"Finnhub 查询失败: {e}")
        return None

def fetch_fmp_extended_trade(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol.upper()}&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10, headers=HEADERS)
        print(f"[DEBUG] FMP extended-trade URL: {url}")
        print(f"[DEBUG] 状态码: {response.status_code}")
        if response.status_code != 200:
            print(f"[DEBUG] 响应内容: {response.text[:200]}")
            return None
        data = response.json()
        print(f"[DEBUG] raw data: {data}")
        if not data or len(data) == 0 or "price" not in data[0] or data[0]["price"] in (None, 0):
            return None
        return data[0]
    except Exception as e:
        print(f"FMP extended-trade 查询失败: {e}")
        return None

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    print(f"[DEBUG] 查询股票 {symbol}，市场状态: {status}")

    current_price = None
    change_amount = 0.0
    change_pct = 0.0
    base_close = None
    source_note = ""

    # 1. 先拿基准价（昨收或今日收盘参考价）
    fmp_data = fetch_fmp_stock_quote(symbol)
    if fmp_data and fmp_data.get("price"):
        base_close = fmp_data["price"]
        print(f"[基准价] 使用 FMP quote.price: {base_close}")
    else:
        # 回退 Finnhub 拿昨收
        fh = fetch_finnhub_quote(symbol)
        if fh and fh.get("pc"):  # pc = previous close
            base_close = fh["pc"]
            source_note = "（基准价来自 Finnhub）"
            print(f"[基准价] 回退 Finnhub previousClose: {base_close}")
        else:
            print(f"[警告] 完全无法获取 {symbol} 的基准价")

    # 2. 根据市场状态拿实时价
    if status == "open":
        # 开盘：优先 FMP
        if fmp_data and fmp_data.get("price"):
            current_price = fmp_data["price"]
            change_amount = fmp_data.get("change", 0) or fmp_data.get("changes", 0)
            change_pct = fmp_data.get("changesPercentage", 0) or fmp_data.get("changeP", 0)
            print(f"[开盘] 使用 FMP 实时价: {current_price}")
        else:
            fh = fetch_finnhub_quote(symbol)
            if fh and fh.get("c"):
                current_price = fh["c"]
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)
                source_note = "（开盘价来自 Finnhub）"
                print(f"[开盘] 回退 Finnhub: {current_price}")

    elif status in ["pre_market", "aftermarket"]:
        # 盘前盘后：优先 FMP extended
        extended = fetch_fmp_extended_trade(symbol)
        if extended and extended.get("price"):
            current_price = extended["price"]
            if base_close:
                change_amount = current_price - base_close
                change_pct = (change_amount / base_close) * 100
            print(f"[{status}] 使用 FMP extended-trade 价: {current_price}")
        else:
            # 没盘前盘后成交 → 显示昨收
            if fmp_data and fmp_data.get("price"):
                current_price = fmp_data["price"]
                change_amount = fmp_data.get("change", 0) or 0
                change_pct = fmp_data.get("changesPercentage", 0) or 0
                print(f"[{status}] 无成交，回退 FMP 昨收: {current_price}")
            else:
                fh = fetch_finnhub_quote(symbol)
                if fh and fh.get("c"):
                    current_price = fh["c"]
                    change_amount = fh.get("d", 0)
                    change_pct = fh.get("dp", 0)
                    source_note = "（来自 Finnhub）"

    else:  # closed_night
        if fmp_data and fmp_data.get("price"):
            current_price = fmp_data["price"]
            change_amount = fmp_data.get("change", 0) or 0
            change_pct = fmp_data.get("changesPercentage", 0) or 0
        else:
            fh = fetch_finnhub_quote(symbol)
            if fh and fh.get("c"):
                current_price = fh["c"]
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)
                source_note = "（来自 Finnhub）"

    if current_price is None:
        await interaction.followup.send("未找到该股票，或当前所有数据源均无数据")
        return

    # 标签
    label_map = {"pre_market": "(盘前)", "open": "", "aftermarket": "(盘后)", "closed_night": "(收盘)"}
    display_label = label_map[status]
    if status != "open" and current_price == base_close:
        display_label = "(收盘)"

    title = f"**{symbol}** {display_label}" if display_label else f"**{symbol}**"
    color = 0xFF0000 if change_amount >= 0 else 0x00FF00

    embed = discord.Embed(title=title, color=color)
    embed.add_field(
        name="",
        value=f"**当前价** `${current_price:.2f}`  **涨跌** `${change_amount:+.2f} ({change_pct:+.2f}%)`",
        inline=False
    )
    footer = f"纽约时间 {get_ny_time().strftime('%H:%M')}"
    if source_note:
        footer += " " + source_note
    embed.set_footer(text=footer)

    await interaction.followup.send(embed=embed)

# ===== /crypto 命令（保持原样，只加 headers）=====
@bot.tree.command(name="crypto", description="查询数字货币实时价格")
@app_commands.describe(symbol="数字货币代码，例如 btc 或 doge")
async def crypto(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    original_symbol = symbol.strip().upper()
    symbol = original_symbol + "USD" if not original_symbol.endswith('USD') else original_symbol

    data = fetch_fmp_crypto_quote(symbol)
    if not data or not data.get("price"):
        await interaction.followup.send("未找到该数字货币，或当前无数据")
        return

    price = data["price"]
    change = data.get("change", 0)
    pct = data.get("changePercentage", 0)

    embed = discord.Embed(title=f"**{original_symbol}**", color=0xFF0000 if change >= 0 else 0x00FF00)
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
    ny_time = get_ny_time().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"Bot 已上线: {bot.user}")
    print(f"纽约时间: {ny_time}")
    print(f"Slash 命令已同步（加上 User-Agent 后 FMP 已恢复正常）")

bot.run(DISCORD_TOKEN)
