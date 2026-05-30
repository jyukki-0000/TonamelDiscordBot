import os
import re
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
bot = commands.Bot(command_prefix="!", intents=intents)

logs = []


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


async def get_tournaments():
    tournaments = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        page = await browser.new_page()

        add_log("Tonamelアクセス")

        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        html = await page.content()

        add_log(f"HTML取得: {len(html)}文字")

        await browser.close()

    matches = re.findall(r'/competition/([A-Za-z0-9]+)', html)

    unique_ids = []
    for m in matches:
        if m != "index" and m not in unique_ids:
            unique_ids.append(m)

    add_log(f"検出大会数: {len(unique_ids)}")

    now_jst = datetime.utcnow() + timedelta(hours=9)
    today = now_jst.date()

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context()

        for competition_id in unique_ids[:20]:
            try:
                link = f"https://tonamel.com/competition/{competition_id}"

                add_log(f"確認中: {competition_id}")

                page = await context.new_page()
                await page.goto(link, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(2000)

                text = await page.locator("body").inner_text()
                html = await page.content()

                title = "Tonamel大会"
                title_match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
                if title_match:
                    title = title_match.group(1).replace("| Tonamel", "").strip()

                # 修正点:
                # 元コードは \\d を使っていたため日時が取得できなかった
                patterns = [
                    r'(20\d{2}/\d{1,2}/\d{1,2}).{0,50}?(\d{1,2}:\d{2})',
                    r'(20\d{2}-\d{1,2}-\d{1,2}).{0,50}?(\d{1,2}:\d{2})',
                ]

                date_match = None

                for pattern in patterns:
                    date_match = re.search(pattern, text, re.DOTALL)
                    if date_match:
                        break

                if not date_match:
                    for pattern in patterns:
                        date_match = re.search(pattern, html, re.DOTALL)
                        if date_match:
                            break

                if not date_match:
                    add_log(f"日時取得失敗: {competition_id}")
                    await page.close()
                    continue

                date_text = date_match.group(1).replace("-", "/")
                time_text = date_match.group(2)

add_log(f"取得日付文字列: {date_text}")
add_log(f"取得時刻文字列: {time_text}")
                dt = datetime.strptime(
                    f"{date_text} {time_text}",
                    "%Y/%m/%d %H:%M"
                )

                add_log(f"取得日時: {dt.strftime('%Y/%m/%d %H:%M')}")

                if dt.date() != today:
                    add_log("当日大会ではない")
                    await page.close()
                    continue

                weekday = weekdays[dt.weekday()]

                tournaments.append({
                    "title": title,
                    "link": link,
                    "schedule": dt.strftime(f"%Y/%m/%d({weekday}) %H:%M ～")
                })

                add_log(f"取得成功: {title}")
                await page.close()

            except Exception as e:
                add_log(f"大会取得失敗 {competition_id}: {e}")

        await browser.close()

    add_log(f"最終取得数: {len(tournaments)}")
    return tournaments


async def purge_channel(channel):
    async for msg in channel.history(limit=100):
        try:
            await msg.delete()
            await asyncio.sleep(0.3)
        except Exception:
            pass


@bot.event
async def on_ready():
    add_log(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:
        add_log("チャンネル取得失敗")
        await send_logs()
        await bot.close()
        return

    add_log("既存メッセージ削除")
    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y/%m/%d")

    if not tournaments:
        add_log("本日の大会なし")

        await channel.send(
            f"## Shadowverse: Worlds Beyond Tonamel 大会一覧 {today_text}\n"
            f"> 本日の大会はありません。"
        )

        await send_logs()
        await bot.close()
        return

    await channel.send(
        f"## Shadowverse: Worlds Beyond Tonamel 大会一覧 {today_text}"
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

        embed.set_footer(text="ShadowverseWB情報収集")

        await channel.send(embed=embed)

    add_log("大会送信完了")

    await send_logs()
    await bot.close()


bot.run(TOKEN)
