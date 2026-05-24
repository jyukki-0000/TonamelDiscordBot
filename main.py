import os
import requests
import discord

from discord.ext import commands
from datetime import datetime

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

API_URL = "https://tonamel.com/api/competitions"

params = {
    "game": "shadowverse_worlds_beyond",
    "region": "JP"
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def get_tournaments():

    tournaments = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=headers
    )

    print("status:", response.status_code)

    data = response.json()

    competitions = data.get("competitions", [])

    for comp in competitions[:10]:

        try:

            title = comp.get("name", "大会名未取得")

            slug = comp.get("slug", "")

            link = f"https://tonamel.com/competition/{slug}"

            organizer = comp.get("owner", {}).get("name", "不明")

            participants = (
                f"{comp.get('participant_count', 0)}"
                f"/{comp.get('capacity', '?')}"
            )

            image = comp.get("cover_image_url")

            format_name = comp.get("format_name", "未取得")

            tournaments.append({
                "title": title,
                "link": link,
                "players": participants,
                "organizer": organizer,
                "image": image,
                "format": format_name
            })

        except Exception as e:
            print("ERROR:", e)

    return tournaments


@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    tournaments = get_tournaments()

    today = datetime.now().strftime("%Y/%m/%d")

    # =========================
    # 一覧メッセージ
    # =========================

    message = f"## 【{today} SVWB 大会一覧】\n\n"

    if not tournaments:
        message += "現在取得できる大会がありません。"

    for i, t in enumerate(tournaments, start=1):

        message += (
            f"{i}️⃣ "
            f"[{t['title']}]({t['link']})\n"
            f"参加人数: {t['players']}\n"
            f"主催: {t['organizer']}\n\n"
        )

    await channel.send(message)

    # =========================
    # 各大会Embed
    # =========================

    for t in tournaments:

        embed = discord.Embed(
            title=t["title"],
            url=t["link"],
            color=discord.Color.blue()
        )

        embed.add_field(
            name="参加人数",
            value=t["players"],
            inline=True
        )

        embed.add_field(
            name="主催",
            value=t["organizer"],
            inline=True
        )

        embed.add_field(
            name="トーナメント形式",
            value=t["format"],
            inline=False
        )

        if t["image"]:
            embed.set_thumbnail(url=t["image"])

        embed.set_footer(text="Tonamel Tournament")

        await channel.send(embed=embed)

    print("送信完了")

    await bot.close()


bot.run(TOKEN)