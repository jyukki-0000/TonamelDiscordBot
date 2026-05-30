import os
import re
import asyncio
import discord
import pytz

from discord.ext import commands
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

LOG_CHANNEL_ID = 1509705370447118407

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

JST = pytz.timezone("Asia/Tokyo")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

logs = []


def add_log(message):
    print(message)
    logs.append(message)


def get_today_jst():
    """日本時間（JST）での今日の日付を返す"""
    return datetime.now(JST).date()


async def send_logs():
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    text = "\n".join(logs)
    # 1900文字超えたら複数に分割して送信
    while text:
        await channel.send(f"```{text[:1900]}```")
        text = text[1900:]


async def get_tournaments(today):
    """
    大会一覧ページのHTMLから直接、当日開催の大会を取得する。
    各大会ページへの個別アクセスは不要。
    """
    tournaments = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()

        add_log("Tonamelアクセス")

        # networkidle で待機（SPAのレンダリング完了を待つ）
        try:
            await page.goto(URL, wait_until="networkidle", timeout=90000)
        except Exception:
            # タイムアウトしても取得を試みる
            add_log("networkidle タイムアウト、取得を続行")

        await page.wait_for_timeout(3000)

        html = await page.content()
        await browser.close()

    add_log(f"HTML取得: {len(html)}文字")

    soup = BeautifulSoup(html, "html.parser")

    # 大会カード: <li class="list-item"> の中に <a href="/competition/ID"> がある
    items = soup.select("li.list-item")
    add_log(f"検出大会数: {len(items)}")

    if not items:
        add_log("大会リストが取得できませんでした（レンダリング未完了の可能性あり）")
        return tournaments

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    for item in items:
        try:
            # ID・リンク取得
            a_tag = item.select_one('a[href^="/competition/"]')
            if not a_tag:
                continue
            href = a_tag["href"]  # 例: /competition/ft50T
            competition_id = href.split("/")[-1]
            link = f"https://tonamel.com{href}"

            # タイトル取得: class に "title" を含む span
            title_tag = item.select_one("span.title")
            title = title_tag.get_text(strip=True) if title_tag else "Tonamel大会"

            # 日付取得: "2026/05/30(土)" 形式のテキストを持つ span を探す
            date_text = None
            for span in item.select("span"):
                text = span.get_text(strip=True)
                m = re.match(r"(20\d{2}/\d{1,2}/\d{1,2})", text)
                if m:
                    date_text = m.group(1)
                    break

            if not date_text:
                add_log(f"日付取得失敗: {competition_id} ({title})")
                continue

            add_log(f"確認中: {competition_id} / {date_text} / {title}")

            dt_date = datetime.strptime(date_text, "%Y/%m/%d").date()

            if dt_date != today:
                add_log(f"当日大会ではない ({date_text})")
                continue

            # 時刻は一覧ページに含まれないため、開催時刻は「-」で表示
            weekday = weekdays[dt_date.weekday()]
            tournaments.append({
                "title": title,
                "link": link,
                "schedule": dt_date.strftime(f"%Y/%m/%d({weekday})")
            })
            add_log(f"取得成功: {title}")

        except Exception as e:
            add_log(f"パース失敗: {e}")

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

    today = get_today_jst()
    today_text = today.strftime("%Y/%m/%d")
    add_log(f"実行日（JST）: {today_text}")

    add_log("既存メッセージ削除")
    await purge_channel(channel)

    tournaments = await get_tournaments(today)

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
            name="開催日",
            value=t["schedule"],
            inline=False
        )
        embed.set_footer(text="ShadowverseWB情報収集")
        await channel.send(embed=embed)

    add_log("大会送信完了")
    await send_logs()
    await bot.close()


bot.run(TOKEN)