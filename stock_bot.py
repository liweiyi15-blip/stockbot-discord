import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
from datetime import datetime
import pytz

# ==================== 环境变量 ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# ==================== Bot 定义 ====================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="$", intents=intents)

# ==================== 工具函数 ====================
def get_ny_time():
    tz = pytz.timezone('America/New_York')
    return datetime.now(tz)

def market_status():
    now = get_ny_time()
    weekday = now.weekday()
    if weekday >= 5:
        return "closed_night"

    open_time      = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time     = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    after_end      = now.replace(hour=20, minute=0,  second=0, microsecond=0)
    pre_start      = now.replace(hour=4,  minute=0,  second=0, microsecond=0)

    if pre_start <= now < open_time:
        return "pre_market"
    elif open_time <= now <= close_time:
        return "open"
    elif close_time < now <= after_end:
        return "aftermarket"
    else:
        return "closed_night"

# ==================== 数据源 ====================
def fetch_finnhub_quote(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data or data.get("c") == 0:
            return None
        return data
    except Exception as e:
        print(f"Finnhub 查询失败: {e}")
        return None

def fetch_fmp_stock(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/quote/{symbol}?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data or len(data) == 0:
            return None
        print(f"[DEBUG] FMP stock quote raw: {data[0]}")
        return data[0]
    except Exception as e:
        print(f"FMP stock 查询失败: {e}")
        return None

def fetch_fmp_aftermarket_trade(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol}&apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            print(f"[DEBUG] FMP aftermarket-trade 失败: {r.status_code}")
            return None
        data = r.json()
        if not data or len(data) == 0:
            return None
        item = data[0]
        if "price" in item and item["price"] is not None and item["price"] > 0:
            return {"price": item["price"]}
        return None
    except Exception as e:
        print(f"FMP aftermarket-trade 查询失败: {e}")
        return None

# ==================== /stock 命令 ====================
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    print(f"[DEBUG] 查询 {symbol}，状态: {status}")

    price_to_show = change_amount = change_pct = None
    use_fallback = False
    fallback_note = "该时段不支持实时查询，显示收盘价。"

    # ---------- 基准价 ----------
    fh = fetch_finnhub_quote(symbol)
    benchmark_price = None
    if fh and fh.get("c") != 0:
        benchmark_price = fh["c"]

    if not benchmark_price:
        fmp = fetch_fmp_stock(symbol)
        if fmp:
            benchmark_price = fmp.get("price")

    # ---------- 各时段股价 ----------
    if status == "open":
        if fh and fh["c"] != 0:
            price_to_show = fh["c"]
            change_amount = fh.get("d", 0)
            change_pct    = fh.get("dp", 0)
        else:
            fmp = fetch_fmp_stock(symbol)
            if fmp:
                price_to_show = fmp.get("price")
                change_amount = fmp.get("change")
                change_pct    = fmp.get("changesPercentage")
            else:
                await interaction.followup.send("未找到该股票，或当前无数据")
                return
    else:
        # 盘前 / 盘后 → aftermarket-trade
        if status in ("pre_market", "aftermarket"):
            extended = fetch_fmp_aftermarket_trade(symbol)
            if extended and extended.get("price"):
                price_to_show = extended["price"]
            else:
                use_fallback = True

        # 收盘 / 夜盘 或 fallback
        if price_to_show is None:
            if fh and fh["c"] != 0:
                price_to_show = fh["c"]
            else:
                fmp = fetch_fmp_stock(symbol)
                if fmp:
                    price_to_show = fmp.get("price")
                else:
                    await interaction.followup.send("未找到该股票，或当前无数据")
                    return
            use_fallback = True

        if benchmark_price:
            change_amount = price_to_show - benchmark_price
            change_pct = (change_amount / benchmark_price) * 100 if benchmark_price != 0 else 0
        else:
            change_amount = change_pct = 0

    # ---------- 标签 ----------
    label_map = {
        "pre_market":   "(盘前)",
        "open":         "",
        "aftermarket":  "(盘后)",
        "closed_night": "(收盘)"
    }
    label = label_map.get(status, "未知")
    if use_fallback and status in ("pre_market", "aftermarket"):
        label = "(收盘)"

    # ---------- Embed（关键：横向排列）----------
    embed = discord.Embed(
        title=f"**{symbol}** {label}" if label else f"**{symbol}**",
        color=0x00FF00 if change_amount < 0 else 0xFF0000
    )

    # 关键：用一个 inline=False 的字段包裹两个 inline=True 的字段 → 手机横排
    embed.add_field(name="\u200b", value=f"**当前价**\n`${price_to_show:.2f}`", inline=True)
    embed.add_field(name="\u200b", value=f"**涨跌**\n`${change_amount:+.2f} (`{change_pct:+.2f}`%)`", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)  # 占位，强制换行

    if use_fallback and status != "open":
        embed.set_footer(text=fallback_note)

    await interaction.followup.send(embed=embed)

# ==================== 启动 ====================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot 已上线: {bot.user}")
    print(f"纽约时间: {get_ny_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")

bot.run(DISCORD_TOKEN)
