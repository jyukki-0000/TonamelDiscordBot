import os
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

        await page.goto(URL, wait_until="networkidle", timeout=120000)
        await page.wait_for_selector("div.competitions-list ul li", timeout=30000)

        # =========================
        # 一覧取得（リンクだけ）
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

                detail_page = await context.new_page()

                try:

                    await detail_page.goto(link, wait_until="networkidle", timeout=120000)

                    # =========================
                    # 詳細データ取得（正しい日付span使用）
                    # =========================
                    detail = await detail_page.evaluate("""
                    () => {

                        function get(xpath) {
                            try {
                                const res = document.evaluate(
                                    xpath,
                                    document,
                                    null,
                                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                                    null
                                );

                                const node = res.singleNodeValue;
                                return node ? node.textContent.trim() : "—";

                            } catch (e) {
                                return "—";
                            }
                        }

                        return {

                            // 🔥 あなたが提示した正しい日付
                            schedule: get(
                                '//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[3]/div[1]/dl/dd[1]/span'
                            ),

                            format: get(
                                '//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[3]/div[1]/dl/dd[2]/span'
                            ),

                            maxPlayers: get(
                                '//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[3]/div[1]/dl/dd[3]/span'
                            )
                        };
                    }
                    """)

                    # =========================
                    # 日付判定（ここが唯一の正解）
                    # =========================
                    import re

                    match = re.search(r"\d{4}/\d{1,2}/\d{1,2}", detail["schedule"])

                    if not match:
                        continue

                    event_date = datetime.strptime(match.group(0), "%Y/%m/%d").date()

                    if event_date != today:
                        continue

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
# メッセージ削除
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