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
def fetch_fmp_stock_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
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
        response = requests.get(url, timeout=10)
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
        response = requests.get(url, timeout=10)
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
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol}&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        print(f"[DEBUG] FMP extended-trade URL: {url}")
        print(f"[DEBUG] FMP extended-trade 状态码: {response.status_code}")
        if response.status_code != 200:
            print(f"[DEBUG] FMP extended-trade 响应: {response.text[:200]}...")
            return None
        data = response.json()
        print(f"[DEBUG] FMP extended-trade raw data: {data}")
        if not data or len(data) == 0 or "price" not in data[0] or data[0]["price"] in (None, 0):
            print(f"[DEBUG] FMP extended-trade 无有效 price")
            return None
        return data[0]
    except Exception as e:
        print(f"FMP extended-trade 查询失败: {e}")
        return None

# ===== /stock 命令（仅美股）=====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    print(f"[DEBUG] 查询股票 {symbol}，市场状态: {status}")

    # 初始化
    current_price = None
    change_amount = 0
    change_pct = 0
    base_close = None
    use_fallback = False
    fallback_note = "该时段不支持实时查询，显示收盘价。"

    # === 1. 获取涨跌基准价：优先 FMP stock quote.price ===
    fmp_data = fetch_fmp_stock_quote(symbol)
    if fmp_data and fmp_data.get("price"):
        base_close = fmp_data["price"]
        print(f"[基准价] 使用 FMP stock quote.price: {base_close}")
    else:
        fh = fetch_finnhub_quote(symbol)
        if fh and fh.get("c"):
            base_close = fh["c"]
            print(f"[基准价] 回退 Finnhub.c: {base_close}")
        else:
            print(f"[警告] 无法获取 {symbol} 的基准价")

    # === 2. 获取当前价 ===
    if status == "open":
        # 开盘：优先 FMP stock quote
        if fmp_data and fmp_data.get("price"):
            current_price = fmp_data["price"]
            change_amount = fmp_data.get("changes", 0)
            change_pct = fmp_data.get("changesPercentage", 0)
            print(f"[开盘] 使用 FMP stock quote.price: {current_price}")
        else:
            # 回退 Finnhub
            fh = fetch_finnhub_quote(symbol)
            if fh and fh.get("c"):
                current_price = fh["c"]
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)
                print(f"[开盘] 回退 Finnhub.c: {current_price}")
            else:
                await interaction.followup.send("未找到该股票，或当前无数据")
                return

    else:
        # 非开盘时段
        if status == "closed_night":
            # 夜盘/收盘：强制回退到收盘价，不查询 extended-trade
            use_fallback = True
            if fmp_data and fmp_data.get("price"):
                current_price = fmp_data["price"]
                change_amount = fmp_data.get("changes", 0)
                change_pct = fmp_data.get("changesPercentage", 0)
                print(f"[closed_night] 强制回退 FMP stock quote.price: {current_price}")
            else:
                fh = fetch_finnhub_quote(symbol)
                if fh and fh.get("c"):
                    current_price = fh["c"]
                    change_amount = fh.get("d", 0)
                    change_pct = fh.get("dp", 0)
                    print(f"[closed_night] 强制回退 Finnhub.c: {current_price}")
                else:
                    await interaction.followup.send("未找到该股票，或当前无数据")
                    return
        else:
            # 盘前/盘后：优先 FMP extended-trade
            extended_data = fetch_fmp_extended_trade(symbol)
            if extended_data and extended_data.get("price"):
                current_price = extended_data["price"]
                if base_close:
                    change_amount = current_price - base_close
                    change_pct = (change_amount / base_close) * 100
                print(f"[{status}] 使用 FMP extended-trade.price: {current_price}")
            else:
                # 无实时价 → 回退到收盘价
                use_fallback = True
                if fmp_data and fmp_data.get("price"):
                    current_price = fmp_data["price"]
                    change_amount = fmp_data.get("changes", 0)
                    change_pct = fmp_data.get("changesPercentage", 0)
                    print(f"[{status}] 无实时价，回退 FMP stock quote.price: {current_price}")
                else:
                    fh = fetch_finnhub_quote(symbol)
                    if fh and fh.get("c"):
                        current_price = fh["c"]
                        change_amount = fh.get("d", 0)
                        change_pct = fh.get("dp", 0)
                        print(f"[{status}] 无实时价，回退 Finnhub.c: {current_price}")
                    else:
                        await interaction.followup.send("未找到该股票，或当前无数据")
                        return

    # === 3. 构建 Embed ===
    label_map = {
        "pre_market": "(盘前)",
        "open": "",
        "aftermarket": "(盘后)",
        "closed_night": "(收盘)"
    }

    display_label = label_map.get(status, "(收盘)")
    if use_fallback and status != "open":
        display_label = "(收盘)"

    title = f"**{symbol}** {display_label}" if display_label else f"**{symbol}**"
    color = 0xFF0000 if change_amount >= 0 else 0x00FF00  # 统一正红负绿

    embed = discord.Embed(title=title, color=color)

    # 最终稳定版：简洁、横向、无标签、无放大
    embed.add_field(
        name="",
        value=f"**当前价** `${current_price:.2f}`  **涨跌** `${change_amount:+.2f} ({change_pct:+.2f}%)`",
        inline=True
    )

    if use_fallback and status != "open":
        embed.set_footer(text="该时段不支持实时查询，显示收盘价。")

    await interaction.followup.send(embed=embed)

# ===== /crypto 命令（仅数字货币）=====
@bot.tree.command(name="crypto", description="查询数字货币实时价格")
@app_commands.describe(symbol="数字货币代码，例如 btc 或 doge")
async def crypto(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    original_symbol = symbol.strip().upper()
    # 无论长度多少，都补齐 USD（如果已以 USD 结尾则不重复添加）
    if not original_symbol.endswith('USD'):
        symbol = original_symbol + "USD"
    else:
        symbol = original_symbol
    print(f"[DEBUG] 查询数字货币 {original_symbol} -> {symbol}")

    # === 获取数据 ===
    fmp_data = fetch_fmp_crypto_quote(symbol)
    if not fmp_data or not fmp_data.get("price"):
        await interaction.followup.send("未找到该数字货币，或当前无数据")
        return

    current_price = fmp_data["price"]
    change_amount = fmp_data.get("changes", 0)
    change_pct = fmp_data.get("changes_percentage", 0)
    print(f"[Crypto] 使用 FMP crypto quote.price: {current_price}, changes: {change_amount}, changes_percentage: {change_pct}")

    # === 构建 Embed ===
    title = f"**{original_symbol}**"
    color = 0xFF0000 if change_amount >= 0 else 0x00FF00  # 统一正红负绿

    embed = discord.Embed(title=title, color=color)

    # 最终稳定版：简洁、横向、无标签、无放大
    embed.add_field(
        name="",
        value=f"**当前价** `${current_price:.2f}`  **涨跌** `${change_amount:+.2f} ({change_pct:+.2f}%)`",
        inline=True
    )

    await interaction.followup.send(embed=embed)

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
