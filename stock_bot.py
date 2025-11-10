import discord
import requests
from datetime import datetime
import pytz

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

FINNHUB_API_KEY = "你的APIKEY"
DISCORD_TOKEN = "你的DISCORD TOKEN"

eastern = pytz.timezone('US/Eastern')
REGULAR_OPEN = 9*60+30
REGULAR_CLOSE = 16*60
PRE_MARKET_OPEN = 4*60
PRE_MARKET_CLOSE = 9*60+30
AFTER_HOURS_OPEN = 16*60
AFTER_HOURS_CLOSE = 20*60

def get_market_session():
    now = datetime.now(eastern)
    minutes_now = now.hour*60 + now.minute
    if PRE_MARKET_OPEN <= minutes_now < PRE_MARKET_CLOSE:
        return "(盘前)"
    elif REGULAR_OPEN <= minutes_now < REGULAR_CLOSE:
        return ""
    elif AFTER_HOURS_OPEN <= minutes_now < AFTER_HOURS_CLOSE:
        return "(盘后)"
    else:
        return "(收盘)"

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('$'):
        stock_symbol = message.content[1:].upper()
        url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
        response = requests.get(url)
        data = response.json()
        if "error" in data or not data.get("c"):
            await message.channel.send(f'❌ 无法找到股票 {stock_symbol}')
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
        await message.channel.send(
            f'{change_symbol} {stock_symbol} {session_info}\n'
            f'当前价: ${formatted_price}\n'
            f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
        )

client.run(DISCORD_TOKEN)
