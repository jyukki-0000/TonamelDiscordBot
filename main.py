import os
import re
import asyncio
import discord
import pytz

from discord.ext import commands
from datetime import datetime
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


def get_today_jst() -> datetime.date:
    """日本時間（JST）での今日の日付を返す"""
    return datetime.now(JST).date()


async def send_logs():
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    text = "\n".join(logs)
    if len(text) > 1900:
        text = text[-1900:]

    await channel.send(f"```{text}```")


async def fetch_page_with_retry(context, url, retries=3):
    """
    ページ取得をリトライ付きで行う。
    成功時は (text, html) を返す。失敗時は (None, None) を返す。
    """
    for attempt in range(1, retries + 1):
        page = await context.new_page()
        try:
            # domcontentloaded で待機（networkidle はSPAで詰まりやすいため変更）
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)

            text = await page.locator("body").inner_text()
            html = await page.content()
            await page.close()
            return text, html

        except Exception as e:
            await page.close()
            add_log(f"取得失敗 (試行 {attempt}/{retries}): {e}")
            if attempt < retries:
                await asyncio.sleep(3)

    return None, None


async def get_tournaments(today):
    """
    today: date オブジェクト（JST）
    当日大会リストを返す。
    """
    tournaments = []

    # ---- 大会一覧ページの取得 ----
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()
        add_log("Tonamelアクセス")

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
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

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    date_patterns = [
        r'(20\d{2}/\d{1,2}/\d{1,2}).{0,50}?(\d{1,2}:\d{2})',
        r'(20\d{2}-\d{1,2}-\d{1,2}).{0,50}?(\d{1,2}:\d{2})',
    ]

    # ---- 各大会ページの確認 ----
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

                text, html = await fetch_page_with_retry(context, link, retries=3)

                if text is None:
                    # リトライ全滅 → この大会はスキップして次へ（中断しない）
                    add_log(f"取得失敗のためスキップ: {competition_id}")
                    continue

                # タイトル取得
                title = "Tonamel大会"
                title_match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
                if title_match:
                    title = title_match.group(1).replace("| Tonamel", "").strip()

                # 日時取得（テキスト → HTML の順）
                date_match = None
                for pattern in date_patterns:
                    date_match = re.search(pattern, text, re.DOTALL)
                    if date_match:
                        break
                if not date_match:
                    for pattern in date_patterns:
                        date_match = re.search(pattern, html, re.DOTALL)
                        if date_match:
                            break

                if not date_match:
                    add_log(f"日時取得失敗: {competition_id}")
                    continue

                date_text = date_match.group(1).replace("-", "/")
                time_text = date_match.group(2)

                add_log(f"取得日付文字列: {date_text}")
                add_log(f"取得時刻文字列: {time_text}")

                dt = datetime.strptime(f"{date_text} {time_text}", "%Y/%m/%d %H:%M")
                add_log(f"取得日時: {dt.strftime('%Y/%m/%d %H:%M')}")

                competition_date = dt.date()

                if competition_date < today:
                    add_log("過去の大会のためスキップ")
                    continue

                if competition_date == today:
                    weekday = weekdays[dt.weekday()]
                    tournaments.append({
                        "title": title,
                        "link": link,
                        "schedule": dt.strftime(f"%Y/%m/%d({weekday}) %H:%M ～")
                    })
                    add_log(f"取得成功: {title}")
                    continue

                # competition_date > today（未来）
                # タイムアウト等で当日大会を取りこぼしている可能性があるため
                # 未来大会が出ても即中断せず、全件スキャンする
                add_log("当日大会ではない")

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

    # JST で今日の日付を確定（以降すべてこの値を使う）
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