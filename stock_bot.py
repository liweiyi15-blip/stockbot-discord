import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
from datetime import datetime
import pytz

# ===== 环境变量 =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

# ===== Bot 定义 =====
class StockBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="$", intents=intents)
        self.session = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(headers=HEADERS)
        await self.tree.sync()
    
    async def close(self):
        await self.session.close()
        await super().close()

bot = StockBot()

# ===== 时间工具 =====
def get_ny_time():
    tz = pytz.timezone('America/New_York')
    return datetime.now(tz)

def market_status():
    now = get_ny_time()
    weekday = now.weekday()
    if weekday >= 5: return "closed_night"
    
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    aftermarket_end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    premarket_start = now.replace(hour=4, minute=0, second=0, microsecond=0)

    if premarket_start <= now < open_time: return "pre_market"
    elif open_time <= now <= close_time: return "open"
    elif close_time < now <= aftermarket_end: return "aftermarket"
    else: return "closed_night"

# ===== 数据源接口 (带日志) =====

async def fetch_fmp_stock_quote(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol.upper()}?apikey={FMP_API_KEY}"
        print(f"🔍 [DEBUG] 请求 Quote: {url}")
        async with bot.session.get(url, timeout=10) as r:
            if r.status != 200: 
                print(f"❌ [DEBUG] Quote 请求失败: Status {r.status}")
                return None
            data = await r.json()
            if data:
                # 打印关键字段
                print(f"📄 [DEBUG] Quote 返回数据: price={data[0].get('price')}, previousClose={data[0].get('previousClose')}")
            else:
                print("❌ [DEBUG] Quote 返回空数据")
            return data[0] if data else None
    except Exception as e:
        print(f"❌ [DEBUG] Quote 异常: {e}")
        return None

async def fetch_finnhub_quote(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        async with bot.session.get(url, timeout=10) as r:
            data = await r.json()
            print(f"📄 [DEBUG] Finnhub 返回: c={data.get('c')}, pc={data.get('pc')}")
            return data if data and data.get("c") not in (0, None) else None
    except:
        return None

async def fetch_fmp_extended_trade(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-trade?symbol={symbol.upper()}&apikey={FMP_API_KEY}"
        print(f"🔍 [DEBUG] 请求 Trade: {url}")
        async with bot.session.get(url, timeout=10) as r:
            data = await r.json()
            if not data or not isinstance(data, list) or len(data) == 0:
                print("❌ [DEBUG] Trade 返回空")
                return None
            
            data.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            latest = data[0]
            print(f"📄 [DEBUG] Trade 最新成交: price={latest.get('price')}, time={latest.get('timestamp')}")
            return latest if latest.get("price") not in (None, 0) else None
    except Exception as e:
        print(f"❌ [DEBUG] Trade 异常: {e}")
        return None

async def fetch_fmp_crypto_quote(symbol: str):
    # ... (保持不变)
    try:
        url = f"https://financialmodelingprep.com/stable/quote?symbol={symbol}&apikey={FMP_API_KEY}"
        async with bot.session.get(url, timeout=10) as r:
            if r.status != 200: return None
            data = await r.json()
            return data[0] if data else None
    except:
        return None

# ===== /stock 命令 (带日志) =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    print(f"\n=== 开始查询: {symbol} | 状态: {status} ===")
    
    quote_task = fetch_fmp_stock_quote(symbol)
    trade_task = fetch_fmp_extended_trade(symbol) if status in ["pre_market", "aftermarket"] else None
    
    quote_data = await quote_task
    extended_data = await trade_task if trade_task else None

    # --- 这里的逻辑是关键 ---
    base_close = None
    source_used = "None"
    
    if quote_data:
        # 强制只取 price
        base_close = quote_data.get("price")
        source_used = f"FMP Quote Price (v={base_close})"
        
        # 如果这里 base_close 依然是 408.92，那说明 API 返回的就是 408.92
        if base_close == quote_data.get("previousClose"):
             print("⚠️ [警告] FMP Quote 的 price 和 previousClose 完全一样！")
             
    else:
        # 备用 Finnhub
        fh = await fetch_finnhub_quote(symbol)
        if fh: 
            base_close = fh.get("pc")
            source_used = f"Finnhub PC (v={base_close})"

    print(f"🛠 [决策] 最终使用的基准昨收: {base_close} | 来源: {source_used}")

    current_price = None
    change_amount = 0.0
    change_pct = 0.0

    if status == "open":
        if quote_data:
            current_price = quote_data.get("price")
            change_amount = quote_data.get("change", 0)
            change_pct = quote_data.get("changesPercentage", 0)
        elif base_close:
            fh = await fetch_finnhub_quote(symbol)
            if fh:
                current_price = fh.get("c")
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)

    elif status in ["pre_market", "aftermarket"]:
        if extended_data and extended_data.get("price"):
            current_price = extended_data["price"]
            print(f"📈 [计算] 当前价({current_price}) - 基准({base_close})")
            
            if base_close:
                change_amount = current_price - base_close
                if base_close != 0:
                    change_pct = (change_amount / base_close) * 100
        else:
            current_price = base_close

    else: 
        current_price = base_close
        if quote_data:
            change_amount = quote_data.get("change", 0)
            change_pct = quote_data.get("changesPercentage", 0)

    if current_price is None or current_price == 0:
        await interaction.followup.send(f"未找到 **{symbol}** 的有效数据。")
        return

    label_map = {"pre_market": "(盘前)", "open": "", "aftermarket": "(盘后)", "closed_night": "(收盘)"}
    display_label = label_map.get(status, "")
    
    if abs(change_amount) < 0.001:
        change_amount = 0
        change_pct = 0
        if status != "open": display_label = "(收盘)"
    
    print(f"✅ [完成] 结果: {current_price} | 涨跌: {change_amount}")

    color = 0xFF0000 if change_amount >= 0 else 0x00FF00
    embed = discord.Embed(title=f"**{symbol}** {display_label}", color=color)
    embed.add_field(
        name="",
        value=f"**当前价** `${current_price:.2f}`  **涨跌** `${change_amount:+.2f} ({change_pct:+.2f}%)`",
        inline=False
    )
    if status == "closed_night": embed.set_footer(text="💤 此时段显示收盘价")

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="crypto", description="查询数字货币实时价格")
async def crypto(interaction: discord.Interaction, symbol: str):
    # ... (保持不变)
    await interaction.response.defer()
    original = symbol.strip().upper()
    symbol = original + "USD" if not original.endswith("USD") else original
    data = await fetch_fmp_crypto_quote(symbol)
    if not data or not data.get("price"):
        await interaction.followup.send("未找到该数字货币")
        return
    price = data["price"]
    change = data.get("change", 0)
    pct = data.get("changePercentage", 0)
    embed = discord.Embed(title=f"**{original}**", color=0xFF0000 if change >= 0 else 0x00FF00)
    embed.add_field(name="", value=f"**当前价** `${price:.2f}`  **涨跌** `${change:+.2f} ({pct:+.2f}%)`", inline=False)
    await interaction.followup.send(embed=embed)

@bot.event
async def on_ready():
    print(f"Bot 已上线: {bot.user} | 🔍 调试模式已开启")

bot.run(DISCORD_TOKEN)
