# ===== /stock 命令 =====
@bot.tree.command(name="stock", description="查询美股价格")
@app_commands.describe(symbol="股票代码，例如 TSLA")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()
    symbol = symbol.upper()
    status = market_status()

    price_to_show = None
    change_amount = None
    change_pct = None
    emoji = "📈"
    label = ""

    try:
        # ===== 优先 FMP =====
        stock = fetch_fmp_stock(symbol)
        if stock:
            stock_price = stock["price"]
            prev_close = stock["previousClose"]
            price_to_show = stock_price
            change_amount = stock["change"]
            change_pct = stock["changePercentage"]

            # 盘前/盘后使用 aftermarket
            if status in ["pre_market", "aftermarket"]:
                after = fetch_fmp_aftermarket(symbol)
                if after:
                    bid_price = after["bidPrice"]
                    price_to_show = bid_price
                    change_amount = bid_price - stock_price
                    change_pct = (change_amount / stock_price) * 100

        else:
            # ===== FMP 失败 → Finnhub =====
            fh = fetch_finnhub_quote(symbol)
            if fh:
                stock_price = fh["c"]
                prev_close = fh["pc"]
                price_to_show = stock_price
                change_amount = stock_price - prev_close
                change_pct = (change_amount / prev_close) * 100
            else:
                # ===== 都查不到 =====
                await interaction.followup.send("😭 此代码不支持该时段查询")
                return

        # ===== emoji =====
        emoji = "📈" if change_amount >= 0 else "📉"

        # ===== 时段标签 =====
        if status == "pre_market":
            label = "盘前"
        elif status == "open":
            label = "盘中"
        elif status == "aftermarket":
            label = "盘后"
        else:
            label = "收盘"

        # ===== 构建消息 =====
        msg = f"{emoji} {symbol} ({label})\n当前价: ${price_to_show:.2f}\n涨跌: ${change_amount:+.2f} ({change_pct:+.2f}%)"
        if status == "closed_night":
            msg += "\n💤 收盘阶段，无法查询实时数据。"

        await interaction.followup.send(msg)

    except Exception as e:
        await interaction.followup.send(f"❌ 查询出错: {e}")
