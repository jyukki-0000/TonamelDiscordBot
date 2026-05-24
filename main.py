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


async def get_tournaments():

    tournaments = []

    try:

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
                )
            )

            page = await context.new_page()

            print("一覧ページ読み込み中...")

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            await page.wait_for_timeout(5000)

            await page.wait_for_selector(
                "div.competitions-list ul li",
                timeout=30000
            )

            cards = await page.evaluate("""
                () => {

                    const items = document.querySelectorAll(
                        'div.competitions-list ul li'
                    );

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
                            ? (
                                timeEl.getAttribute('datetime')
                                || timeEl.textContent.trim()
                              )
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

            today_md = datetime.now().strftime("%-m/%-d")

            for card in cards:

                try:

                    link = card["href"]

                    if not link:
                        continue

                    datetime_text = card["datetimeText"]

                    print(f"日時確認: {datetime_text}")

                    # 当日大会のみ
                    if today_md not in datetime_text:
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

                        detail = await detail_page.evaluate("""
() => {

    function findValue(labelText) {

        const items = document.querySelectorAll("dl, div");

        for (const el of items) {

            const text = el.innerText || "";

            if (text.includes(labelText)) {

                const parts = text.split("\\n");

                for (let i = 0; i < parts.length; i++) {

                    if (parts[i].includes(labelText)) {
                        return parts[i + 1] || "—";
                    }
                }
            }
        }

        return "—";
    }

    function getOrganizer() {

        const el = document.querySelector(
            ".organization span"
        );

        return el ? el.textContent.trim() : "—";
    }

    return {

        schedule: findValue("開催時間"),

        format: findValue("大会形式"),

        maxPlayers: findValue("参加上限"),

        organizer: getOrganizer()
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

    except Exception as e:

        print(f"取得エラー: {e}")

        import traceback
        traceback.print_exc()

    print(f"取得大会数: {len(tournaments)}")

    return tournaments


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