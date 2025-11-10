import discord
import yfinance as yf
import os

# 启用读取消息内容的权限
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # Discord 令牌

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("$"):
        symbol = message.content[1:].upper()
        print(f"Received message: {symbol}")

        try:
            stock = yf.Ticker(symbol)
            data = stock.fast_info
            current_price = data["last_price"]
            previous_close = data["previous_close"]
            
            price_change = current_price - previous_close
            percent_change = (price_change / previous_close) * 100
            
            change_symbol = "📈" if price_change > 0 else "📉"
            formatted_price = f"{current_price:.2f}"
            formatted_change = f"{price_change:.2f}"
            formatted_percent = f"{percent_change:.2f}"

            market_state = stock.info.get("marketState", "N/A")
            if market_state == "PRE":
                session = "盘前"
            elif market_state == "POST":
                session = "盘后"
            elif market_state == "REGULAR":
                session = "盘中"
            else:
                session = "未知"

            await message.channel.send(
                f"{change_symbol} {symbol} ({session})\n"
                f"当前价: ${formatted_price}\n"
                f"涨跌: {formatted_change} ({formatted_percent}%)"
            )

        except Exception as e:
            await message.channel.send(f"无法获取 {symbol} 的信息: {e}")

client.run(DISCORD_TOKEN)
