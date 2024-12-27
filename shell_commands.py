import os
from app import app

with app.app_context():
    # Định nghĩa các đường dẫn
    base_dir = app.root_path
    static_dir = os.path.join(base_dir, 'static')
    uploads_dir = os.path.join(static_dir, 'uploads')
    images_dir = os.path.join(uploads_dir, 'images')
    variants_dir = os.path.join(images_dir, 'variants')
    products_dir = os.path.join(images_dir, 'products')

    # Tạo các thư mục
    for directory in [static_dir, uploads_dir, images_dir, variants_dir, products_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Đã tạo thư mục: {directory}")
        
        # Kiểm tra quyền
        if os.access(directory, os.W_OK):
            print(f"✓ {directory}: Có quyền ghi")
        else:
            print(f"✗ {directory}: Không có quyền ghi")

    # In ra cấu trúc thư mục
    print("\nCấu trúc thư mục:")
    for root, dirs, files in os.walk(static_dir):
        level = root.replace(static_dir, '').count(os.sep)
        indent = ' ' * 4 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f"{subindent}{f}") 