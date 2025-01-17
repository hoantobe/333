from flask import Flask, render_template
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User
from extensions import db, login_manager, migrate
import os

from models import User, Post, PostImage, Category

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY', 'hoan050505')  # Sử dụng biến môi trường cho secret key
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:DtmxLdRwDfdGiikhkrhyYENZiFOqqyFP@roundhouse.proxy.rlwy.net:21669/railway'
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        from models import User, Product, Order, OrderItem, Variant, Category
        db.create_all()

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 465
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_USERNAME'] = 'hoan05052002@gmail.com'
    app.config['MAIL_PASSWORD'] = 'hoan00002'
    return app

app = create_app()

from routes import *

if __name__ == "__main__":
    app.run(debug=True)