import discord
import requests
import os
from datetime import datetime
import pytz

# 启用读取消息内容的权限
intents = discord.Intents.default()
intents.message_content = True  # 启用读取消息内容权限
client = discord.Client(intents=intents)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # 从环境变量读取 API 密钥
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")      # 从环境变量读取 Discord 令牌

# 定义美东时间时区
eastern = pytz.timezone('US/Eastern')

# 美股交易时间 (美东时间，分钟表示)
REGULAR_OPEN = 9 * 60 + 30    # 09:30
REGULAR_CLOSE = 16 * 60       # 16:00
PRE_MARKET_OPEN = 4 * 60      # 04:00
PRE_MARKET_CLOSE = 9 * 60 + 30
AFTER_HOURS_OPEN = 16 * 60
AFTER_HOURS_CLOSE = 20 * 60   # 20:00

def get_market_session():
    """返回当前市场阶段字符串"""
    now = datetime.now(eastern)
    minutes_now = now.hour * 60 + now.minute

    if PRE_MARKET_OPEN <= minutes_now < PRE_MARKET_CLOSE:
        return "盘前交易 ⏰"
    elif REGULAR_OPEN <= minutes_now < REGULAR_CLOSE:
        return ""  # 正常开盘，无提示
    elif AFTER_HOURS_OPEN <= minutes_now < AFTER_HOURS_CLOSE:
        return "盘后交易 🌙"
    else:
        return "收盘 ❌"

# 机器人启动时的事件
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# 监听消息事件
@client.event
async def on_message(message):
    print(f"Received message: {message.content}")  # 调试用

    if message.author == client.user:
        return
    
    if message.content.startswith('$'):
        stock_symbol = message.content[1:].upper()

        # Finnhub 需要加交易所前缀，如 NASDAQ:TSLA
        if ":" not in stock_symbol:
            stock_symbol_full = f"NASDAQ:{stock_symbol}"
        else:
            stock_symbol_full = stock_symbol

        url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol_full}&token={FINNHUB_API_KEY}'
        response =
