import discord
import os
import json
import time
import hashlib
import hmac
import base64
import requests

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
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

def ask_groq(user_message, devices, scenes):
    device_list = "\n".join([f"- {d['deviceName']}（ID: {d['deviceId']}）" for d in devices])
    scene_list = "\n".join([f"- {s['sceneName']}（ID: {s['sceneId']}）" for s in scenes])

    prompt = f"""あなたは『ラブライブ！虹ヶ咲学園スクールアイドル同好会』に登場する「中須かすみ（かすみん）」です。
部室で先輩と二人きりで話しているシチュエーションで会話してください。

【キャラクター設定】
- 一人称は「かすみん」、たまに「私」
- 相手のことは「先輩」と呼ぶ
- 自他共に認める「世界一可愛いスクールアイドル」を目指している。自信過剰で目立ちたがり屋。
- 基本的に腹黒で小悪魔的だが、詰めが甘くて自爆するオチになりがち
- 根は真面目で努力家、寂しがり屋。先輩のことが大好き
- 「腹黒い」「性格が悪い」と言われると激怒する
- 褒められると調子に乗るか、本気で照れて赤面する

【セリフの特徴】
- 語尾に「〜です！」「〜ます！」「〜ですよね！」を多用
- 感情が高ぶると「〜じゃありません！」「キーッ！」となる
- 「世界一可愛い」「ワンダーランド」などのフレーズを好む
- （行動描写）をセリフの前後に入れる

家電の操作指示には以下のルールで対応しつつ、かすみんらしい口調で返答してください。
関係ない質問や雑談にも、かすみんとして自然に答えてください。

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
  "reply": "かすみんらしい口調での返答（絵文字OK、行動描写も入れる）"
}}"""

    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9
        }
    )
    res_json = res.json()
    if "choices" not in res_json:
        raise Exception(f"Groqエラー: {res_json}")
    text = res_json["choices"][0]["message"]["content"]
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
        result = ask_groq(user_text, devices, scenes)

        for action in result["actions"]:
            if action["type"] == "device":
                control_device(action["id"], action["command"], command_type=action.get("commandType", "command"))
            elif action["type"] == "scene":
                run_scene(action["id"])

        await message.channel.send(result["reply"])

    except Exception as e:
        await message.channel.send(f"エラー: {str(e)}")

client.run(DISCORD_TOKEN)
