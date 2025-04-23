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
import json
from firebase_admin import credentials, initialize_app

# 加載 .env 文件中的變數
load_dotenv()

# 從環境變數中讀取 LINE 的 Channel Access Token 和 Channel Secret
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')

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


# 檢查是否設置了環境變數
if not line_token or not line_secret:
    print(f"LINE_TOKEN: {line_token}")  # 調試輸出
    print(f"LINE_SECRET: {line_secret}")  # 調試輸出
    raise ValueError("LINE_TOKEN 或 LINE_SECRET 未設置")

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# 創建 Flask 應用
app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# 設置一個路由來處理 LINE Webhook 的回調請求
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

# 設置一個事件處理器來處理 TextMessage 事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: Event):
    if event.message.type == "text":
        user_message = event.message.text  # 使用者的訊息
        app.logger.info(f"收到的訊息: {user_message}")

        # 使用 GPT 生成回應
        reply_text =""
        if(firebase_initialized):
            # 在這裡調用 GPT 生成回應的函數
            reply_text = F"你說:{user_message}"
        else:
            reply_text = "Firebase 初始化失敗，無法處理請求。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
# 應用程序入口點
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)


