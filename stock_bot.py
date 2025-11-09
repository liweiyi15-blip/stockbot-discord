import discord
from discord.ext import commands
import requests
import os

# 使用 py-cord 库的 Bot 创建一个客户端实例
intents = discord.Intents.default()
client = commands.Bot(command_prefix="/", intents=intents)

# 读取环境变量中的 API 密钥和 Discord 令牌
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # 从环境变量读取 API 密钥
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # 从环境变量读取 Discord 令牌

# 注册 /stock 命令
@client.tree.command(name="stock", description="查询股票价格和涨跌")
async def stock(interaction: discord.Interaction, stock_symbol: str):
    # 请求股票数据
    url = f'https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={FINNHUB_API_KEY}'
    response = requests.get(url)
    data = response.json()

    # 检查是否返回了有效的数据
    if "error" in data or not data.get("c"):
        await interaction.response.send_message(f'无法找到股票 {stock_symbol} 的信息。请检查股票代码是否正确。')
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
        await interaction.response.send_message(
            f'{change_symbol} {stock_symbol}\n'
            f'当前价: ${formatted_price}\n'
            f'涨跌: {formatted_price_change} ({formatted_percent_change}%)'
        )

# 启动机器人
client.run(DISCORD_TOKEN)
