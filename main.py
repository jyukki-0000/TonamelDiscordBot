import os
import requests
import discord

from bs4 import BeautifulSoup
from discord.ext import commands
from datetime import datetime, timezone, timedelta

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


def get_today_string():
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).strftime("%Y/%m/%d")


def get_tournaments():

    tournaments = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    try:

        response = requests.get(
            URL,
            headers=headers,
            timeout=15
        )

        print("status:", response.status_code)

        html = response.text

        print("html length:", len(html))

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        links = soup.find_all("a")

        checked = set()

        today = get_today_string()

        for link in links:

            try:

                href = link.get("href")

                if not href:
                    continue

                if "/competitions/" not in href:
                    continue

                full_url = (
                    "https://tonamel.com" + href
                )

                if full_url in checked:
                    continue

                checked.add(full_url)

                text = link.get_text(
                    " ",
                    strip=True
                )

                if len(text) < 5:
                    continue

                # 最大10件
                if len(tournaments) >= 10:
                    break

                image = None

                img = link.find("img")

                if img:
                    image = img.get("src")

                tournaments.append({
                    "title": text[:100],
                    "link": full_url,
                    "players": "未取得",
                    "organizer": "Tonamel",
                    "image": image,
                    "format": "未取得"
                })

            except Exception as e:
                print("大会解析エラー:", e)

    except Exception as e:
        print("取得エラー:", e)

    print("取得大会数:", len(tournaments))

    return tournaments


@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    if channel is None:
        print("チャンネル取得失敗")
        await bot.close()
        return

    tournaments = get_tournaments()

    today_text = datetime.now().strftime(
        "%Y/%m/%d"
    )

    # =========================
    # 一覧
    # =========================

    message = (
        f"## 【{today_text} SVWB 大会一覧】\n\n"
    )

    if not tournaments:

        message += (
            "現在取得できる大会がありません。"
        )

    else:

        for i, t in enumerate(
            tournaments,
            start=1
        ):

            message += (
                f"{i}️⃣ "
                f"[{t['title']}]({t['link']})\n"
                f"参加人数: {t['players']}\n"
                f"主催: {t['organizer']}\n\n"
            )

    await channel.send(message)

    # =========================
    # Embed
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
            embed.set_thumbnail(
                url=t["image"]
            )

        embed.set_footer(
            text="Tonamel Tournament"
        )

        await channel.send(embed=embed)

    print("送信完了")

    await bot.close()


bot.run(TOKEN)