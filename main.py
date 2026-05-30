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
    return datetime.now(JST).date()


async def send_logs():
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    text = "\n".join(logs)
    while text:
        await channel.send(f"```{text[:1900]}```")
        text = text[1900:]


async def fetch_detail(context, competition_id):
    """
    各大会ページから「時刻」と「トーナメント形式」を取得する。
    当日大会のみ呼ばれるため件数は少ない。
    失敗時は (None, None) を返す。
    """
    url = f"https://tonamel.com/competition/{competition_id}"
    for attempt in range(1, 4):
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(3000)
            text = await page.locator("body").inner_text()
            html = await page.content()
            await page.close()

            # 時刻: 一覧にある日付の直後に "HH:MM" が続くパターン
            time_match = re.search(
                r'20\d{2}/\d{1,2}/\d{1,2}[^\d]*?(\d{1,2}:\d{2})', text
            )
            start_time = time_match.group(1) if time_match else None

            # トーナメント形式: "シングルエリミネーション" "ダブルエリミネーション"
            # "スイス式" "総当たり" 等をテキストから探す
            format_match = re.search(
                r'(シングルエリミネーション|ダブルエリミネーション|スイス式|総当たり|リーグ戦|Swiss)',
                text
            )
            tournament_format = format_match.group(1) if format_match else None

            return start_time, tournament_format

        except Exception as e:
            await page.close()
            add_log(f"詳細取得失敗 試行{attempt}/3: {competition_id} - {e}")
            if attempt < 3:
                await asyncio.sleep(3)

    return None, None


async def get_tournaments(today):
    tournaments = []

    # ---- 大会一覧ページ取得 ----
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()
        add_log("Tonamelアクセス")

        try:
            await page.goto(URL, wait_until="networkidle", timeout=90000)
        except Exception:
            add_log("networkidle タイムアウト、取得を続行")

        await page.wait_for_timeout(3000)
        html = await page.content()
        await browser.close()

    add_log(f"HTML取得: {len(html)}文字")

    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.list-item")
    add_log(f"検出大会数: {len(items)}")

    if not items:
        add_log("大会リストが取得できませんでした")
        return tournaments

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    # 一覧から当日大会を抽出
    today_items = []
    for item in items:
        try:
            a_tag = item.select_one('a[href^="/competition/"]')
            if not a_tag:
                continue
            competition_id = a_tag["href"].split("/")[-1]
            link = f"https://tonamel.com{a_tag['href']}"

            title_tag = item.select_one("span.title")
            title = title_tag.get_text(strip=True) if title_tag else "Tonamel大会"

            # 画像URL
            img_tag = item.select_one("div.widescreen img")
            image_url = None
            if img_tag and img_tag.get("src"):
                src = img_tag["src"]
                image_url = f"https:{src}" if src.startswith("//") else src

            # 参加人数上限: "2/64" -> "64"
            capacity = None
            spans = item.select("div.competition-items div.competition-data span")
            for span in spans:
                t = span.get_text(strip=True)
                m = re.match(r'^\d+/(\d+)$', t)
                if m:
                    capacity = m.group(1)
                    break

            # 日付
            date_text = None
            for span in spans:
                t = span.get_text(strip=True)
                m = re.match(r'(20\d{2}/\d{1,2}/\d{1,2})', t)
                if m:
                    date_text = m.group(1)
                    break

            if not date_text:
                add_log(f"日付取得失敗: {competition_id} ({title})")
                continue

            dt_date = datetime.strptime(date_text, "%Y/%m/%d").date()

            add_log(f"確認中: {competition_id} / {date_text} / {title}")

            if dt_date == today:
                today_items.append({
                    "id": competition_id,
                    "link": link,
                    "title": title,
                    "image_url": image_url,
                    "capacity": capacity,
                    "date": dt_date,
                })
                add_log(f"当日大会: {title}")
            elif dt_date > today:
                # 未来の大会が出た時点で中断
                add_log(f"未来の大会を検出、処理を中断: {competition_id} ({date_text})")
                break
            else:
                add_log(f"過去の大会のためスキップ: {date_text}")

        except Exception as e:
            add_log(f"パース失敗: {e}")

    add_log(f"当日大会数: {len(today_items)}")

    if not today_items:
        return tournaments

    # ---- 当日大会のみ詳細ページにアクセスして時刻・形式を取得 ----
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context()

        for t_item in today_items:
            add_log(f"詳細取得: {t_item['id']}")
            start_time, tournament_format = await fetch_detail(context, t_item["id"])

            weekday = weekdays[t_item["date"].weekday()]
            date_str = t_item["date"].strftime(f"%Y/%m/%d({weekday})")
            schedule = f"{date_str} {start_time} ～" if start_time else date_str

            tournaments.append({
                "title": t_item["title"],
                "link": t_item["link"],
                "image_url": t_item["image_url"],
                "schedule": schedule,
                "capacity": t_item["capacity"],
                "format": tournament_format,
            })
            add_log(f"取得成功: {t_item['title']} / {schedule} / 形式:{tournament_format} / 上限:{t_item['capacity']}")

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
        embed.add_field(name="開催日時", value=t["schedule"], inline=False)

        if t["format"]:
            embed.add_field(name="形式", value=t["format"], inline=True)

        if t["capacity"]:
            embed.add_field(name="参加人数上限", value=f"{t['capacity']}人", inline=True)

        if t["image_url"]:
            embed.set_image(url=t["image_url"])

        embed.set_footer(text="ShadowverseWB情報収集")
        await channel.send(embed=embed)

    add_log("大会送信完了")
    await send_logs()
    await bot.close()


bot.run(TOKEN)
