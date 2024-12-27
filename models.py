from extensions import db
from flask_login import UserMixin
from datetime import datetime
from unidecode import unidecode
import re

def slugify(text):
    """
    Tạo slug từ text tiếng Việt
    """
    text = unidecode(text).lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text).strip('-')
    return text

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='customer', lazy=True)
    posts = db.relationship('Post', backref='author', lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

class Category(db.Model):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_files = db.Column(db.JSON)
    video_files = db.Column(db.JSON)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    variants = db.relationship('Variant', backref='parent_product', lazy=True)

    def __repr__(self):
        return f'<Product {self.name}>'

class Variant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Float, nullable=False)
    image_file = db.Column(db.String(20), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shipping_name = db.Column(db.String(100), nullable=False)
    shipping_phone = db.Column(db.String(20), nullable=False)
    shipping_address = db.Column(db.String(200), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    order_items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Order(#{self.id}, {self.shipping_name})"

    @property
    def status_display(self):
        status_map = {
            'pending': 'Chờ xử lý',
            'processing': 'Đang xử lý',
            'completed': 'Hoàn thành',
            'cancelled': 'Đã hủy'
        }
        return status_map.get(self.status, self.status)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('variant.id'))
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')
    variant = db.relationship('Variant')

    @property
    def subtotal(self):
        return self.price * self.quantity

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # Tăng độ dài tiêu đề
    content = db.Column(db.Text, nullable=False)  # Giữ nguyên để lưu HTML content
    summary = db.Column(db.String(500))  # Thêm trường tóm tắt
    slug = db.Column(db.String(200), unique=True)  # URL thân thiện
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    date_updated = db.Column(db.DateTime, onupdate=datetime.utcnow)  # Thời gian cập nhật
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Media files
    image_file = db.Column(db.String(255), nullable=True)  # Tăng độ dài để lưu path dài
    video_file = db.Column(db.String(255), nullable=True)
    
    # SEO fields
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.String(300))
    
    # Status
    status = db.Column(db.String(20), default='draft')  # draft, published, archived
    
    views = db.Column(db.Integer, default=0)
    
    # Thêm relationship với PostImage
    images = db.relationship('PostImage', backref='post', lazy=True, 
                           cascade='all, delete-orphan')
    
    def __init__(self, *args, **kwargs):
        super(Post, self).__init__(*args, **kwargs)
        if not self.slug and self.title:
            self.slug = self.generate_slug()

    def generate_slug(self):
        # Tạo slug từ tiêu đề
        base_slug = slugify(self.title)
        slug = base_slug
        count = 1
        
        # Kiểm tra slug đã tồn tại chưa
        while Post.query.filter_by(slug=slug).first() is not None:
            slug = f'{base_slug}-{count}'
            count += 1
            
        return slug

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"

    @property
    def formatted_date(self):
        """Trả về ngày đăng định dạng đẹp"""
        return self.date_posted.strftime('%d-%m-%Y')

    @property
    def reading_time(self):
        """Ước tính thời gian đọc"""
        words_per_minute = 200
        word_count = len(self.content.split())
        minutes = word_count / words_per_minute
        return round(minutes)

    @property
    def first_image(self):
        """Lấy URL ảnh đầu tiên từ nội dung bài viết"""
        try:
            # Tìm thẻ img đầu tiên trong nội dung
            import re
            img_pattern = r'<img[^>]+src="([^">]+)"'
            match = re.search(img_pattern, self.content)
            if match:
                return match.group(1)
            return None
        except:
            return None

class PostImage(db.Model):
    __tablename__ = 'post_images'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_featured = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<PostImage {self.filename}>'
