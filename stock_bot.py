import discord
import requests
import os
from datetime import datetime
import pytz

# 启用消息权限
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# 美东时间时区
eastern = pytz.timezone('US/Eastern')
REGULAR_OPEN = 9 * 60 + 30
REGULAR_CLOSE = 16 * 60
PRE_MARKET_OPEN = 4 * 60
PRE_MARKET_CLOSE = 9 * 60 + 30
AFTER_HOURS_OPEN = 16 * 60
AFTER_HOURS_CLOSE = 20 * 60

def get_market_session():
    now = datetime.now(eastern)
    minutes_now = now.hour * 60 + now.minute
    if PRE_MARKET_OPEN <= minutes_now < PRE_MARKET_CLOSE:
        return "(盘前)"
    elif REGULAR_OPEN <= minutes_now < REGULAR_CLOSE:
        return ""  # 正常交易，无提示
    elif AFTER_HOURS_OPEN <= minutes_now < AFTER_HOURS_CLOSE:
        return "(盘后)"
    else:
        return "(收盘)"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print(f'Synced {len(bot.application_commands)} command(s)')

# 创建 Slash 命令，参数提示中文
@bot.slash_command(name="stock", description="查询股票价格和涨跌")
async def stock(ctx, symbol: str):
    stock_symbol = symbol.upper()
    url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
    response = requests.get(url)
    data = response.json()

    if "error" in data or not data.get("c"):
        await ctx.respond(f'❌ 无法找到股票 {stock_symbol} 的信息，请检查代码是否正确。')
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

    await ctx.respond(
        f'{change_symbol} {stock_symbol} {session_info}\n'
        f'当前价: ${formatted_price}\n'
        f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
    )

bot.run(DISCORD_TOKEN)
