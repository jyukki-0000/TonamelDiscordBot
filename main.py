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
                if GRAPHQL_URL in response.url and graphql_data is None:
                    try:
                        body = await response.json()
                        graphql_data = body
                        edges = body.get("data", {}).get("publicCompetitions", {}).get("edges", [])
                        if edges:
                            print("=== 最初のノード全フィールド ===")
                            print(json.dumps(edges[0].get("node", {}), ensure_ascii=False, indent=2))
                            print("=================================")
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

                print(f"node keys: {list(node.keys())}")

                comp_id = node.get("id", "")
                title = node.get("title", "不明")

                entry_count = (
                    node.get("entryCount") or
                    node.get("participantCount") or
                    node.get("currentEntryCount") or
                    node.get("entryNum") or
                    "—"
                )

                organizer_raw = (
                    node.get("organizerName") or
                    node.get("organizer") or
                    node.get("hostName") or
                    node.get("host") or
                    "—"
                )
                if isinstance(organizer_raw, dict):
                    organizer = organizer_raw.get("name", "—")
                else:
                    organizer = str(organizer_raw)

                fmt = (
                    node.get("tournamentFormat") or
                    node.get("format") or
                    node.get("competitionFormat") or
                    "—"
                )

                slug = (
                    node.get("slug") or
                    node.get("competitionId") or
                    comp_id
                )
                comp_url = (
                    node.get("url") or
                    node.get("link") or
                    f"https://tonamel.com/competitions/{slug}"
                )

                tournaments.append({
                    "title": title,
                    "link": comp_url,
                    "players": str(entry_count),
                    "organizer": organizer,
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

    print("既存メッセージを削除中...")
    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = datetime.now().strftime("%Y/%m/%d")

    header = (
        f"## SVWB 大会一覧 ─ {today_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await channel.send(header)

    if not tournaments:
        await channel.send("> 現在取得できる大会情報はありません。")
    else:
        lines = []
        for t in tournaments:
            lines.append(f"- **[{t['title']}]({t['link']})**")
            lines.append(
                f"  参加人数 `{t['players']}` ／ "
                f"主催 `{t['organizer']}` ／ "
                f"形式 `{t['format']}`"
            )
            lines.append("")

        list_message = "\n".join(lines)

        if len(list_message) > 1900:
            list_message = list_message[:1900] + "\n..."

        await channel.send(list_message)

        for t in tournaments:
            embed = discord.Embed(
                title=t["title"],
                url=t["link"],
                color=0x5865F2
            )
            embed.add_field(name="参加人数", value=t["players"], inline=True)
            embed.add_field(name="主催", value=t["organizer"], inline=True)
            embed.add_field(name="トーナメント形式", value=t["format"], inline=False)
            embed.set_footer(text="Tonamel Tournament")
            await channel.send(embed=embed)

    await channel.send("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    print("送信完了")
    await bot.close()


bot.run(TOKEN)