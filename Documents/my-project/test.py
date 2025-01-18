import requests
import time
import hashlib
import hmac

def generate_signature(url, partner_id, key):
    base_string = f"{url}|{int(time.time())}"
    return hmac.new(key.encode(), base_string.encode(), hashlib.sha256).hexdigest()

def get_product_details(product_id, shop_id, partner_id, partner_key):
    url = f"https://partner.shopeemobile.com/api/v2/product/get_item_base_info"
    params = {
        "item_id": product_id,
        "shop_id": shop_id,
        "partner_id": partner_id,
        "timestamp": int(time.time()),
    }
    signature = generate_signature(url, partner_id, partner_key)
    headers = {"Authorization": signature}

    response = requests.get(url, headers=headers, params=params)
    return response.json()

# Ví dụ sử dụng:
partner_id = 1589295236
partner_key = "your_partner_key"
shop_id = 654321
product_id = 987654

product_info = get_product_details(product_id, shop_id, partner_id, partner_key)
print(product_info)