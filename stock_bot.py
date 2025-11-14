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

def fetch_fmp_stable_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v3/stable/quote/{symbol}?apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or len(data) == 0:
            return None
        return data[0]
    except Exception as e:
        print(f"FMP stable/quote 查询失败: {e}")
        return None

def fetch_fmp_aftermarket_trade(symbol: str):
    try:
        # 修复：使用无版本前缀路径，匹配你的测试 URL
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol}&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        print(f"[DEBUG] FMP aftermarket-trade URL: {url}")  # 新增：打印完整 URL
        print(f"[DEBUG] FMP aftermarket-trade 状态码: {response.status_code}")  # 保留
        if response.status_code != 200:
            print(f"[DEBUG] FMP aftermarket-trade 响应文本: {response.text[:200]}...")  # 新增：打印 raw 响应（截断）
            return None
        data = response.json()
        print(f"[DEBUG] FMP aftermarket-trade raw data: {data}")  # 新增：打印完整 data
        if not data or len(data) == 0 or "price" not in data[0] or data[0]["price"] in (None, 0):
            print(f"[DEBUG] FMP aftermarket-trade 无有效 price: {data}")
            return None
        return data[0]
    except Exception as e:
        print(f"FMP aftermarket-trade 查询失败: {e}")
        return None

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    print(f"[DEBUG] 查询 {symbol}，市场状态: {status}")

    # 初始化
    current_price = None
    change_amount = 0
    change_pct = 0
    base_close = None
    use_fallback = False
    fallback_note = "该时段不支持实时查询，显示收盘价。"

    # === 1. 获取涨跌基准价：优先 Finnhub.c → FMP stable/quote.price ===
    fh = fetch_finnhub_quote(symbol)
    fmp_stable = fetch_fmp_stable_quote(symbol)

    if fh and fh.get("c"):
        base_close = fh["c"]
        print(f"[基准价] 使用 Finnhub.c: {base_close}")
    elif fmp_stable and fmp_stable.get("price"):
        base_close = fmp_stable["price"]
        print(f"[基准价] 使用 FMP stable/quote.price: {base_close}")
    else:
        print(f"[警告] 无法获取 {symbol} 的基准价")

    # === 2. 获取当前价 ===
    if status == "open":
        # 开盘：优先 Finnhub.c → FMP stable/quote.price
        if fh and fh.get("c"):
            current_price = fh["c"]
            change_amount = fh.get("d", 0)
            change_pct = fh.get("dp", 0)
            print(f"[开盘] 使用 Finnhub.c: {current_price}")
        elif fmp_stable and fmp_stable.get("price"):
            current_price = fmp_stable["price"]
            change_amount = fmp_stable.get("change", 0)
            change_pct = fmp_stable.get("changesPercentage", 0)
            print(f"[开盘] 回退 FMP stable/quote.price: {current_price}")
        else:
            await interaction.followup.send("未找到该股票，或当前无数据")
            return

    else:
        # 盘前 / 盘后 / 夜盘
        aftermarket_data = fetch_fmp_aftermarket_trade(symbol)
        if aftermarket_data and aftermarket_data.get("price"):
            current_price = aftermarket_data["price"]
            if base_close:
                change_amount = current_price - base_close
                change_pct = (change_amount / base_close) * 100
            print(f"[{status}] 使用 FMP aftermarket-trade.price: {current_price}")
        else:
            # 无实时价 → 回退显示收盘价 + 提示
            use_fallback = True
            if fh and fh.get("c"):
                current_price = fh["c"]
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)
                print(f"[{status}] 无实时价，回退 Finnhub.c: {current_price}")
            elif fmp_stable and fmp_stable.get("price"):
                current_price = fmp_stable["price"]
                if base_close:
                    change_amount = current_price - base_close
                    change_pct = (change_amount / base_close) * 100
                print(f"[{status}] 无实时价，回退 FMP stable/quote.price: {current_price}")
            else:
                await interaction.followup.send("未找到该股票，或当前无数据")
                return

    # === 3. 构建 Embed ===
    emoji = "📈" if change_amount >= 0 else "📉"  # 修复：使用实际 emoji（之前是 "up"/"down"，Embed 会显示文本）
    label_map = {
        "pre_market": "(盘前)",
        "open": "",
        "aftermarket": "(盘后)",
        "closed_night": "(收盘)"
    }
    label = label_map.get(status, "(未知)")

    title = f"{emoji} **{symbol}** {label}" if label else f"{emoji} **{symbol}**"
    color = 0xFF0000 if change_amount >= 0 else 0x00FF00  # 涨红跌绿

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="当前价", value=f"${current_price:.2f}", inline=True)
    embed.add_field(name="涨跌", value=f"${change_amount:+.2f} (`{change_pct:+.2f}`%)", inline=True)

    # 盘前/盘后/夜盘 无实时价时加提示
    if use_fallback and status != "open":
        embed.set_footer(text=fallback_note)

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
