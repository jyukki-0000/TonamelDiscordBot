import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import commands
from datetime import datetime

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def get_tournaments():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    res = requests.get(URL, headers=headers)

    soup = BeautifulSoup(res.text, "lxml")

    tournaments = []

    # Tonamelの大会カード取得
    cards = soup.select("a[href^='/competitions/']")

    checked = set()

    for card in cards:
        try:
            href = card.get("href")

            if not href:
                continue

            full_url = "https://tonamel.com" + href

            # 重複防止
            if full_url in checked:
                continue

            checked.add(full_url)

            text = card.get_text(" ", strip=True)

            if len(text) < 5:
                continue

            title = text[:100]

            image_tag = card.select_one("img")

            image = None

            if image_tag:
                image = image_tag.get("src")

            tournaments.append({
                "title": title,
                "link": full_url,
                "players": "取得中",
                "organizer": "Tonamel",
                "image": image,
                "format": "未取得"
            })

        except Exception as e:
            print(e)

    return tournaments[:10]


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