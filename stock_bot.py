import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from datetime import datetime
import pytz

# Bot 前缀不用了，使用 slash 命令
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # Finnhub API Key

# 定义美东时间时区
eastern = pytz.timezone('US/Eastern')

# 美股交易时间（分钟数）
REGULAR_OPEN = 9 * 60 + 30   # 09:30
REGULAR_CLOSE = 16 * 60      # 16:00
PRE_MARKET_OPEN = 4 * 60     # 04:00
PRE_MARKET_CLOSE = 9 * 60 + 30
AFTER_HOURS_OPEN = 16 * 60
AFTER_HOURS_CLOSE = 20 * 60  # 20:00

def get_market_session():
    """返回当前市场阶段字符串"""
    now = datetime.now(eastern)
    minutes_now = now.hour * 60 + now.minute

    if PRE_MARKET_OPEN <= minutes_now < PRE_MARKET_CLOSE:
        return "(盘前)"
    elif REGULAR_OPEN <= minutes_now < REGULAR_CLOSE:
        return ""  # 正常开盘无提示
    elif AFTER_HOURS_OPEN <= minutes_now < AFTER_HOURS_CLOSE:
        return "(盘后)"
    else:
        return "(收盘)"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()  # 同步 slash 命令
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Sync failed: {e}")

# 注册 slash 命令 /stock
@bot.tree.command(name="stock", description="查询股票价格和涨跌")
@app_commands.describe(symbol="请输入股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    stock_symbol = symbol.upper()

    url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
    except Exception as e:
        await interaction.response.send_message(f"❌ 请求股票数据失败: {e}", ephemeral=True)
        return

    if "error" in data or not data.get("c"):
        await interaction.response.send_message(f'❌ 无法找到股票 {stock_symbol} 的信息，请检查代码是否正确。', ephemeral=True)
        return

    latest_price = data['c']
    previous_close = data['pc']

    price_change = latest_price - previous_close
    percent_change = (price_change / previous_close) * 100

    change_symbol = '📈' if price_change > 0 else '📉'

    formatted_price = f"{latest_price:,.2f}"
    formatted_price_change = f"{price_change:,.2f}"
    formatted_percent_change = f"{percent_change:.2f}"

    session_info = get_market_session()

    await interaction.response.send_message(
        f'{change_symbol} {stock_symbol} {session_info}\n'
        f'当前价: ${formatted_price}\n'
        f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
    )

# 启动机器人
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(DISCORD_TOKEN)
