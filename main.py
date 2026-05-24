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
# データ取得
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

                const timeEl = li.querySelector('time');

                const datetimeText = timeEl
                    ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim())
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

                detail_page = await context.new_page()

                try:

                    await detail_page.goto(link, wait_until="domcontentloaded", timeout=60000)
                    await detail_page.wait_for_timeout(4000)

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

                            schedule: get('//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[3]/div[1]/dl/dd[1]/span'),

                            format: get('//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[3]/div[1]/dl/dd[2]/span'),

                            maxPlayers: get('//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[3]/div[1]/dl/dd[3]/span'),

                            organizer: (() => {
                                const el = document.querySelector(
                                    '//*[@id="__layout"]/div/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[1]/a/div/span'
                                );
                                return el ? el.textContent.trim() : "—";
                            })()
                        };
                    }
                    """)

                    tournaments.append({
                        "title": card["title"],
                        "link": link,
                        "image": card["imgSrc"],
                        "schedule": detail["schedule"],
                        "organizer": detail["organizer"],
                        "players": detail["maxPlayers"],
                        "format": detail["format"]
                    })

                    print(f"取得成功: {card['title']}")

                finally:
                    await detail_page.close()

            except Exception as e:
                print(f"大会処理失敗: {e}")

        await browser.close()

    return tournaments


# =========================
# 削除
# =========================
async def purge_channel(channel):

    async for msg in channel.history(limit=100):
        try:
            await msg.delete()
            await asyncio.sleep(1)
        except:
            pass


# =========================
# UI（Webカード風）
# =========================
def create_web_embed(t):

    embed = discord.Embed(
        title=f"🎮 {t['title']}",
        url=t["link"],
        color=0xee4235,
        description=(
            f"📅 **開催時間**: {t['schedule']}\n"
            f"🏆 **形式**: {t['format']}\n"
            f"👥 **参加上限**: {t['players']}\n"
            f"🏢 **主催**: {t['organizer']}\n"
        )
    )

    if t["image"]:
        embed.set_thumbnail(url=t["image"])

    embed.add_field(
        name="🔗 詳細リンク",
        value=f"[大会ページを開く]({t['link']})",
        inline=False
    )

    embed.add_field(
        name="🌐 コミュニティ",
        value="[ShadowverseWB情報収集](https://discord.com/invite/gCVcg8JtR6)",
        inline=False
    )

    embed.set_footer(text="Tonamel Tournament Viewer")

    return embed


# =========================
# 起動
# =========================
@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:
        return

    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = datetime.now().strftime("%Y/%m/%d")

    if not tournaments:

        await channel.send(
            f"## 🎯 SVWB Tournament Dashboard ─ {today_text}\n"
            "> 本日の大会はありません"
        )
        return

    await channel.send(f"## 🎯 SVWB Tournament Dashboard ─ {today_text}")

    for t in tournaments:
        embed = create_web_embed(t)
        await channel.send(embed=embed)

    print("送信完了")
    await bot.close()


bot.run(TOKEN)