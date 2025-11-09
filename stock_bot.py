import discord
import requests
import os
import asyncio

# 设置Discord机器人
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# 读取环境变量中的 API 密钥和 Discord 令牌
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # 从环境变量读取 API 密钥
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # 从环境变量读取 Discord 令牌

# 创建一个队列用于存储请求
task_queue = asyncio.Queue()

# 定义后台任务来处理队列中的任务
async def process_queue():
    while True:
        # 获取队列中的任务
        message, stock_symbol = await task_queue.get()
        
        # 请求股票数据
        url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
        response = requests.get(url)
        data = response.json()

        # 检查是否返回了有效的数据
        if "error" in data or not data.get("c"):
            await message.channel.send(f'无法找到股票 {stock_symbol} 的信息。请检查股票代码是否正确。')
        else:
            latest_price = data['c']
            previous_close = data['pc']
            price_change = latest_price - previous_close
            percent_change = (price_change / previous_close) * 100

            change_symbol = '📈' if price_change > 0 else '📉'
            percent_change = abs(percent_change)  # 去除负号

            formatted_price = f"{latest_price:,.2f}"
            formatted_price_change = f"{price_change:,.2f}"
            formatted_percent_change = f"{percent_change:.2f}"

            await message.channel.send(
                f'{change_symbol} {stock_symbol}\n'
                f'当前价: ${formatted_price}\n'
                f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
            )

        # 完成任务
        task_queue.task_done()

# 机器人启动时的事件
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    # 启动后台任务来处理队列
    client.loop.create_task(process_queue())

# 监听消息事件
@client.event
async def on_message(message):
    # 如果消息来自机器人本身，忽略
    if message.author == client.user:
        return

    # 仅处理以 $ 开头的消息
    if message.content.startswith('$'):
        stock_symbol = message.content[1:].upper()  # 提取股票符号（去掉$）

        # 过滤掉非有效的股票符号
        if not stock_symbol.isalpha():  # 如果符号不是字母组合（例如 $nio、$aapl）
            await message.channel.send("无效的股票符号。请使用正确的股票代码。")
            return

        # 将任务添加到队列中
        await task_queue.put((message, stock_symbol))

# 启动机器人
client.run(DISCORD_TOKEN)
