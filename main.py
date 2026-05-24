import os
import json
import discord

from discord.ext import commands
from datetime import datetime
from playwright.async_api import async_playwright

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"
GRAPHQL_URL = "https://tonamel.com/graphql/competition_management"

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

            graphql_data = None

            async def handle_response(response):
                nonlocal graphql_data
                if GRAPHQL_URL in response.url:
                    try:
                        body = await response.json()
                        print(f"GraphQL取得成功: {json.dumps(body, ensure_ascii=False)[:300]}")
                        graphql_data = body
                    except Exception as e:
                        print(f"GraphQLパースエラー: {e}")

            page.on("response", handle_response)

            print("ページ読み込み中...")

            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            await page.wait_for_timeout(8000)

            await browser.close()

        if graphql_data:

            edges = (
                graphql_data
                .get("data", {})
                .get("publicCompetitions", {})
                .get("edges", [])
            )

            print(f"エッジ数: {len(edges)}")

            for edge in edges[:10]:

                node = edge.get("node", {})

                comp_id = node.get("id", "")
                title = node.get("title", "不明")
                entry_count = node.get("entryCount") or node.get("participantCount") or "未取得"
                organizer = node.get("organizerName") or node.get("organizer", {}).get("name") or "未取得"
                fmt = node.get("tournamentFormat") or node.get("format") or "未取得"
                url = node.get("url") or f"https://tonamel.com/competitions/{comp_id}"

                tournaments.append({
                    "title": title,
                    "link": url,
                    "players": str(entry_count),
                    "organizer": str(organizer),
                    "format": str(fmt)
                })

        else:
            print("GraphQLデータが取得できませんでした")

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