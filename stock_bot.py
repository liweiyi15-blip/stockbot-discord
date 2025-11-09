import discord
import requests
import os

# 设置Discord机器人
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# 读取环境变量中的 API 密钥和 Discord 令牌
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # 从环境变量读取 API 密钥
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # 从环境变量读取 Discord 令牌

# 机器人启动时的事件
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# 监听消息事件
@client.event
async def on_message(message):
    # 打印接收到的消息内容
    print(f"Received message: {message.content}")
    
    # 如果消息来自机器人本身，忽略
    if message.author == client.user:
        return
    
    # 当用户发送股票代码时，查询股票信息
    if message.content.startswith('$'):
        stock_symbol = message.content[1:].upper()  # 提取股票符号（去掉$）
        
        # 发送确认收到消息的反馈
        await message.channel.send(f"Received stock query for: {stock_symbol}")
        print(f"Processing stock: {stock_symbol}")  # 打印正在处理的股票代码
        
        # 请求股票数据
        url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
        response = requests.get(url)
        data = response.json()
        
        # 检查是否返回了有效的数据
        if "error" in data or not data.get("c"):
            await message.channel.send(f'无法找到股票 {stock_symbol} 的信息。请检查股票代码是否正确。')
        else:
            # 获取最新的股票价格
            latest_price = data['c']
            previous_close = data['pc']
            
            # 计算涨跌幅
            price_change = latest_price - previous_close
            percent_change = (price_change / previous_close) * 100
            
            # 生成符号和格式化输出
            change_symbol = '📈' if price_change > 0 else '📉'
            percent_change = abs(percent_change)  # 去除负号
            
            # 强制保留小数点后两位
            formatted_price = f"{latest_price:,.2f}"
            formatted_price_change = f"{price_change:,.2f}"
            formatted_percent_change = f"{percent_change:.2f}"
            
            # 构建并发送消息
            await message.channel.send(
                f'{change_symbol} {stock_symbol}\n'
                f'当前价: ${formatted_price}\n'
                f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
            )

# 启动机器人
client.run(DISCORD_TOKEN)
