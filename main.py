import os
import re
import asyncio
import discord

from discord.ext import commands
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

# ログ送信チャンネル
LOG_CHANNEL_ID = 1509705370447118407

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ログをまとめる
logs = []


# =========================
# ログ追加
# =========================
def add_log(message):

    print(message)
    logs.append(message)


# =========================
# ログ送信
# =========================
async def send_logs():

    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if not log_channel:
        return

    text = "\n".join(logs)

    # Discord文字数対策
    if len(text) > 1900:
        text = text[-1900:]

    await log_channel.send(f"```{text}```")


# =========================
# 大会取得
# =========================
async def get_tournaments():

    tournaments = []

    add_log("Tonamel大会取得開始")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
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

        add_log("一覧ページ読み込み中...")

        await page.goto(
            URL,
            wait_until="networkidle",
            timeout=60000
        )

        await page.wait_for_timeout(5000)

        # HTML保存デバッグ
        html = await page.content()

        add_log(f"HTML取得成功: {len(html)}文字")

        # =========================
        # 大会カード取得
        # =========================
        cards = await page.evaluate("""
        () => {

            const links = document.querySelectorAll('a[href*="/competitions/"]');

            return Array.from(links).map(a => {

                const title =
                    a.textContent
                    .replace(/\\s+/g, ' ')
                    .trim();

                const img = a.querySelector('img');

                return {
                    title: title,
                    href: a.href,
                    imgSrc: img ? img.src : ''
                };
            });
        }
        """)

        # 重複削除
        unique_cards = []
        used = set()

        for c in cards:

            if c["href"] in used:
                continue

            used.add(c["href"])
            unique_cards.append(c)

        cards = unique_cards

        add_log(f"取得カード数: {len(cards)}")

        now_jst = datetime.utcnow() + timedelta(hours=9)
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

                add_log(f"確認中: {link}")

                detail_page = await context.new_page()

                await detail_page.goto(
                    link,
                    wait_until="networkidle",
                    timeout=60000
                )

                await detail_page.wait_for_timeout(3000)

                text = await detail_page.locator("body").inner_text()

                # 日付検索
                match = re.search(
                    r"(\\d{4}/\\d{1,2}/\\d{1,2}).*?(\\d{1,2}):(\\d{2})",
                    text
                )

                if not match:

                    add_log("日付取得失敗")
                    await detail_page.close()
                    continue

                date_text = match.group(1)

                hour = int(match.group(2))
                minute = int(match.group(3))

                base_date = datetime.strptime(
                    date_text,
                    "%Y/%m/%d"
                )

                corrected = base_date.replace(
                    hour=hour,
                    minute=minute
                )

                add_log(
                    f"取得日時: {corrected.strftime('%Y/%m/%d %H:%M')}"
                )

                # 当日判定
                if corrected.date() != today:

                    add_log("当日大会ではないためスキップ")

                    await detail_page.close()
                    continue

                weekday = weekdays[corrected.weekday()]

                display_schedule = corrected.strftime(
                    f"%Y/%m/%d({weekday}) %H:%M 〜"
                )

                # タイトル補正
                title = card["title"]

                if len(title) < 3:
                    title = "Tonamel大会"

                tournaments.append({
                    "title": title,
                    "link": link,
                    "image": card["imgSrc"],
                    "schedule": display_schedule,
                    "players": "Tonamel参照",
                    "format": "Tonamel参照"
                })

                add_log(f"取得成功: {title}")

                await detail_page.close()

            except Exception as e:

                add_log(f"大会処理失敗: {str(e)}")

        await browser.close()

    add_log(f"取得大会数: {len(tournaments)}")

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
            add_log(f"削除失敗: {e}")


# =========================
# 起動
# =========================
@bot.event
async def on_ready():

    add_log(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:

        add_log("チャンネル取得失敗")

        await send_logs()
        await bot.close()
        return

    add_log("既存メッセージ削除中...")

    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = (
        datetime.utcnow() + timedelta(hours=9)
    ).strftime("%Y/%m/%d")

    if not tournaments:

        add_log("本日の大会なし")

        await channel.send(
            f"## Shadowverse: World Beyond Tonamel 大会一覧 {today_text}\n"
            f"> 本日の大会はありません。"
        )

        await send_logs()

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

        add_log(f"送信完了: {t['title']}")

    add_log("全大会送信完了")

    await send_logs()

    await bot.close()


bot.run(TOKEN)