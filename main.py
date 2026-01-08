import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import os
import requests
import threading
import xml.etree.ElementTree as ET
from flask import Flask
from openai import OpenAI  # 最新のOpenAIクライアント

# --- 1. 設定と環境変数 ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
# OpenAIクライアントの初期化
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_id(key):
    val = os.getenv(key)
    return int(val) if val and val.isdigit() else None

CH_IDS = {
    "news": get_id("CH_NEWS"),      
    "greeting": get_id("CH_GREETING"), 
    "log": get_id("CH_LOG"),        
    "welcome": get_id("CH_WELCOME"),  
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
        self.scratch_promotion.start()

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
                try:
                    res = requests.get("https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json").json()
                    weather = res[0]['timeSeries'][0]['areas'][0]['weathers'][0]
                    msg += f"☁️ 東京の天気: {weather}\n"
                except: msg += "⚠️ 天気取得エラー\n"
                
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
                    res = requests.get("https://api.scratch.mit.edu/explore/projects?limit=1&mode=trending&q=*").json()
                    project = res[0]
                    await ch.send(f"🚀 **Scratchおすすめ作品**\n「{project['title']}」\nhttps://scratch.mit.edu/projects/{project['id']}/")
                except: pass

    # --- C. VC入退室ログ ---
    async def on_voice_state_update(self, member, before, after):
        ch = self.get_channel(CH_IDS["log"])
        if not ch: return
        if before.channel is None and after.channel is not None:
            await ch.send(f"🎤 **{member.display_name}** が `{after.channel.name}` に入室")
        elif before.channel is not None and after.channel is None:
            await ch.send(f"👋 **{member.display_name}** が退室")

    # --- D. 新規メンバーへの通知 ---
    async def on_member_join(self, member):
        ch = self.get_channel(CH_IDS["welcome"])
        if ch: await ch.send(f"🎊 {member.mention} さん、サーバーへようこそ！")
        try:
            await member.send(f"こんにちは！{member.guild.name}へようこそ！")
        except: pass

# --- 4. 実行 ---
bot = MyBot()

# AI会話コマンド (GPT-4o-mini使用)
@bot.tree.command(name="chat", description="GPT-4o-miniと会話します")
async def chat(interaction: discord.Interaction, メッセージ: str):
    await interaction.response.defer()
    try:
        # 最新のAPI形式
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": メッセージ}]
        )
        answer = response.choices[0].message.content
        await interaction.followup.send(f"🗨️ **AI(GPT-4o-mini)の回答:**\n{answer}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生しました: {e}")

if __name__ == "__main__":
    t = threading.Thread(target=run_web, daemon=True)
    t.start()
    if TOKEN:
        bot.run(TOKEN)
