import discord
import requests
import os

# 启用读取消息内容的权限
intents = discord.Intents.default()
intents.message_content = True  # 启用读取消息内容权限
client = discord.Client(intents=intents)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # 从环境变量读取 API 密钥
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # 从环境变量读取 Discord 令牌

# 机器人启动时的事件
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# 监听消息事件
@client.event
async def on_message(message):
    print(f"Received message: {message.content}")  # 调试输出消息内容

    # 如果消息来自机器人本身，忽略
    if message.author == client.user:
        return
    
    # 当用户发送以 $ 开头的股票代码时
    if message.content.startswith('$'):
        stock_symbol = message.content[1:].upper()  # 提取股票代码并转大写
        
        # 请求股票数据
        url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
        response = requests.get(url)
        data = response.json()
        
        # 检查是否返回了有效的数据
        if "error" in data or not data.get("c"):
            await message.channel.send(f'❌ 无法找到股票 {stock_symbol} 的信息，请检查代码是否正确。')
            return
        
        # 获取价格
        latest_price = data['c']
        previous_close = data['pc']
        
        # 计算涨跌幅
        price_change = latest_price - previous_close
        percent_change = (price_change / previous_close) * 100
        
        # 生成符号
        change_symbol = '📈' if price_change > 0 else '📉'
        
        # 格式化为两位小数
        formatted_price = f"{latest_price:,.2f}"
        formatted_price_change = f"{price_change:,.2f}"
        formatted_percent_change = f"{percent_change:.2f}"  # 保留正负号
        
        # 发送消息
        await message.channel.send(
            f'{change_symbol} {stock_symbol}\n'
            f'当前价: ${formatted_price}\n'
            f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
        )

# 启动机器人
client.run(DISCORD_TOKEN)
