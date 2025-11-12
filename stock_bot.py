import discord
from discord.ext import commands
import requests
import os
from datetime import datetime, timedelta
import pytz

# ===== Debug 检查 Discord Token =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")  # ✅ 从环境变量读取 API key

print("\n===== DEBUG: 环境变量检查 =====")
if not DISCORD_TOKEN:
    print("[❌ ERROR] 未读取到 DISCORD_TOKEN！请到 Railway 设置 Variables。")
else:
    print("[✅ INFO] 成功读取到 DISCORD_TOKEN")
    print(f"前10位: {DISCORD_TOKEN[:10]} ... 后5位: {DISCORD_TOKEN[-5:]}")

if not FMP_API_KEY:
    print("[⚠️ WARNING] 未读取到 FMP_API_KEY，部分功能可能无法使用。")
else:
    print("[✅ INFO] 成功读取到 FMP_API_KEY")
    print(f"前5位: {FMP_API_KEY[:5]} ... 后3位: {FMP_API_KEY[-3:]}")
print("=====================================\n")

# ===== 设置 Discord Bot =====
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

# ===== 判断美股是否开盘 =====
def is_market_open():
    ny_tz = pytz.timezone("America/New_York")
    now = datetime.now(ny_tz)
    weekday = now.weekday()
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if weekday >= 5:
        return False
    return market_open <= now <= market_close

# ===== 机器人启动事件 =====
@bot.event
async def on_ready():
    print(f"✅ 已登录为 {bot.user}")

# ===== 股票查询指令 =====
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith("$"):
        symbol = message.content[1:].upper()

        if not FMP_API_KEY:
            await message.channel.send("❌ 未设置 FMP_API_KEY，请管理员检查配置。")
            return

        url = f"https://financialmodelingprep.com/stable/quote-short?symbol={symbol}&apikey={FMP_API_KEY}"
        response = requests.get(url)
        data = response.json()

        if not data:
            await message.channel.send(f"❌ 未找到股票代码 `{symbol}` 的信息。")
            return

        price = data[0]["price"]
        change = data[0].get("change", 0)
        volume = data[0].get("volume", 0)

        if is_market_open():
            title = f"📈 {symbol} (盘中)"
        else:
            title = f"📉 {symbol} (盘后)"

        msg = (
            f"{title}\n"
            f"当前价: ${price:.2f}\n"
            f"涨跌: {change:+.2f}\n"
            f"成交量: {volume:,}"
        )
        await message.channel.send(msg)

# ===== 启动机器人 =====
bot.run(DISCORD_TOKEN)
