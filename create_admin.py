# create_admin.py
from app import db
from models import User
from werkzeug.security import generate_password_hash

def create_admin_account():
    # Kiểm tra xem tài khoản admin đã tồn tại chưa
    existing_admin = User.query.filter_by(username='admin').first()
    if existing_admin:
        db.session.delete(existing_admin)
        db.session.commit()
        print("Old admin account deleted.")

    # Tạo tài khoản admin
    admin_user = User(
        username='admin',
        email='admin@example.com',
        password=generate_password_hash('Hoan00002'),  # Thay đổi mật khẩu nếu cần
        is_admin=True
    )
    db.session.add(admin_user)
    db.session.commit()
    print("Admin account created!")

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        create_admin_account()