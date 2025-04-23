import os
import datetime
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

import firebase_admin
from firebase_admin import credentials, firestore

# === 初始化設定 ===
load_dotenv()
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')
firebase_key_path = "firebase_key.json"

# === 初始化 Firebase ===
if not os.path.exists(firebase_key_path):
    raise FileNotFoundError(f"找不到 Firebase 金鑰檔案：{firebase_key_path}")
cred = credentials.Certificate(firebase_key_path)
firebase_admin.initialize_app(cred)
db = firestore.client()


app = Flask(__name__)

# 初始化 LINE SDK
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# 使用者狀態記錄：用來判斷目前使用者正在進行什麼操作
user_states = {}  # 格式: { "user_id": "狀態" }，例如: {"U123456": "等待寫入", "U789012": "等待查詢"}
WRITE_MODE = "等待寫入"
READ_MODE = "等待查詢"

# Webhook 接收
@app.route("/", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent)
def handle_message(event):
    if not isinstance(event.message, TextMessage):
        return

    user_id = event.source.user_id #取得這個 LINE 使用者的 ID
    user_message = event.message.text.strip().lower() # 將使用者輸入轉為小寫方便判斷

    # === 進入寫入模式 ===
    if user_message == "/write":
        user_states[user_id] = WRITE_MODE
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請直接輸入：\n教授名稱 課程名稱\n你的評價")
        )
        return

    # === 處理寫入模式的輸入 ===
    if user_id in user_states and user_states[user_id] == WRITE_MODE:
        user_states.pop(user_id) # 完成寫入後，移除使用者狀態

        lines = event.message.text.strip().splitlines()

        course_key = lines[0].strip() # 取輸入訊息的第一行 例如：帶至華 作業系統
        feedback = lines[1].strip() # 取輸入的第二行 例如：這堂課很好，很有收穫

        doc = db.collection("feedbacks").document(course_key).get() # 取得指定的document，也就是指定的"課程名稱ID"
        
        if doc.exists:
            feedbacks = doc.to_dict().get("回饋", [])  # 取得該課程的回饋列表，先將其轉成 dict 格式，讓Python更好操作
            feedbacks.append(feedback)                # 將新評價加入回饋列表
        else: 
            feedbacks = [feedback]
        
        db.collection("feedbacks").document(course_key).set({"回饋": feedbacks}, merge=True)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"✅ 成功寫入「{course_key}」的評價，感謝你的回饋！")
        )
        return

    # === 進入查詢模式 ===
    if user_message == "/read":
        user_states[user_id] = READ_MODE
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入教授名稱與課程名稱（例如：帶至華 作業系統）：")
        )
        return

    # === 處理查詢模式的輸入 ===
    if user_id in user_states and user_states[user_id] == READ_MODE:
        user_states.pop(user_id) # 完成查詢後，移除使用者狀態
        course_key = event.message.text.strip()
        
        doc = db.collection("feedbacks").document(course_key).get()

        if doc.exists:
            feedbacks = doc.to_dict().get("回饋", [])
            if feedbacks:
                reply_text = f"【{course_key}】課程評價：\n" + "\n".join(f"- {fb}" for fb in feedbacks)
            else:
                reply_text = f"「{course_key}」目前沒有任何評價。"
        else:
            reply_text = f"查無「{course_key}」的課程紀錄。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    # === 預設提示 ===
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="請輸入 /write 來填寫課程評價，或 /read 查詢課程評價")
    )

# 啟動 Flask 應用
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)