import os
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

            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            )

            page = await context.new_page()

            print("一覧ページ読み込み中...")

            await page.goto(URL, wait_until="networkidle")

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

                        const titleEl = li.querySelector('h3');
                        const title = titleEl
                            ? titleEl.textContent.trim()
                            : '不明';

                        const timeEl = li.querySelector('time');

                        const datetimeText = timeEl
                            ? (
                                timeEl.getAttribute('datetime')
                                || timeEl.textContent.trim()
                              )
                            : '';

                        return {
                            title,
                            href,
                            imgSrc,
                            datetimeText
                        };
                    });
                }
            """)

            today = datetime.now().strftime("%Y-%m-%d")

            for card in cards:

                link = card["href"]

                if not link:
                    continue

                datetime_text = card["datetimeText"]

                # 当日大会のみ
                if today not in datetime_text:
                    continue

                print(f"詳細取得: {card['title']}")

                detail_page = await context.new_page()

                try:

                    await detail_page.goto(
                        link,
                        wait_until="networkidle",
                        timeout=60000
                    )

                    detail = await detail_page.evaluate("""
                        () => {

                            function getText(selector) {
                                const el = document.querySelector(selector);
                                return el
                                    ? el.textContent.trim()
                                    : "—";
                            }

                            return {

                                schedule: getText(
                                    "#__layout > div > div.competition-detail > div.competition-detail > div.main > div.detail > div.competition-detail-info.section > div:nth-child(1) > dl > dd:nth-child(2) > span"
                                ),

                                organizer: getText(
                                    "#__layout > div > div.competition-detail > div.competition-detail > div.main > div.detail > div.a-box.competition-card.m-competition-card.a-box--no-radius.a-box--white > div.inner > div.a-flex.organization.a-flex--flex-start.a-flex--row > a > div > span"
                                ),

                                maxPlayers: getText(
                                    "#__layout > div > div.competition-detail > div.competition-detail > div.main > div.detail > div.competition-detail-info.section > div:nth-child(1) > dl > dd:nth-child(6) > span"
                                ),

                                format: getText(
                                    "#__layout > div > div.competition-detail > div.competition-detail > div.main > div.detail > div.competition-detail-info.section > div:nth-child(1) > dl > dd:nth-child(4) > span"
                                )
                            };
                        }
                    """)

                    # 現在人数取得
                    current_players = await detail_page.evaluate("""
                        () => {

                            const text = document.body.innerText;

                            const match = text.match(/(\\d+)\\s*\\/\\s*(\\d+)/);

                            if (!match) return "—";

                            return match[1];
                        }
                    """)

                    max_players = detail["maxPlayers"]

                    tournaments.append({
                        "title": card["title"],
                        "link": link,
                        "image": card["imgSrc"],
                        "schedule": detail["schedule"],
                        "organizer": detail["organizer"],
                        "players": f"{current_players}/{max_players}",
                        "format": detail["format"]
                    })

                except Exception as e:
                    print(f"詳細取得失敗: {e}")

                finally:
                    await detail_page.close()

            await browser.close()

    except Exception as e:
        print(f"取得エラー: {e}")
        import traceback
        traceback.print_exc()

    print(f"取得大会数: {len(tournaments)}")

    return tournaments


async def purge_channel(channel):

    deleted = 0

    async for message in channel.history(limit=None):
        try:
            await message.delete()
            deleted += 1
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
                color=0x5865F2
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
                name="参加人数",
                value=t["players"],
                inline=True
            )

            embed.add_field(
                name="大会形式",
                value=t["format"],
                inline=True
            )

            if t["image"]:
                embed.set_image(url=t["image"])

            embed.set_footer(text="Tonamel")

            await channel.send(embed=embed)

    print("送信完了")

    await bot.close()


bot.run(TOKEN)