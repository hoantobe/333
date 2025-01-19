import requests
import os
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
from datetime import datetime

def allowed_file(filename, allowed_extensions=None):
    if not allowed_extensions:
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions 

def download_image_from_url(url, upload_folder):
    try:
        # Tải ảnh từ URL
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # Lấy tên file từ URL
            filename = secure_filename(os.path.basename(urlparse(url).path))
            if not filename:
                filename = 'image_' + str(datetime.now().timestamp()) + '.jpg'
            
            # Tạo đường dẫn đầy đủ
            filepath = os.path.join(upload_folder, filename)
            
            # Lưu file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
                    
            return filename
    except Exception as e:
        print(f"Lỗi khi tải ảnh: {str(e)}")
        return None 