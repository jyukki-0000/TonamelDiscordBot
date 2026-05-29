import os
import json
import asyncio
import discord

from discord.ext import commands
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

LOG_CHANNEL_ID = 1509705370447118407

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

logs = []


# =========================
# ログ
# =========================
def add_log(message):

    print(message)
    logs.append(message)


async def send_logs():

    channel = bot.get_channel(LOG_CHANNEL_ID)

    if not channel:
        return

    text = "\n".join(logs)

    if len(text) > 1900:
        text = text[-1900:]

    await channel.send(f"```{text}```")


# =========================
# 大会取得
# =========================
async def get_tournaments():

    tournaments = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        page = await browser.new_page()

        add_log("Tonamelページアクセス")

        await page.goto(
            URL,
            wait_until="networkidle",
            timeout=60000
        )

        await page.wait_for_timeout(5000)

        # =========================
        # NEXT_DATA取得
        # =========================
        next_data = await page.locator(
            'script#__NEXT_DATA__'
        ).text_content()

        if not next_data:

            add_log("__NEXT_DATA__取得失敗")

            await browser.close()
            return tournaments

        add_log("__NEXT_DATA__取得成功")

        data = json.loads(next_data)

        await browser.close()

    # =========================
    # 大会一覧取得
    # =========================
    try:

        competitions = (
            data["props"]
            ["pageProps"]
            ["dehydratedState"]
            ["queries"]
        )

    except Exception as e:

        add_log(f"JSON解析失敗: {e}")
        return tournaments

    now_jst = datetime.utcnow() + timedelta(hours=9)
    today = now_jst.date()

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    found = 0

    for query in competitions:

        try:

            state = query.get("state", {})
            query_data = state.get("data", {})

            if not isinstance(query_data, dict):
                continue

            comps = query_data.get("competitions")

            if not comps:
                continue

            for c in comps:

                try:

                    found += 1

                    title = c.get("name", "Tonamel大会")

                    competition_id = c.get("id")

                    if not competition_id:
                        continue

                    url = f"https://tonamel.com/competition/{competition_id}"

                    thumb = ""

                    cover = c.get("coverImage")

                    if cover:
                        thumb = cover.get("url", "")

                    schedule = c.get("schedule", {})

                    start_at = schedule.get("startedAt")

                    if not start_at:
                        continue

                    # UTC → JST
                    dt = datetime.fromisoformat(
                        start_at.replace("Z", "+00:00")
                    ) + timedelta(hours=9)

                    add_log(
                        f"確認: {title} / {dt.strftime('%Y/%m/%d %H:%M')}"
                    )

                    # 今日のみ
                    if dt.date() != today:
                        continue

                    weekday = weekdays[dt.weekday()]

                    display_time = dt.strftime(
                        f"%Y/%m/%d({weekday}) %H:%M 〜"
                    )

                    tournaments.append({
                        "title": title,
                        "link": url,
                        "image": thumb,
                        "schedule": display_time
                    })

                    add_log(f"取得成功: {title}")

                except Exception as e:

                    add_log(f"大会解析失敗: {e}")

        except Exception:
            pass

    add_log(f"一覧検出数: {found}")
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

        except:
            pass


# =========================
# 起動
# =========================
@bot.event
async def on_ready():

    add_log(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:

        add_log("大会チャンネル取得失敗")

        await send_logs()
        await bot.close()
        return

    add_log("既存メッセージ削除")

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

        if t["image"]:
            embed.set_thumbnail(url=t["image"])

        embed.set_footer(text="ShadowverseWB情報収集")

        await channel.send(embed=embed)

    add_log("大会送信完了")

    await send_logs()

    await bot.close()


bot.run(TOKEN)