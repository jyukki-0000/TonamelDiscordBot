import os
import re
import asyncio
import discord

from discord.ext import commands
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

# 実行ログ送信チャンネル
LOG_CHANNEL_ID = 1509705370447118407

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# ログ送信
# =========================
async def send_log(message):

    print(message)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if log_channel:

        try:
            await log_channel.send(f"```{message}```")

        except Exception as e:
            print(f"ログ送信失敗: {e}")


# =========================
# 大会取得
# =========================
async def get_tournaments():

    tournaments = []

    await send_log("Tonamel大会取得開始")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            locale="ja-JP"
        )

        page = await context.new_page()

        await send_log("一覧ページ読み込み中...")

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        await page.wait_for_selector(
            "div.competitions-list ul li",
            timeout=15000
        )

        # =========================
        # 一覧取得
        # =========================
        cards = await page.evaluate("""
        () => {

            const items = document.querySelectorAll('div.competitions-list ul li');

            return Array.from(items).map(li => {

                const a = li.querySelector('a[href]');
                const href = a ? a.href : '';

                const img = li.querySelector('img');
                const imgSrc = img ? img.src : '';

                const titleEl =
                    li.querySelector('h3') ||
                    li.querySelector('h2') ||
                    li.querySelector('[class*="title"]');

                const title = titleEl
                    ? titleEl.textContent.trim()
                    : li.textContent.trim().split('\\n')[0];

                return {
                    title,
                    href,
                    imgSrc
                };
            });
        }
        """)

        await send_log(f"取得カード数: {len(cards)}")

        # JST基準
        now_jst = datetime.now() + timedelta(hours=9)
        today = now_jst.date()

        weekdays = ["月", "火", "水", "木", "金", "土", "日"]

        # =========================
        # 詳細取得
        # =========================
        for card in cards:

            try:

                link = card["href"]

                if not link:
                    continue

                detail_page = await context.new_page()

                try:

                    await send_log(f"確認中: {card['title']}")

                    await detail_page.goto(
                        link,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    await detail_page.wait_for_timeout(2000)

                    detail = await detail_page.evaluate("""
                    () => {

                        const get = (sel) => {
                            const el = document.querySelector(sel);
                            return el ? el.textContent.trim() : "—";
                        };

                        return {
                            schedule_raw: get("span.a-text--medium"),
                            format: get("dl dd:nth-child(4) span"),
                            maxPlayers: get("dl dd:nth-child(6) span")
                        };
                    }
                    """)

                    schedule_text = detail["schedule_raw"]

                    await send_log(f"取得日時: {schedule_text}")

                    match = re.search(
                        r"\\d{4}/\\d{1,2}/\\d{1,2}\\(.+?\\)\\s*(\\d{1,2}):(\\d{2})",
                        schedule_text
                    )

                    if not match:

                        await send_log(
                            f"日付取得失敗: {schedule_text}"
                        )

                        continue

                    year_month_day = re.search(
                        r"\\d{4}/\\d{1,2}/\\d{1,2}",
                        schedule_text
                    ).group(0)

                    base_date = datetime.strptime(
                        year_month_day,
                        "%Y/%m/%d"
                    )

                    hour = int(match.group(1))
                    minute = int(match.group(2))

                    # JST補正なし
                    corrected = base_date.replace(
                        hour=hour,
                        minute=minute
                    )

                    await send_log(
                        f"変換後日時: {corrected.strftime('%Y/%m/%d %H:%M')}"
                    )

                    # 当日以外スキップ
                    if corrected.date() != today:

                        await send_log(
                            f"当日大会ではないためスキップ: {card['title']}"
                        )

                        continue

                    weekday = weekdays[corrected.weekday()]

                    display_schedule = corrected.strftime(
                        f"%Y/%m/%d({weekday}) %H:%M 〜"
                    )

                    tournaments.append({
                        "title": card["title"],
                        "link": link,
                        "image": card["imgSrc"],
                        "schedule": display_schedule,
                        "players": detail["maxPlayers"],
                        "format": detail["format"]
                    })

                    await send_log(
                        f"取得成功: {card['title']}"
                    )

                finally:
                    await detail_page.close()

            except Exception as e:

                await send_log(
                    f"大会処理失敗: {str(e)}"
                )

        await browser.close()

    await send_log(f"取得大会数: {len(tournaments)}")

    return tournaments


# =========================
# メッセージ削除
# =========================
async def purge_channel(channel):

    async for msg in channel.history(limit=100):

        try:
            await msg.delete()
            await asyncio.sleep(0.3)

        except Exception as e:
            print(f"メッセージ削除失敗: {e}")


# =========================
# 起動
# =========================
@bot.event
async def on_ready():

    await send_log(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:

        await send_log("チャンネル取得失敗")

        await bot.close()
        return

    await send_log("既存メッセージ削除中...")

    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = (
        datetime.now() + timedelta(hours=9)
    ).strftime("%Y/%m/%d")

    if not tournaments:

        await send_log("本日の大会なし")

        await channel.send(
            f"## Shadowverse: World Beyond Tonamel 大会一覧 {today_text}\n"
            f"> 本日の大会はありません。"
        )

        await bot.close()
        return

    await channel.send(
        f"## Shadowverse: World Beyond Tonamel 大会一覧 {today_text}"
    )

    for t in tournaments:

        embed = discord.Embed(
            title=t["title"],
            url=t["link"],
            color=0xee4235
        )

        embed.add_field(
            name="開催時間",
            value=t["schedule"],
            inline=False
        )

        embed.add_field(
            name="参加上限",
            value=t["players"],
            inline=True
        )

        embed.add_field(
            name="大会形式",
            value=t["format"],
            inline=True
        )

        if t["image"]:
            embed.set_thumbnail(url=t["image"])

        embed.set_footer(text="ShadowverseWB情報収集")

        await channel.send(embed=embed)

        await send_log(f"送信完了: {t['title']}")

    await send_log("全大会送信完了")

    await bot.close()


bot.run(TOKEN)