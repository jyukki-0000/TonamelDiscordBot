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

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        )

        page = await context.new_page()

        print("一覧ページ読み込み中...")

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        await page.wait_for_selector("div.competitions-list ul li", timeout=30000)

        # =========================
        # 一覧取得（安定版）
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

        today = datetime.now().strftime("%Y/%m/%d")

        # =========================
        # 詳細取得
        # =========================
        for card in cards:

            try:

                link = card["href"]
                if not link:
                    continue

                raw_text = card["datetimeText"]

                print(f"日時確認: {raw_text}")

                # =========================
                # 日付抽出（修正ポイント）
                # =========================
                match = re.search(r"\d{4}/\d{1,2}/\d{1,2}", raw_text)

                if not match:
                    continue

                event_date = match.group(0)

                # 正規化
                event_norm = "/".join(str(int(x)) for x in event_date.split("/"))
                today_norm = "/".join(str(int(x)) for x in today.split("/"))

                if event_norm != today_norm:
                    continue

                print(f"本日の大会: {card['title']}")

                detail_page = await context.new_page()

                try:

                    await detail_page.goto(
                        link,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    await detail_page.wait_for_timeout(3000)

                    # =========================
                    # 詳細取得（ラベルベース安定）
                    # =========================
                    detail = await detail_page.evaluate("""
                    () => {

                        function findValue(label) {

                            const nodes = Array.from(
                                document.querySelectorAll("dl, div")
                            );

                            for (const n of nodes) {

                                const text = n.innerText || "";

                                if (text.includes(label)) {

                                    const lines = text.split("\\n");

                                    for (let i = 0; i < lines.length; i++) {

                                        if (lines[i].includes(label)) {
                                            return lines[i + 1] || "—";
                                        }
                                    }
                                }
                            }

                            return "—";
                        }

                        const org = document.querySelector(".organization span");

                        return {

                            schedule: findValue("開催時間"),
                            format: findValue("大会形式"),
                            maxPlayers: findValue("参加上限"),
                            organizer: org ? org.textContent.trim() : "—"
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

                except Exception as e:
                    print(f"詳細取得失敗: {e}")

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

    deleted = 0

    async for message in channel.history(limit=100):

        try:
            await message.delete()
            deleted += 1
            await asyncio.sleep(1)

        except Exception as e:
            print(f"削除エラー: {e}")

    print(f"削除完了: {deleted}件")


# =========================
# 起動処理
# =========================
@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if channel is None:
        print("チャンネル取得失敗")
        await bot.close()
        return

    print("既存メッセージ削除中...")
    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = datetime.now().strftime("%Y/%m/%d")

    # =========================
    # 送信処理
    # =========================
    if not tournaments:

        await channel.send(
            f"## SVWB 大会一覧 ─ {today_text}\n"
            f"> 本日の大会はありません。"
        )

    else:

        await channel.send(
            f"## SVWB 大会一覧 ─ {today_text}"
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
                name="主催",
                value=t["organizer"],
                inline=True
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

            embed.set_footer(
                text="ShadowverseWB情報収集"
            )

            await channel.send(embed=embed)

    print("送信完了")
    await bot.close()


bot.run(TOKEN)