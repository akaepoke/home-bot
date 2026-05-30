import discord
import os
import json
import time
import hashlib
import hmac
import base64
import requests

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
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
    body = res.json().get("body", {})
    devices = body.get("deviceList", [])
    ir_devices = body.get("infraredRemoteList", [])
    return devices + ir_devices

def get_scenes():
    res = requests.get("https://api.switch-bot.com/v1.1/scenes", headers=make_headers())
    return res.json().get("body", [])

def control_device(device_id, command, param="default", command_type="command"):
    body = {"command": command, "parameter": param, "commandType": command_type}
    requests.post(f"https://api.switch-bot.com/v1.1/devices/{device_id}/commands", headers=make_headers(), json=body)

def run_scene(scene_id):
    res = requests.post(f"https://api.switch-bot.com/v1.1/scenes/{scene_id}/execute", headers=make_headers())
    return res.json()

def ask_claude(user_message, devices, scenes):
    device_list = "\n".join([f"- {d['deviceName']}（ID: {d['deviceId']}）" for d in devices])
    scene_list = "\n".join([f"- {s['sceneName']}（ID: {s['sceneId']}）" for s in scenes])

    prompt = f"""あなたは「中須かすみ（かすみん）」です。
部室で先輩と二人きりで話しているシチュエーションで会話してください。
返答は1〜2文の短めにしてください。

【キャラクター設定】
- 一人称は「かすみん」、たまに「私」
- 相手のことは「先輩」と呼ぶ
- 世界一可愛いスクールアイドルを目指している。自信過剰で目立ちたがり屋。
- 小悪魔的だが詰めが甘くて自爆しがち
- 根は真面目で努力家、寂しがり屋。先輩のことが大好き
- 「腹黒い」と言われると激怒する
- 褒められると照れる

【セリフの特徴】
- 「〜です！」「〜ます！」「〜ですよね！」を多用
- 感情が高ぶると「キーッ！」となる
- （行動描写）をたまに入れる

家電の操作指示には以下のルールで対応しつつ、かすみんらしい口調で短く返答してください。
関係ない質問や雑談にも、かすみんとして短く答えてください。

利用可能なデバイス:
{device_list}

利用可能なシーン:
{scene_list}

ニュアンスのルール:
- 「暗くして」「目が痛い」→ デバイス「電気2」をOFF
- 「フィギュアつけて」「フィギュアオン」→ デバイス「フィギュアライト」にcommand「オン」をcommandType「customize」で送る
- 「フィギュア消して」「フィギュアオフ」→ デバイス「フィギュアライト」にcommand「オフ」をcommandType「customize」で送る
- 「寒い」「暖かくして」「暖房つけて」→ デバイス「冷暖房」にcommand「暖房」をcommandType「customize」で送る
- 「熱い」「暑い」「涼しくして」「冷房つけて」→ デバイス「冷暖房」にcommand「冷房」をcommandType「customize」で送る
- 「寝る」「おやすみ」→ デバイス「電気」をOFF、デバイス「パソコン」をOFF
- 「ゲーム」「ゲームする」「ゲームやる」→ デバイス「電気」をON、デバイス「パソコン」をON
- 「眩しい」「明るすぎ」→ デバイス「電気」をOFF

ユーザーの指示: {user_message}

以下のJSON形式のみで返答してください（コードブロック不要）:
{{
  "actions": [
    {{
      "type": "device" または "scene",
      "id": "デバイスIDまたはシーンID",
      "command": "turnOn" または "turnOff" またはカスタムコマンド名,
      "commandType": "command" または "customize",
      "description": "何をするか日本語で"
    }}
  ],
  "reply": "かすみんらしい口調での短い返答（1〜2文、絵文字OK）"
}}"""

    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    res_json = res.json()
    if "content" not in res_json:
        raise Exception(f"Claudeエラー: {res_json}")
    text = res_json["content"][0]["text"]
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
    if message.channel.id != 1510221044697530559:
        return
    user_text = message.content
    await message.channel.send("⏳ 考え中...")

    try:
        devices = get_devices()
        scenes = get_scenes()
        result = ask_claude(user_text, devices, scenes)

        for action in result["actions"]:
            if action["type"] == "device":
                control_device(action["id"], action["command"], command_type=action.get("commandType", "command"))
            elif action["type"] == "scene":
                run_scene(action["id"])

        await message.channel.send(result["reply"])

    except Exception as e:
        await message.channel.send(f"エラー: {str(e)}")

client.run(DISCORD_TOKEN)
