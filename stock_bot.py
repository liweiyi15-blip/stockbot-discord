# ===== /stock 命令 (极简版) =====
@bot.tree.command(name="stock", description="查询美股实时价格（支持盘前/盘后）")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    symbol = symbol.upper().strip()
    status = market_status()
    
    # 1. 获取数据 (逻辑保持不变)
    quote_task = fetch_fmp_stock_quote(symbol)
    trade_task = fetch_fmp_extended_trade(symbol) if status in ["pre_market", "aftermarket"] else None
    
    quote_data = await quote_task
    extended_data = await trade_task if trade_task else None

    # 基准价 logic
    base_close = None
    if quote_data:
        base_close = quote_data.get("price")
    else:
        fh = await fetch_finnhub_quote(symbol)
        if fh: base_close = fh.get("c")

    current_price = None
    change_amount = 0.0
    change_pct = 0.0

    # 2. 计算逻辑 (逻辑保持不变)
    if status == "open":
        if quote_data:
            current_price = quote_data.get("price")
            change_amount = quote_data.get("change", 0)
            change_pct = quote_data.get("changePercentage") or quote_data.get("changesPercentage") or 0
        elif base_close:
            fh = await fetch_finnhub_quote(symbol)
            if fh:
                current_price = fh.get("c")
                change_amount = fh.get("d", 0)
                change_pct = fh.get("dp", 0)

    elif status in ["pre_market", "aftermarket"]:
        if extended_data and extended_data.get("price"):
            current_price = extended_data["price"]
            if base_close:
                change_amount = current_price - base_close
                if base_close != 0:
                    change_pct = (change_amount / base_close) * 100
        else:
            current_price = base_close

    else: # closed_night
        current_price = base_close
        if quote_data:
            change_amount = quote_data.get("change", 0)
            change_pct = quote_data.get("changePercentage") or quote_data.get("changesPercentage") or 0

    # 3. 输出结果 (极简优化版)
    if current_price is None or current_price == 0:
        await interaction.followup.send(f"❌ 未找到 **{symbol}**")
        return

    # 定义极简状态后缀
    label_map = {
        "pre_market": "(盘前)", 
        "open": "",             # 交易中不显示后缀，保持干净
        "aftermarket": "(盘后)", 
        "closed_night": "(收盘)"
    }
    status_suffix = label_map.get(status, "")
    
    # 微调数据
    if abs(change_amount) < 0.001:
        change_amount = 0
        change_pct = 0

    # 设置侧边栏颜色
    embed_color = 0xFF3131 if change_amount >= 0 else 0x00C853
    
    # 【核心修改】标题直接显示 "Symbol (状态)"
    embed = discord.Embed(title=f"{symbol} {status_suffix}", color=embed_color)
    
    # 生成 ANSI 彩色块 (假设你保留了上面的 format_ansi_price 函数)
    # 如果没有那个函数，请告诉我，我再发一次
    ansi_block = format_ansi_price(current_price, change_amount, change_pct)
    
    # Description 只放 ANSI 块，不放任何其他废话
    embed.description = ansi_block
    
    # 不再添加 add_field (移除了时间)
    # Footer 可以保留极短的提示，或者如果你连 Footer 都不想要，可以把下面两行删掉
    if status == "closed_night":
        embed.set_footer(text="💤 已收盘")
    
    await interaction.followup.send(embed=embed)
