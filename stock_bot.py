import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from datetime import datetime
import pytz

# ===== 配置 =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")  # ✅ 从环境变量读取

if not FMP_API_KEY:
    print("[❌ ERROR] 未设置 FMP_API_KEY！请在环境变量中配置")
if not DISCORD_TOKEN:
    print("[❌ ERROR] 未设置 DISCORD_TOKEN！请在环境变量中配置")

# ===== Bot 设置 =====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== 美东时间 =====
def get_ny_time():
    ny_tz = pytz.timezone("America/New_York")
    return datetime.now(ny_tz)

# ===== 市场阶段判断 =====
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

# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股价格")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()  # ✅ 告诉 Discord 稍后回复
    symbol = symbol.upper()

    if not FMP_API_KEY:
        await interaction.followup.send("❌ 未设置 FMP_API_KEY，请管理员检查配置。")
        return

    status = market_status()

    try:
        # ===== Stock Quote =====
        quote_url = f"https://financialmodelingprep.com/stable/quote?symbol={symbol}&apikey={FMP_API_KEY}"
        quote_data = requests.get(quote_url, timeout=5).json()
        if not quote_data:
            await interaction.followup.send(f"❌ 未找到股票代码 `{symbol}` 的信息。")
            return
        stock_price = quote_data[0]["price"]
        change_amount = quote_data[0]["change"]
        change_pct = quote_data[0]["changePercentage"]

        price_to_show = stock_price

        # ===== 盘前/盘后使用 Aftermarket Quote =====
        if status in ["pre_market", "aftermarket"]:
            after_url = f"https://financialmodelingprep.com/stable/aftermarket-quote?symbol={symbol}&apikey={FMP_API_KEY}"
            after_data = requests.get(after_url, timeout=5).json()
            if after_data and len(after_data) > 0 and after_data[0].get("bidPrice"):
                bid_price = after_data[0]["bidPrice"]
                price_to_show = bid_price
                change_amount = bid_price - stock_price
                change_pct = (change_amount / stock_price) * 100

        # ===== 涨跌 emoji =====
        emoji = "📈" if change_amount >= 0 else "📉"

        # ===== 时段标签 =====
        if status == "pre_market":
            label = "盘前"
        elif status == "open":
            label = "盘中"
        elif status == "aftermarket":
            label = "盘后"
        else:
            label = "收盘"

        # ===== 构建消息 =====
        msg = f"{emoji} {symbol} ({label})\n当前价: ${price_to_show:.2f}\n涨跌: ${change_amount:+.2f} ({change_pct:+.2f}%)"
        if status == "closed_night":
            msg += "\n💤 收盘阶段，无法查询实时数据。"

        await interaction.followup.send(msg)

    except Exception as e:
        await interaction.followup.send(f"❌ 查询出错: {e}")

# ===== 启动事件 =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 已登录为 {bot.user}，Slash Command 已同步到 Discord")

# ===== 启动 Bot =====
bot.run(DISCORD_TOKEN)
