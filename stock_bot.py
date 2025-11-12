import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from datetime import datetime
import pytz

# ===== 读取环境变量 =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")

if not DISCORD_TOKEN:
    print("[❌ ERROR] 未读取到 DISCORD_TOKEN！")
if not FMP_API_KEY:
    print("[⚠️ WARNING] 未读取到 FMP_API_KEY，部分功能可能无法使用。")

# ===== 设置 Bot =====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== 获取美东时间 =====
def get_ny_time():
    ny_tz = pytz.timezone("America/New_York")
    return datetime.now(ny_tz)

# ===== 判断市场时段 =====
def market_status():
    now = get_ny_time()
    weekday = now.weekday()
    if weekday >= 5:
        return "closed_night"  # 周末算作收盘
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    aftermarket_end = now.replace(hour=20, minute=0, second=0, microsecond=0)  # 盘后到20:00

    if now < open_time:
        return "pre_market"       # 盘前
    elif open_time <= now <= close_time:
        return "open"             # 盘中
    elif close_time < now <= aftermarket_end:
        return "aftermarket"      # 盘后
    else:
        return "closed_night"     # 夜盘/收盘

# ===== Slash Command: /stock =====
@bot.tree.command(name="stock", description="查询美股价格")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    symbol = symbol.upper()
    if not FMP_API_KEY:
        await interaction.response.send_message("❌ 未设置 FMP_API_KEY，请管理员检查配置。")
        return

    status = market_status()
    try:
        # 获取 Stock Quote
        quote_url = f"https://financialmodelingprep.com/stable/quote?symbol={symbol}&apikey={FMP_API_KEY}"
        quote_data = requests.get(quote_url).json()
        if not quote_data:
            await interaction.response.send_message(f"❌ 未找到股票代码 `{symbol}` 的信息。")
            return

        stock_price = quote_data[0]["price"]
        prev_close = quote_data[0]["previousClose"]

        price_to_show = stock_price
        change_amount = quote_data[0]["change"]
        change_pct = quote_data[0]["changePercentage"]

        # 盘前/盘后阶段使用 Aftermarket Quote
        if status in ["pre_market", "aftermarket"]:
            after_url = f"https://financialmodelingprep.com/stable/aftermarket-quote?symbol={symbol}&apikey={FMP_API_KEY}"
            after_data = requests.get(after_url).json()
            if after_data and isinstance(after_data, list) and len(after_data) > 0:
                bid_price = after_data[0].get("bidPrice")
                if bid_price:
                    price_to_show = bid_price
                    change_amount = bid_price - stock_price
                    change_pct = (change_amount / stock_price) * 100

        # 判断涨跌 emoji
        emoji = "📈" if change_amount >= 0 else "📉"

        # 市场标签
        if status == "pre_market":
            label = "盘前"
        elif status == "open":
            label = "盘中"
        elif status == "aftermarket":
            label = "盘后"
        else:
            label = "收盘"

        msg = (
            f"{emoji} {symbol} ({label})\n"
            f"当前价: ${price_to_show:.2f}\n"
            f"涨跌: ${change_amount:+.2f} ({change_pct:+.2f}%)"
        )

        # 夜盘提示
        if status == "closed_night":
            msg += "\n💤 收盘阶段，无法查询实时数据。"

        await interaction.response.send_message(msg)

    except Exception as e:
        await interaction.response.send_message(f"❌ 查询出错: {e}")

# ===== 启动事件 =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 已登录为 {bot.user}，Slash Command 已同步到 Discord")

# ===== 启动 Bot =====
bot.run(DISCORD_TOKEN)
