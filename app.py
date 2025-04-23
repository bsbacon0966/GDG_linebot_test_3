import json
import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler, Event
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging.models import TextMessage
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    ImageSendMessage)
from linebot.exceptions import InvalidSignatureError
import logging
from firebase_admin import credentials, firestore,initialize_app
import google.generativeai as genai

# 加載 .env 文件中的變數
load_dotenv()

# 從環境變數中讀取 LINE 的 Channel Access Token 和 Channel Secret
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')
gemini_api_key = os.getenv("GEMINI_API_KEY")

# 檢查是否設置了環境變數
if not line_token or not line_secret or not gemini_api_key:
    print(f"LINE_TOKEN: {line_token}")  # 調試輸出
    print(f"LINE_SECRET: {line_secret}")  # 調試輸出
    print(f"GEMINI_API_KEY: {gemini_api_key}")  # 調試輸出
    raise ValueError("LINE_TOKEN, LINE_SECRET 或 GEMINI_API_KEY 未設置")

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# === 初始化 Firebase ===
firebase_cred_str = os.getenv("FIREBASE_KEY") #放在遠端得環境變數中
firebase_initialized = False
if firebase_cred_str:
    cred_dict = json.loads(firebase_cred_str)  # 將 JSON 字串轉回 dict
    cred = credentials.Certificate(cred_dict)
    initialize_app(cred)
    firebase_initialized = True
else:
    raise ValueError("未設定 FIREBASE_CREDENTIAL_JSON")

# === 初始化 Gemini ===
genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-pro")

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

@app.route("/", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭
    signature = request.headers['X-Line-Signature']

    # 取得請求的原始內容
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # 驗證簽名並處理請求
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: Event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    app.logger.info(f"使用者 ID: {user_id}")
    app.logger.info(f"收到的訊息: {user_message}")
    
    db = firestore.client()
    if user_message.lower() == '/delete':
        doc_ref = db.collection("feedbacks").document("history")
        try:
            doc_ref.set({"record": []})
            reply_text = "對話記錄已成功刪除。"
        except Exception as e:
            app.logger.error(f"刪除對話記錄時發生錯誤: {e}")
            reply_text = "刪除對話記錄時發生錯誤，請稍後再試。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    if not firebase_initialized:
        app.logger.error("Firebase 未初始化，無法存取資料庫。")
        reply_text = "抱歉，目前服務暫時無法使用。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    doc_ref = db.collection("feedbacks").document("history")
    doc = doc_ref.get()
    history = []
    if doc.exists:
        history = doc.to_dict().get("record", [])

    if history == []:
        response = model.generate_content(user_message)
    else:
        response = model.generate_content(f"之前的歷史對話為{history}，請根據歷史對話，回答{user_message}")

    reply_text = ""
    if response and hasattr(response, 'text'):
        reply_text = response.text
        history.append({"role": "user", "content": user_message})
        history.append({"role": "gemini", "content": reply_text})
        doc_ref.set({"record": history})
    else:
        reply_text = "抱歉，我無法回答這個問題。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# 應用程序入口點
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)