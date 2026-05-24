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

            graphql_responses = []

            async def handle_response(response):
                if GRAPHQL_URL in response.url:
                    try:
                        body = await response.json()
                        edges = (
                            body.get("data", {})
                            .get("publicCompetitions", {})
                            .get("edges", [])
                        )
                        print(f"GraphQL受信: edges={len(edges)}")
                        if edges:
                            graphql_responses.append(body)
                    except Exception as e:
                        print(f"GraphQL解析エラー: {e}")

            page.on("response", handle_response)

            print("ページ読み込み中...")

            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            for _ in range(20):
                if graphql_responses:
                    break
                await page.wait_for_timeout(1000)

            if not graphql_responses:
                print("GraphQLデータなし")
                await browser.close()
                return tournaments

            try:
                await page.wait_for_selector(
                    "div.competitions-list ul li",
                    timeout=10000
                )
            except Exception:
                print("li セレクター待機タイムアウト（続行）")

            cards = await page.evaluate("""
                () => {
                    const items = document.querySelectorAll(
                        'div.competitions-list ul li'
                    );
                    return Array.from(items).slice(0, 10).map(li => {
                        const a = li.querySelector('a[href]');
                        const href = a ? a.href : '';

                        const img = li.querySelector('img');
                        const imgSrc = img ? img.src : '';

                        const allText = Array.from(li.querySelectorAll('*'))
                            .filter(el => el.children.length === 0 && el.textContent.trim())
                            .map(el => ({
                                tag: el.tagName,
                                cls: el.className,
                                text: el.textContent.trim()
                            }));

                        const timeEl = li.querySelector('time');
                        const timeAttr = timeEl
                            ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim())
                            : '';

                        return { href, imgSrc, timeAttr, allText };
                    });
                }
            """)

            print(f"DOMカード数: {len(cards)}")
            if cards:
                print("=== カード0 全テキスト要素 ===")
                print(json.dumps(cards[0], ensure_ascii=False, indent=2))
                print("==============================")

            edges = (
                graphql_responses[-1]
                .get("data", {})
                .get("publicCompetitions", {})
                .get("edges", [])
            )

            for i, edge in enumerate(edges[:10]):
                node = edge.get("node", {})
                card = cards[i] if i < len(cards) else {}

                comp_id = node.get("id", "")
                title = node.get("title", "不明")

                slug = node.get("slug") or node.get("competitionId") or comp_id
                comp_url = card.get("href") or f"https://tonamel.com/competition/{slug}"

                image_url = card.get("imgSrc") or None

                schedule = card.get("timeAttr") or "—"

                all_text = card.get("allText", [])
                print(f"[{title}] テキスト要素数: {len(all_text)}")
                for t in all_text:
                    print(f"  {t['tag']} cls={t['cls']!r} -> {t['text']!r}")

                entry_count = (
                    node.get("entryCount") or
                    node.get("participantCount") or
                    node.get("currentEntryCount") or
                    "—"
                )

                organizer_raw = (
                    node.get("organizerName") or
                    node.get("organizer") or
                    node.get("hostName") or
                    node.get("owner") or
                    node.get("creator") or
                    "—"
                )
                organizer = (
                    organizer_raw.get("name") or organizer_raw.get("displayName") or "—"
                    if isinstance(organizer_raw, dict)
                    else str(organizer_raw)
                )

                fmt = (
                    node.get("tournamentFormat") or
                    node.get("format") or
                    node.get("competitionFormat") or
                    "—"
                )

                tournaments.append({
                    "title": title,
                    "link": comp_url,
                    "players": str(entry_count),
                    "organizer": organizer,
                    "format": str(fmt),
                    "image": image_url,
                    "schedule": schedule,
                })

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

    print("既存メッセージを削除中...")
    await purge_channel(channel)

    tournaments = await get_tournaments()

    today_text = datetime.now().strftime("%Y/%m/%d")

    if not tournaments:
        await channel.send(
            f"## SVWB 大会一覧 ─ {today_text}\n"
            f"> 現在取得できる大会情報はありません。"
        )
    else:
        await channel.send(f"## SVWB 大会一覧 ─ {today_text}")

        for t in tournaments:
            embed = discord.Embed(
                title=t["title"],
                url=t["link"],
                color=0x5865F2
            )
            embed.add_field(name="開催時間", value=t["schedule"], inline=False)
            embed.add_field(name="参加人数", value=t["players"], inline=True)
            embed.add_field(name="主催", value=t["organizer"], inline=True)
            embed.add_field(name="形式", value=t["format"], inline=True)
            if t["image"]:
                embed.set_image(url=t["image"])
            embed.set_footer(text="Tonamel")
            await channel.send(embed=embed)

    print("送信完了")
    await bot.close()


bot.run(TOKEN)