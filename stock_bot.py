import discord
import yfinance as yf
import os

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$'):
        stock_symbol = message.content[1:].upper()
        ticker = yf.Ticker(stock_symbol)
        info = ticker.info

        # 先尝试盘前价 -> 正常市场价 -> 盘后价
        price = info.get('preMarketPrice') or info.get('regularMarketPrice') or info.get('postMarketPrice')
        previous_close = info.get('previousClose')

        if price is None or previous_close is None:
            await message.channel.send(f'无法获取 {stock_symbol} 的当前价格。')
            return

        price_change = price - previous_close
        percent_change = (price_change / previous_close) * 100
        change_symbol = '📈' if price_change > 0 else '📉'

        # 判断时段
        if info.get('preMarketPrice'):
            period = '盘前'
        elif info.get('postMarketPrice'):
            period = '盘后'
        else:
            period = '盘中'

        # 格式化
        formatted_price = f"{price:.2f}"
        formatted_price_change = f"{price_change:.2f}"
        formatted_percent_change = f"{percent_change:.2f}"

        await message.channel.send(
            f'{change_symbol} {stock_symbol} ({period})\n'
            f'当前价: ${formatted_price}\n'
            f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
        )

client.run(DISCORD_TOKEN)
