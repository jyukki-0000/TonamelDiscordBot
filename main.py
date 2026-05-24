import os
import re
import asyncio
import discord

from discord.ext import commands
from datetime import datetime
from playwright.async_api import async_playwright

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# 大会取得
# =========================
async def get_tournaments():

    tournaments = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context()
        page = await context.new_page()

        print("一覧ページ読み込み中...")

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(7000)
        await page.wait_for_selector("div.competitions-list ul li", timeout=30000)

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

                // ⚠ datetime属性・timeタグは使わない（ズレ原因）
                const timeSpan =
                    li.querySelector('span.a-text--medium') ||
                    li.querySelector('time') ||
                    li.querySelector('span');

                const datetimeText = timeSpan
                    ? timeSpan.textContent.trim()
                    : li.textContent;

                return {
                    title,
                    href,
                    imgSrc,
                    datetimeText
                };
            });
        }
        """)

        print(f"取得カード数: {len(cards)}")

        today = datetime.now().date()

        # =========================
        # 詳細取得
        # =========================
        for card in cards:

            try:

                link = card["href"]
                if not link:
                    continue

                raw_text = card["datetimeText"]

                match = re.search(r"\d{4}/\d{1,2}/\d{1,2}", raw_text)
                if not match:
                    continue

                try:
                    event_date = datetime.strptime(match.group(0), "%Y/%m/%d").date()
                except:
                    continue

                if event_date != today:
                    continue

                print(f"本日の大会: {card['title']}")

                detail_page = await context.new_page()

                try:

                    await detail_page.goto(link, wait_until="domcontentloaded", timeout=60000)
                    await detail_page.wait_for_timeout(5000)

                    # =========================
                    # 詳細取得（時間はそのまま）
                    # =========================
                    detail = await detail_page.evaluate("""
                    () => {

                        function get(xpaths) {

                            for (const xpath of xpaths) {

                                try {
                                    const res = document.evaluate(
                                        xpath,
                                        document,
                                        null,
                                        XPathResult.FIRST_ORDERED_NODE_TYPE,
                                        null
                                    );

                                    const node = res.singleNodeValue;

                                    if (node && node.textContent.trim()) {
                                        return node.textContent.trim();
                                    }

                                } catch (e) {}
                            }

                            return "—";
                        }

                        return {

                            // 🔥 正しい時間（変換禁止・表示そのまま）
                            schedule: get([
                                '//*[@id="__layout"]//div[contains(@class,"competition-detail")]//dl/dd[1]/span',
                                '//*[@id="__layout"]//dl/dd[1]/span'
                            ]),

                            format: get([
                                '//*[@id="__layout"]//dl/dd[2]/span'
                            ]),

                            maxPlayers: get([
                                '//*[@id="__layout"]//dl/dd[3]/span'
                            ])
                        };
                    }
                    """)

                    tournaments.append({
                        "title": card["title"],
                        "link": link,
                        "image": card["imgSrc"],
                        "schedule": detail["schedule"],
                        "players": detail["maxPlayers"],
                        "format": detail["format"]
                    })

                    print(f"取得成功: {card['title']}")

                finally:
                    await detail_page.close()

            except Exception as e:
                print(f"大会処理失敗: {e}")

        await browser.close()

    print(f"取得大会数: {len(tournaments)}")
    return tournaments


# =========================
# 削除処理
# =========================
async def purge_channel(channel):

    async for msg in channel.history(limit=100):
        try:
            await msg.delete()
            await asyncio.sleep(1)
        except:
            pass


# =========================
# 起動
# =========================
@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:
        print("チャンネル取得失敗")
        await bot.close()
        return

    print("既存メッセージ削除中...")
    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = datetime.now().strftime("%Y/%m/%d")

    if not tournaments:

        await channel.send(
            f"## SVWB 大会一覧 ─ {today_text}\n"
            f"> 本日の大会はありません。"
        )
        return

    await channel.send(f"## SVWB 大会一覧 ─ {today_text}")

    for t in tournaments:

        embed = discord.Embed(
            title=t["title"],
            url=t["link"],
            color=0xee4235
        )

        embed.add_field(name="開催時間", value=t["schedule"], inline=False)
        embed.add_field(name="参加上限", value=t["players"], inline=True)
        embed.add_field(name="大会形式", value=t["format"], inline=True)

        if t["image"]:
            embed.set_thumbnail(url=t["image"])

        embed.set_footer(text="ShadowverseWB情報収集")

        await channel.send(embed=embed)

    print("送信完了")
    await bot.close()


bot.run(TOKEN)