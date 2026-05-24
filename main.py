import os
import asyncio
import json
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
    captured_responses = []

    try:

        async with async_playwright() as p:

            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )

            page = await context.new_page()

            async def handle_response(response):
                url = response.url
                if (
                    "firestore" in url or
                    "firebase" in url or
                    "tonamel" in url and (
                        "competition" in url or
                        "tournament" in url or
                        "api" in url
                    )
                ):
                    try:
                        body = await response.text()
                        if "competition" in body.lower() and len(body) > 100:
                            captured_responses.append({
                                "url": url,
                                "body": body[:2000]
                            })
                            print(f"キャプチャ: {url[:100]}")
                    except Exception:
                        pass

            page.on("response", handle_response)

            print("ページ読み込み中...")

            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            await page.wait_for_timeout(8000)

            print(f"キャプチャしたレスポンス数: {len(captured_responses)}")

            for r in captured_responses:
                print(f"URL: {r['url'][:80]}")
                print(f"Body: {r['body'][:200]}")
                print("---")

            links = await page.eval_on_selector_all(
                "a[href*='/competitions/']",
                "els => els.map(el => ({href: el.href, text: el.innerText.trim()}))"
            )

            print(f"取得リンク数: {len(links)}")

            checked = set()

            for link in links:
                href = link.get("href", "")
                text = link.get("text", "").strip()

                if not href or href in checked:
                    continue

                if "/competitions/" not in href:
                    continue

                slug = href.rstrip("/").split("/")[-1]

                if not slug or slug == "competitions":
                    continue

                if "?" in slug:
                    continue

                checked.add(href)

                title = text if text else slug.replace("-", " ")

                if not title or len(title.strip()) == 0:
                    title = slug.replace("-", " ")

                tournaments.append({
                    "title": title[:100],
                    "link": href,
                    "players": "未取得",
                    "organizer": "Tonamel",
                    "format": "未取得"
                })

                if len(tournaments) >= 10:
                    break

            await browser.close()

    except Exception as e:
        print(f"取得エラー: {e}")
        import traceback
        traceback.print_exc()

    print(f"取得大会数: {len(tournaments)}")

    return tournaments


@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if channel is None:
        print("チャンネル取得失敗")
        await bot.close()
        return

    tournaments = await get_tournaments()

    today_text = datetime.now().strftime("%Y/%m/%d")

    message = f"## 【{today_text} SVWB 大会一覧】\n\n"

    if not tournaments:
        message += "現在取得できる大会がありません。"
    else:
        for i, t in enumerate(tournaments, start=1):
            message += (
                f"{i}️⃣ [{t['title']}]({t['link']})\n"
                f"参加人数: {t['players']}\n"
                f"主催: {t['organizer']}\n\n"
            )

    await channel.send(message)

    for t in tournaments:

        embed = discord.Embed(
            title=t["title"],
            url=t["link"],
            color=discord.Color.blue()
        )

        embed.add_field(name="参加人数", value=t["players"], inline=True)
        embed.add_field(name="主催", value=t["organizer"], inline=True)
        embed.add_field(name="トーナメント形式", value=t["format"], inline=False)
        embed.set_footer(text="Tonamel Tournament")

        await channel.send(embed=embed)

    print("送信完了")

    await bot.close()


bot.run(TOKEN)