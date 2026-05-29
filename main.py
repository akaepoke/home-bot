import discord
import os
import json
import time
import hashlib
import hmac
import base64
import requests

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SWITCHBOT_TOKEN = os.environ.get("SWITCHBOT_TOKEN")
SWITCHBOT_SECRET = os.environ.get("SWITCHBOT_SECRET")

def make_headers():
    nonce = "abc123"
    t = str(round(time.time() * 1000))
    string_to_sign = SWITCHBOT_TOKEN + t + nonce
    sign = base64.b64encode(
        hmac.new(SWITCHBOT_SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "Authorization": SWITCHBOT_TOKEN,
        "sign": sign,
        "nonce": nonce,
        "t": t,
        "Content-Type": "application/json"
    }

def get_devices():
    res = requests.get("https://api.switch-bot.com/v1.1/devices", headers=make_headers())
    return res.json().get("body", {}).get("deviceList", [])

def get_scenes():
    res = requests.get("https://api.switch-bot.com/v1.1/scenes", headers=make_headers())
    return res.json().get("body", [])

def control_device(device_id, command, param="default"):
    body = {"command": command, "parameter": param, "commandType": "command"}
    requests.post(f"https://api.switch-bot.com/v1.1/devices/{device_id}/commands", headers=make_headers(), json=body)

def run_scene(scene_id):
    requests.post(f"https://api.switch-bot.com/v1.1/scenes/{scene_id}/execute", headers=make_headers())

def ask_gemini(user_message, devices, scenes):
    device_list = "\n".join([f"- {d['deviceName']}（ID: {d['deviceId']}）" for d in devices])
    scene_list = "\n".join([f"- {s['sceneName']}（ID: {s['sceneId']}）" for s in scenes])

    prompt = f"""あなたはスマートホームのAIアシスタントです。
ユーザーの指示を解析して操作内容をJSON形式で返してください。

利用可能なデバイス:
{device_list}

利用可能なシーン:
{scene_list}

ニュアンスのルール:
- 「暗くして」「目が痛い」→ デバイス「電気」をOFF、デバイス「フィギュアライト」をON
- 「寒い」「暖かくして」→ シーン「暖房」を実行
- 「熱い」「暑い」「涼しくして」→ シーン「冷房」を実行
- 「寝る」「おやすみ」→ 電気・エアコン・せんぷうき・フィギュアライトをOFF
- 「眩しい」「明るすぎ」→ デバイス「電気」をOFF

ユーザーの指示: {user_message}

以下のJSON形式のみで返答してください（コードブロック不要）:
{{
  "actions": [
    {{
      "type": "device" または "scene",
      "id": "デバイスIDまたはシーンID",
      "command": "turnOn" または "turnOff"（deviceの場合のみ）,
      "description": "何をするか日本語で"
    }}
  ],
  "reply": "ユーザーへの返答（日本語、絵文字OK）"
}}"""

    res = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        json={"contents": [{"parts": [{"text": prompt}]}]}
    )
    res_json = res.json()
    if "candidates" not in res_json:
        raise Exception(f"Geminiエラー: {res_json}")
    text = res_json["candidates"][0]["content"]["parts"][0]["text"]
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Bot起動: {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if not message.content.startswith("!"):
        return

    user_text = message.content[1:]
    await message.channel.send("⏳ 考え中...")

    try:
        devices = get_devices()
        scenes = get_scenes()
        result = ask_gemini(user_text, devices, scenes)

        for action in result["actions"]:
            if action["type"] == "device":
                control_device(action["id"], action["command"])
            elif action["type"] == "scene":
                run_scene(action["id"])

        await message.channel.send(result["reply"])

    except Exception as e:
        await message.channel.send(f"エラー: {str(e)}")

client.run(DISCORD_TOKEN)