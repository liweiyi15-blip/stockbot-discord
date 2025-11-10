# stock_bot.py
import discord
from discord.ext import commands
import yfinance as yf

# ==========================
# 填入你的Token
# ==========================
DISCORD_TOKEN = "MTQzNzEyNTQ4ODI0MDc1NDc4MA.GxNsek.WGqOf6XdxY8A7vcocI27CyotYU8-f8URLPIzZ4"
FINNHUB_TOKEN = "d48omf9r01qnpsnoq1vgd48omf9r01qnpsnoq200"

# 设置机器人前缀
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="$", intents=intents)

# 机器人启动事件
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# 股票查询命令
@bot.command(name="stock", help="查询股票信息, 用法：$stock TSLA")
async def stock(ctx, *, code: str):
    code = code.upper()
    try:
        stock = yf.Ticker(code)
        data = stock.info

        # 获取价格信息
        current = data.get("regularMarketPrice")
        pre = data.get("preMarketPrice")
        post = data.get("postMarketPrice")
        change = data.get("regularMarketChange")
        change_percent = data.get("regularMarketChangePercent")

        # 判断数据是否存在
        if current is None:
            await ctx.send(f"❌ 无法找到股票 {code} 的信息，请检查代码是否正确。")
            return

        msg = f"📉 {code}\n"
        msg += f"收盘: ${current:.2f}\n"
        if pre is not None:
            msg += f"盘前: ${pre:.2f}\n"
        if post is not None:
            msg += f"盘后: ${post:.2f}\n"
        if change is not None and change_percent is not None:
            msg += f"涨跌: {change:.2f} ({change_percent:.2f}%)"

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ 查询 {code} 时出错：{e}")

# 支持 $TSLA 直接查询
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith("$"):
        code = message.content[1:].strip()
        ctx = await bot.get_context(message)
        await stock(ctx, code=code)

    await bot.process_commands(message)

# 启动机器人
bot.run(DISCORD_TOKEN)
