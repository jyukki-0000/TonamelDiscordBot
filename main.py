import os
import re
import json
import requests
import discord

from bs4 import BeautifulSoup
from discord.ext import commands
from datetime import datetime

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


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
            timeout=20
        )

        print("status:", response.status_code)

        html = response.text

        print("html length:", len(html))

        # JSON抽出
        match = re.search(
            r'window\.__NUXT__=(.*)</script>',
            html
        )

        if not match:
            print("NUXTデータ取得失敗")
            return tournaments

        json_text = match.group(1)

        data = json.loads(json_text)

        json_string = json.dumps(data)

        # 大会URL抽出
        urls = re.findall(
            r'\/competitions\/[a-zA-Z0-9_-]+',
            json_string
        )

        checked = set()

        for url in urls:

            try:

                full_url = (
                    "https://tonamel.com" + url
                )

                if full_url in checked:
                    continue

                checked.add(full_url)

                slug = url.split("/")[-1]

                title = slug.replace("-", " ")

                tournaments.append({
                    "title": title,
                    "link": full_url,
                    "players": "未取得",
                    "organizer": "Tonamel",
                    "image": None,
                    "format": "未取得"
                })

                # 最大10件
                if len(tournaments) >= 10:
                    break

            except Exception as e:
                print("解析エラー:", e)

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

        embed.set_footer(
            text="Tonamel Tournament"
        )

        await channel.send(embed=embed)

    print("送信完了")

    await bot.close()


bot.run(TOKEN)