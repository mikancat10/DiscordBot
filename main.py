import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import os
import requests
import threading
import xml.etree.ElementTree as ET
from flask import Flask
import openai  # AI会話用

# --- 1. 設定と環境変数 ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_id(key):
    val = os.getenv(key)
    return int(val) if val and val.isdigit() else None

CH_IDS = {
    "news": get_id("CH_NEWS"),      # 天気・ニュース・宣伝用
    "greeting": get_id("CH_GREETING"), # 挨拶用
    "log": get_id("CH_LOG"),        # VC入退室ログ用
    "welcome": get_id("CH_WELCOME"),  # 新規入会メッセージ用
}

# --- 2. Flask (稼働維持用) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- 3. ボットクラス ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        self.scheduled_task.start()
        self.scratch_promotion.start() # 1時間おきの宣伝開始

    async def on_ready(self):
        print(f"✅ ログイン成功: {self.user.name}")

    # --- A. 定期タスク (挨拶・天気・ニュース) ---
    @tasks.loop(seconds=60)
    async def scheduled_task(self):
        jst = timezone(timedelta(hours=9), 'JST')
        now = datetime.now(jst).strftime('%H:%M')

        # 朝 08:00 天気とニュース
        if now == "08:00" and CH_IDS["news"]:
            ch = self.get_channel(CH_IDS["news"])
            if ch:
                msg = "🌅 **おはようございます！今日の天気とニュースです**\n"
                # 天気取得 (東京の例)
                try:
                    res = requests.get("https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json").json()
                    weather = res[0]['timeSeries'][0]['areas'][0]['weathers'][0]
                    msg += f"☁️ 今日の天気: {weather}\n"
                except: msg += "⚠️ 天気情報の取得に失敗しました。\n"
                
                # ニュース取得
                try:
                    res = requests.get("https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja")
                    root = ET.fromstring(res.text)
                    msg += "\n📰 **最新ニュース**\n"
                    for item in root.findall('.//item')[:3]:
                        msg += f"・{item.find('title').text}\n"
                except: pass
                await ch.send(msg)

        # 昼 12:00 挨拶
        if now == "12:00" and CH_IDS["greeting"]:
            ch = self.get_channel(CH_IDS["greeting"])
            if ch: await ch.send("🍱 12:00です。お昼休みにしましょう！")

    # --- B. Scratchプロジェクト宣伝 (1時間に1回) ---
    @tasks.loop(hours=1)
    async def scratch_promotion(self):
        if CH_IDS["news"]:
            ch = self.get_channel(CH_IDS["news"])
            if ch:
                try:
                    # Scratchの「傾向」からランダムに1つ取得する例
                    res = requests.get("https://api.scratch.mit.edu/explore/projects?limit=1&mode=trending&q=*").json()
                    project = res[0]
                    p_id = project['id']
                    p_title = project['title']
                    await ch.send(f"🚀 **Scratchおすすめプロジェクト紹介**\n「{p_title}」\nhttps://scratch.mit.edu/projects/{p_id}/")
                except: pass

    # --- C. VC入退室確認ログ ---
    async def on_voice_state_update(self, member, before, after):
        ch = self.get_channel(CH_IDS["log"])
        if not ch: return
        if before.channel is None and after.channel is not None:
            await ch.send(f"🎤 **{member.display_name}** が `{after.channel.name}` に参加しました。")
        elif before.channel is not None and after.channel is None:
            await ch.send(f"👋 **{member.display_name}** が退出しました。")

    # --- D. 新規メンバーへのメッセージ (個人 & 通常) ---
    async def on_member_join(self, member):
        # サーバー内メッセージ
        ch = self.get_channel(CH_IDS["welcome"])
        if ch: await ch.send(f"🎊 {member.mention} さん、サーバーへようこそ！")
        # 個人メッセージ (DM)
        try:
            await member.send(f"こんにちは！{member.guild.name}へようこそ！楽しんでいってくださいね。")
        except: print(f"{member.name} へのDM送信に失敗しました（ブロック等）")

# --- 4. コマンド定義 ---
bot = MyBot()

# AI会話機能 (/chat)
@bot.tree.command(name="chat", description="AIと会話します")
async def chat(interaction: discord.Interaction, メッセージ: str):
    await interaction.response.defer() # 処理に時間がかかるので保留
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": メッセージ}]
        )
        answer = response.choices[0].message.content
        await interaction.followup.send(f"🗨️ **AIの回答:**\n{answer}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生しました: {e}")

# --- 5. 実行 ---
if __name__ == "__main__":
    t = threading.Thread(target=run_web, daemon=True)
    t.start()
    if TOKEN:
        bot.run(TOKEN)
