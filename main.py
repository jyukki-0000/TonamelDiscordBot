import os
import asyncio
import discord

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from discord.ext import commands
from datetime import datetime

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

URL = "https://tonamel.com/competitions?game=shadowverse_worlds_beyond&region=JP"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


async def get_tournaments():

    tournaments = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        await page.goto(URL)

        await page.wait_for_timeout(5000)

        html = await page.content()

        await browser.close()

    soup = BeautifulSoup(html, "lxml")

    links = soup.select("a[href^='/competitions/']")

    checked = set()

    for link in links:

        try:

            href = link.get("href")

            if not href:
                continue

            full_url = "https://tonamel.com" + href

            if full_url in checked:
                continue

            checked.add(full_url)

            text = link.get_text(" ", strip=True)

            if len(text) < 3:
                continue

            image = None

            img = link.select_one("img")

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
            print(e)

    return tournaments[:10]


@bot.event
async def on_ready():

    print(f"ログイン成功: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    tournaments = await get_tournaments()

    today = datetime.now().strftime("%Y/%m/%d")

    # =========================
    # 一覧
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
            embed.set_thumbnail(url=t["image"])

        await channel.send(embed=embed)

    print("送信完了")

    await bot.close()


bot.run(TOKEN)