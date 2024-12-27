import requests

# Thay thế bằng token của bạn và chat_id cố định
TOKEN = '7234592257:AAGyRzMsMS2jlHWGpWKihI6jfcDFsPPv6hw'
CHAT_ID = 'YOUR_CHAT_ID'  # Lưu Chat ID ở đây

def send_message_to_telegram(message):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    data = {
        'chat_id': 6580174494,
        'text': message
    }
    response = requests.post(url, data=data)
    return response.json()

# Gửi thông báo
message = "Đây là thông báo tự động từ bot!"
result = send_message_to_telegram(message)

if result.get("ok"):
    print("Tin nhắn đã được gửi thành công!")
else:
    print("Có lỗi xảy ra:", result)