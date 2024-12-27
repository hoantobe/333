from flask import render_template, url_for, flash, redirect, request, session, abort, jsonify
from flask_mail import Mail, Message
from app import app
from extensions import db
from models import User, Product, Post, Variant, Category, Order, OrderItem, PostImage
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from markupsafe import Markup
from sqlalchemy import or_, func
from datetime import datetime, timedelta
from unidecode import unidecode
import re
from functools import wraps
import json
from decorators import admin_required
from utils import allowed_file
import time
import requests
import shutil
from pathlib import Path
from flask import current_app

def number_format(value, decimal_places=0, decimal_separator=',', thousands_separator='.'):
    """Định dạng số với số chữ số thập phân và ký tự phân cách."""
    if value is None:
        return '0'  # Hoặc một giá trị mặc định khác
    try:
        formatted_value = f"{float(value):,.{decimal_places}f}".replace(',', 'X').replace('.', decimal_separator).replace('X', thousands_separator)
        return formatted_value
    except (ValueError, TypeError):
        return '0'  # Hoặc một giá trị mặc định khác

# Thêm bộ lọc vào môi trường Jinja2
app.jinja_env.filters['number_format'] = number_format

# Tạo thư mục và copy ảnh mặc định
def setup_default_images():
    # Tạo các thư mục cần thiết
    static_dir = Path(app.root_path) / 'static'
    img_dir = static_dir / 'img'
    img_dir.mkdir(exist_ok=True)
    
    # Đường dẫn đến ảnh mặc định
    default_variant = img_dir / 'default-variant.jpg'
    default_product = img_dir / 'default-product.jpg'
    
    # Copy ảnh mặc định từ thư mục assets nếu chưa tồn tại
    if not default_variant.exists():
        source = Path(app.root_path) / 'static' / 'assets' / 'default-variant.jpg'
        if source.exists():
            shutil.copy(source, default_variant)
    
    if not default_product.exists():
        source = Path(app.root_path) / 'static' / 'assets' / 'default-product.jpg'
        if source.exists():
            shutil.copy(source, default_product)

# Gọi hàm khi khởi động app
setup_default_images()

@app.route('/')
@app.route('/home')
def home():
    # Lấy sản phẩm theo danh mục
    featured_products = {}
    categories = Category.query.all()
    
    for category in categories:
        products = Product.query.filter_by(category_id=category.id).limit(8).all()
        if products:
            featured_products[category] = products
    per_page = 4  # Số bài viết hiển thị
    posts = Post.query\
        .order_by(Post.date_posted.desc())\
        .limit(per_page).all()  # Lấy 3 bài viết mới nhất
            
    return render_template('home.html', 
                         featured_products=featured_products,
                         categories=categories,
                         posts=posts)

@app.route('/product/<int:product_id>')
def product(product_id):

        print(f"Accessing product route with ID: {product_id}")
        
        # Lấy thông tin sản phẩm
        product = Product.query.get_or_404(product_id)
        if not product:
            print("Product not found")
            flash('Không tìm thấy sản phẩm', 'error')
            return redirect(url_for('home'))
            
        print(f"Found product: {product.name}")
        
        # Kiểm tra và chuẩn bị ảnh sản phẩm
        if not product.image_files:
            product.image_files = ['default-product.jpg']
            print("Using default product image")
        
        # Lấy các biến thể của sản phẩm
        variants = Variant.query.filter_by(product_id=product.id).all()
        print(f"Found {len(variants)} variants")
        
        # Chuẩn bị dữ liệu biến thể
        for variant in variants:
            if not variant.image_file:
                variant.image_file = 'default-variant.jpg'
            print(f"Variant {variant.name} with image: {variant.image_file}")
        
        # Lấy sản phẩm liên quan
        related_products = Product.query.filter(
            Product.category_id == product.category_id,
            Product.id != product.id
        ).limit(4).all()
        
        print("Preparing to render product.html template")
        data = {
        'shop_url': url_for('products'),  # URL cho nút "Tiếp tục mua sắm"
        'cart_url': url_for('cart')      # URL cho nút "Đi tới giỏ hàng"
    }
        # Kiểm tra template tồn tại
        try:
            return render_template('product.html',
                                 product=product,
                                 variants=variants,
                                 related_products=related_products,
                                 data=data )
        except Exception as template_error:
            print(f"Template error: {str(template_error)}")
            raise
                             


@app.route('/products')
def products():
    page = request.args.get('page', 1, type=int)
    category_name = request.args.get('category')
    sort = request.args.get('sort', 'newest')
    
    # Query cơ bản
    query = Product.query
    
    # Filter theo category nếu có
    if category_name:
        category = Category.query.filter_by(name=category_name).first()
        if category:
            query = query.filter_by(category_id=category.id)
    
    # Sắp xếp
    if sort == 'price-asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price-desc':
        query = query.order_by(Product.price.desc())
    else:  # newest
        query = query.order_by(Product.id.desc())
    
    # Phân trang
    products = query.paginate(page=page, per_page=12, error_out=False)
    categories = Category.query.all()

    # Đảm bảo mỗi sản phẩm có ít nhất một ảnh
    for product in products.items:
        if not product.image_files:
            product.image_files = ['default-product.jpg']
            
    return render_template('products.html', 
                         products=products,
                         categories=categories,
                         selected_category=category_name)

@app.route('/cart')
@login_required
def cart():
    if 'cart' not in session:
        session['cart'] = []
    
    cart_items = []
    total_price = 0
    
    try:
        for item in session['cart']:
            product = Product.query.get(item['product_id'])
            variant = Variant.query.get(item['variant_id'])
            if product and variant:
                # Đảm bảo các giá trị số được chuyển đổi đúng kiểu
                quantity = int(item['quantity'])
                price = float(variant.value)
                item_total = price * quantity
                
                cart_item = {
                    'id': item['product_id'],
                    'name': product.name,
                    'variant_name': variant.name,
                    'price': price,
                    'quantity': quantity,
                    'total': item_total,
                    'image': variant.image_file if variant.image_file else 'default-variant.jpg',  # Lấy hình ảnh của biến thể
                    'product_id': product.id,
                    'variant_id': variant.id
                }
                cart_items.append(cart_item)
                total_price += item_total

        return render_template('cart.html', cart_items=cart_items, total_price=total_price)
        
    except Exception as e:
        print(f"Error in cart route: {str(e)}")  # Debug log
        flash('Có lỗi xảy ra khi hiển thị giỏ hàng!', 'danger')
        session['cart'] = []  # Reset giỏ hàng nếu có lỗi
        return redirect(url_for('products'))

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    try:
        # Lấy ID biến thể và số lượng từ form
        variant_id = request.form.get('variant')  
        quantity = int(request.form.get('quantity', 1))
        
        if not variant_id:
            print("Không có biến thể được chọn")
            return jsonify({
                'success': False,
                'message': 'Vui lòng chọn Mẫu!'
            })
        
        # Kiểm tra số lượng
        if quantity <= 0:
            return jsonify({
                'success': False,
                'message': 'Số lượng phải lớn hơn 0!'
            })

        # Khởi tạo giỏ hàng nếu chưa có
        if 'cart' not in session:
            session['cart'] = []
        
        # Lấy thông tin sản phẩm và biến thể
        product = Product.query.get_or_404(product_id)
        variant = Variant.query.get_or_404(variant_id)
        
        # Kiểm tra xem sản phẩm đã có trong giỏ hàng chưa
        cart = session['cart']
        item_found = False
        
        for item in cart:
            if item.get('product_id') == product_id and item.get('variant_id') == int(variant_id):
                item['quantity'] += quantity  # Cập nhật số lượng
                item_found = True
                break
        
        if not item_found:
            cart.append({
                'product_id': product_id,
                'variant_id': int(variant_id),
                'quantity': quantity,
                'product_name': product.name,
                'variant_name': variant.name,
                'price': variant.value
            })
        
        session['cart'] = cart
        session.modified = True
            
        return jsonify({
            'success': True,
            'message': 'Đã thêm vào giỏ hàng thành công!',
            'cart_count': len(session.get('cart', [])),
            'shop_url': url_for('products'),  # URL đến trang cửa hàng
            'cart_url': url_for('cart')   # URL đến giỏ hàng
        })
        
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Số lượng không hợp lệ!'
        })
    except Exception as e:
        print(f"Error in add_to_cart: {str(e)}")  # Log lỗi để debug
        return jsonify({
            'success': False,
            'message': 'Có lỗi xảy ra khi thêm vào giỏ hàng'
        })


@app.route('/remove_from_cart/<int:product_id>/<int:variant_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id, variant_id):
    if 'cart' in session:
        session['cart'] = [item for item in session['cart'] 
                          if not (item['product_id'] == product_id and item['variant_id'] == variant_id)]
        session.modified = True
        flash('Sản phẩm đã được xóa khỏi giỏ hàng!', 'success')
    return redirect(url_for('cart'))



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
            return redirect(url_for('register'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)  # Sử dụng phương thức băm mặc định

        # Kiểm tra xem người dùng đã tồn tại chưa
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))

        # Tạo người dùng mới
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/admin/manage_products')
@login_required
@admin_required
def manage_products():
    products = Product.query.all()
    categories = Category.query.all()
    return render_template('admin/manage_products.html', 
                         products=products,
                         categories=categories,
                         active_page='products')

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        try:
            # Lấy thông tin sản phẩm cơ bản
            name = request.form.get('name')
            category_id = request.form.get('category')
            price = request.form.get('price')
            description = request.form.get('description')
            
            # Xử lý danh mục mới nếu có
            new_category_name = request.form.get('new_category')
            if new_category_name:
                category = Category(name=new_category_name)
                db.session.add(category)
                db.session.commit()
                category_id = category.id

            # Xử lý upload ảnh sản phẩm
            image_filenames = []
            if 'image_files' in request.files:
                files = request.files.getlist('image_files')
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = save_image(file, 'products')
                        if filename:
                            image_filenames.append(filename)

            # Tạo sản phẩm mới
            new_product = Product(
                name=name,
                price=float(price),
                description=description,
                category_id=int(category_id),
                image_files=image_filenames  # Bây giờ đã có danh sách ảnh
            )
            db.session.add(new_product)
            db.session.flush()  # Để lấy product id

            # Xử lý biến thể
            variant_names = request.form.getlist('variant_name[]')
            variant_values = request.form.getlist('variant_value[]')
            variant_images = request.files.getlist('variant_image[]')

            print("Số lượng biến thể:", len(variant_names))
            print("Số lượng ảnh biến thể:", len(variant_images))

            for name, value, image in zip(variant_names, variant_values, variant_images):
                if name and value:  # Chỉ tạo biến thể nếu có tên và giá
                    try:
                        variant = Variant(
                            name=name,
                            value=float(value),
                            product_id=new_product.id
                        )
                        
                        # Xử lý ảnh biến thể
                        if image and image.filename:  # Kiểm tra có file được upload không
                            print(f"Xử lý ảnh biến thể: {image.filename}")
                            if allowed_file(image.filename):
                                filename = save_image(image, 'variants')
                                if filename:
                                    variant.image_file = filename  # Chỉ lưu tên file
                                    print(f"Đã lưu ảnh biến thể: {filename}")
                        
                        db.session.add(variant)
                        print(f"Đã thêm biến thể: {name} với ảnh: {variant.image_file}")
                    except Exception as e:
                        print(f"Lỗi khi thêm biến thể {name}: {str(e)}")
                        raise

            db.session.commit()
            flash('Sản phẩm đã được thêm thành công!', 'success')
            return redirect(url_for('manage_products'))

        except Exception as e:
            db.session.rollback()
            print(f"Lỗi khi thêm sản phẩm: {str(e)}")
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            return redirect(url_for('add_product'))

    # GET request
    categories = Category.query.all()
    return render_template('admin/add_product.html', categories=categories)

@app.route('/admin/edit_product/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    # Kiểm tra và sửa đường dẫn ảnh cho các biến thể
    for variant in product.variants:
        if variant.image_file:
            variant.image_file = verify_image_path(variant.image_file, 'variants')
    
    if request.method == 'POST':
        try:
            # Cập nhật thông tin cơ bản
            product.name = request.form.get('name')
            product.price = float(request.form.get('price'))
            product.description = request.form.get('description')
            product.category_id = int(request.form.get('category'))

            # Xử lý ảnh sản phẩm mới
            if 'image_files' in request.files:
                new_images = request.files.getlist('image_files')
                for image in new_images:
                    if image and allowed_file(image.filename):
                        filename = save_image(image, 'products')
                        if filename:
                            if not product.image_files:
                                product.image_files = []
                            product.image_files.append(filename)
                            print(f"Đã thêm ảnh mới: {filename}")

            # Xử lý biến thể
            variant_ids = request.form.getlist('variant_ids[]')
            variant_names = request.form.getlist('variant_names[]')
            variant_values = request.form.getlist('variant_values[]')
            variant_images = request.files.getlist('variant_images[]')

            # Xóa các biến thể cũ không còn trong form
            existing_variants = {str(v.id): v for v in product.variants}
            for vid in existing_variants.keys():
                if vid not in variant_ids:
                    db.session.delete(existing_variants[vid])
                    print(f"Đã xóa biến thể ID: {vid}")

            # Cập nhật hoặc thêm biến thể mới
            for vid, name, value, image in zip(variant_ids, variant_names, variant_values, variant_images):
                if name and value:
                    if vid and vid != 'null' and vid in existing_variants:
                        # Cập nhật biến thể hiện có
                        variant = existing_variants[vid]
                        variant.name = name
                        variant.value = float(value)
                        
                        # Cập nhật ảnh nếu có
                        if image and image.filename:
                            filename = save_image(image, 'variants')
                            if filename:
                                variant.image_file = filename
                                print(f"Đã cập nhật ảnh biến thể: {filename}")
                    else:
                        # Thêm biến thể mới
                        variant = Variant(
                            name=name,
                            value=float(value),
                            product_id=product.id
                        )
                        if image and image.filename:
                            filename = save_image(image, 'variants')
                            if filename:
                                variant.image_file = filename
                                print(f"Đã thêm ảnh cho biến thể mới: {filename}")
                        db.session.add(variant)
                        print(f"Đã thêm biến thể mới: {name}")

            db.session.commit()
            flash('Sản phẩm đã được cập nhật thành công!', 'success')
            return redirect(url_for('manage_products'))

        except Exception as e:
            db.session.rollback()
            print(f"Lỗi khi cập nhật sản phẩm: {str(e)}")
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            return redirect(url_for('edit_product', id=id))

    # GET request
    categories = Category.query.all()
    # Đảm bảo đường dẫn ảnh đúng với cấu trúc thư mục
    image_path = 'uploads/images/products/'  # Thay đổi đường dẫn này
    return render_template('admin/edit_product.html', 
                         product=product,
                         categories=categories,
                         image_path=image_path)

@app.route('/admin/delete_product/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_product(id):
    try:
        # Tìm sản phẩm
        product = Product.query.get_or_404(id)
        
        # Xóa các biến thể trước
        Variant.query.filter_by(product_id=id).delete()
        
        # Xóa các file ảnh
        if product.image_files:
            for image in product.image_files:
                try:
                    image_path = os.path.join(app.root_path, 'static/uploads/img', image)
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    print(f"Error deleting image {image}: {str(e)}")
        
        # Xóa sản phẩm
        db.session.delete(product)
        db.session.commit()
        
        flash('Sản phẩm đã được xóa thành công!', 'success')
        return jsonify({
            'success': True,
            'message': 'Sản phẩm đã được xóa thành công!'
         })
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting product: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        # Xử lý thanh toán
        pass
    return render_template('checkout.html')

@app.route('/posts')
def posts():
    posts = Post.query.all()
    return render_template('posts.html', posts=posts)

@app.route('/admin/posts', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        try:
            title = request.form['title']
            # Lấy nội dung HTML từ CKEditor
            content = request.form['content']
            
            # Xử lý file ảnh
            image_filename = None
            if 'image_file' in request.files:
                image_file = request.files['image_file']
                if image_file and image_file.filename:
                    image_filename = secure_filename(image_file.filename)
                    # Cập nhật đường dẫn lưu ảnh
                    image_path = os.path.join(app.root_path, 'static/uploads/images/posts')
                    os.makedirs(image_path, exist_ok=True)
                    image_file.save(os.path.join(image_path, image_filename))

            # Xử lý file video (nếu cần)
            video_filename = None
            if 'video_file' in request.files:
                video_file = request.files['video_file']
                if video_file and video_file.filename:
                    video_filename = secure_filename(video_file.filename)
                    video_path = os.path.join(app.root_path, 'static/uploads/video')
                    os.makedirs(video_path, exist_ok=True)
                    video_file.save(os.path.join(video_path, video_filename))

            # Tạo bài viết mới với nội dung HTML
            post = Post(
                title=title,
                content=content,  # Lưu trực tiếp HTML
                user_id=current_user.id,
                image_file=image_filename,
                video_file=video_filename
            )
            
            db.session.add(post)
            db.session.commit()
            flash('Bài viết đã được tạo thành công!', 'success')
            return redirect(url_for('blog'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            return redirect(url_for('new_post'))
            
    return render_template('admin/add_post.html')



@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
        
    if request.method == 'POST':
        try:
            post.title = request.form['title']
            post.content = request.form['content']  # Cập nhật nội dung HTML

            # Xử lý file ảnh mới
            if 'image_file' in request.files:
                image_file = request.files['image_file']
                if image_file and image_file.filename:
                    # Xóa ảnh cũ nếu có
                    if post.image_file:
                        old_image_path = os.path.join(app.root_path, 'static/img', post.image_file)
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                            
                    # Lưu ảnh mới
                    image_filename = secure_filename(image_file.filename)
                    image_path = os.path.join(app.root_path, 'static/img')
                    os.makedirs(image_path, exist_ok=True)
                    image_file.save(os.path.join(image_path, image_filename))
                    post.image_file = image_filename

            # Xử lý file video mới
            if 'video_file' in request.files:
                video_file = request.files['video_file']
                if video_file and video_file.filename:
                    # Xóa video cũ nếu có
                    if post.video_file:
                        old_video_path = os.path.join(app.root_path, 'static/video', post.video_file)
                        if os.path.exists(old_video_path):
                            os.remove(old_video_path)
                            
                    # Lưu video mới
                    video_filename = secure_filename(video_file.filename)
                    video_path = os.path.join(app.root_path, 'static/video')
                    os.makedirs(video_path, exist_ok=True)
                    video_file.save(os.path.join(video_path, video_filename))
                    post.video_file = video_filename

            db.session.commit()
            flash('Bài viết đã được cập nhật thành công!', 'success')
            return redirect(url_for('post', post_id=post.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            
    return render_template('admin/add_post.html', title='Cập nhật bài viết', post=post)

@app.route('/admin/post/<int:post_id>/delete', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_post(post_id):
    try:
        # Debug log
        print(f"\n=== Bắt đầu xóa bài viết ID: {post_id} ===")
        
        # Tìm bài viết
        post = Post.query.get_or_404(post_id)
        print(f"Đã tìm thấy bài viết: {post.title}")
        
        # Xóa file ảnh nếu có
        if post.image_file:
            try:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_file)
                print(f"Đường dẫn ảnh: {image_path}")
                if os.path.exists(image_path):
                    os.remove(image_path)
                    print("Đã xóa file ảnh")
            except Exception as e:
                print(f"Lỗi khi xóa file ảnh: {str(e)}")
                # Tiếp tục xóa bài viết ngay cả khi không xóa được ảnh
        
        # Lưu thông tin bài viết trước khi xóa
        title = post.title
        
        # Xóa bài viết
        db.session.delete(post)
        db.session.commit()
        
        print(f"Đã xóa bài viết thành công: {title}")
        flash(f'Bài viết "{title}" đã được xóa thành công!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Lỗi SQLAlchemy: {str(e)}")
        flash('Có lỗi xảy ra khi xóa bài viết trong database!', 'danger')
        

    
    finally:
        # Luôn redirect về trang quản lý
        return redirect(url_for('manage_posts'))




mail = Mail(app)
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Lấy dữ liệu từ form
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']

        try:
            # Gửi email
            send_email(name, email, message)
            flash('Cảm ơn bạn đã liên hệ. Chúng tôi sẽ phản hồi sớm nhất!', 'success')
        except Exception as e:
            # Báo lỗi nếu không gửi được email
            flash('Có lỗi xảy ra khi gửi email. Vui lòng thử lại sau.', 'danger')
            print(f"Lỗi: {e}")

        return redirect('/contact')
    
    return render_template('contact.html')

def send_email(name, email, message):
    msg = Message(
        subject=f'Liên hệ từ {name}',
        sender=app.config['MAIL_USERNAME'],
        recipients=['hoan0505200222@gmail.com']  # Thay bằng email bạn muốn nhận thông tin
    )
    msg.body = f"Người gửi: {name}\nEmail: {email}\n\nTin nhắn:\n{message}"
    mail.send(msg)


@app.route('/admin/manage_categories')
@login_required
@admin_required
def manage_categories():
    categories = Category.query.all()
    return render_template('admin/manage_categories.html', 
                         categories=categories,
                         active_page='categories')

@app.route('/admin/categories/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_category():
    if request.method == 'POST':
        name = request.form.get('name')
        
        # Kiểm tra tên danh mục không được trống
        if not name:
            flash('Tên danh mục không được để trống', 'danger')
            return redirect(url_for('add_category'))
            
        # Kiểm tra danh mục đã tồn tại chưa
        existing_category = Category.query.filter_by(name=name).first()
        if existing_category:
            flash('Danh mục này đã tồn tại', 'danger')
            return redirect(url_for('add_category'))
        
        try:
            new_category = Category(name=name)
            db.session.add(new_category)
            db.session.commit()
            flash('Đã thêm danh mục thành công', 'success')
            return redirect(url_for('manage_categories'))
        except Exception as e:
            db.session.rollback()
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            return redirect(url_for('add_category'))

    return render_template('admin/add_category.html')

@app.route('/admin/categories/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(id):
    category = Category.query.get_or_404(id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        
        if not name:
            flash('Tên danh mục không được để trống', 'danger')
            return redirect(url_for('edit_category', id=id))
        
        # Kiểm tra tên mới có trùng với danh mục khác không
        existing_category = Category.query.filter(
            Category.name == name, 
            Category.id != id
        ).first()
        
        if existing_category:
            flash('Danh mục này đã tồn tại', 'danger')
            return redirect(url_for('edit_category', id=id))
            
        try:
            category.name = name
            db.session.commit()
            flash('Đã cập nhật danh mục thành công', 'success')
            return redirect(url_for('manage_categories'))
        except Exception as e:
            db.session.rollback()
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            
    return render_template('admin/edit_category.html', category=category)

@app.route('/admin/categories/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_category(id):
    category = Category.query.get_or_404(id)
    
    # Kiểm tra xem danh mục có sản phẩm không
    if category.products:
        flash('Không thể xóa danh mục đang có sản phẩm', 'danger')
        return redirect(url_for('manage_categories'))
        
    try:
        db.session.delete(category)
        db.session.commit()
        flash('Đã xóa danh mục thành công', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
        
    return redirect(url_for('manage_categories'))

@app.route('/category/<int:category_id>')
def category(category_id):
    category = Category.query.get_or_404(category_id)
    products = Product.query.filter_by(category_id=category_id).all()
    return render_template('category.html', 
                         category=category, 
                         products=products)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    
    if not query:
        return render_template('search.html', products=[], query='')
    
    # Chỉ tìm theo tên và mô tả
    products = Product.query.filter(
        or_(
            Product.name.ilike(f'%{query}%'),
            Product.description.ilike(f'%{query}%')
        )
    ).all()
    
    products_by_category = {}
    for product in products:
        category = product.category
        if category not in products_by_category:
            products_by_category[category] = []
        products_by_category[category].append(product)
    
    return render_template('search.html', 
                         products_by_category=products_by_category,
                         query=query,
                         total_results=len(products))

from flask import render_template, request
from app import app
from models import Post
import re

@app.route('/posts/<string:slug>')
def view_post(slug):
    # Tìm bài viết theo slug
    post = Post.query.filter_by(slug=slug).first_or_404()
    
    # Lấy tất cả các thẻ <h2> trong nội dung bài viết
    headings = re.findall(r'<h2.*?>(.*?)</h2>', post.content)
    headings = [{'id': f'heading-{i+1}', 'text': text} for i, text in enumerate(headings)]

    # Lấy bài trước và sau
    prev_post = Post.query.filter(
        Post.id < post.id,
        Post.status == 'published'
    ).order_by(Post.id.desc()).first()

    next_post = Post.query.filter(
        Post.id > post.id,
        Post.status == 'published'
    ).order_by(Post.id.asc()).first()

    return render_template('post.html', 
                           post=post, 
                           headings=headings, 
                           prev_post=prev_post, 
                           next_post=next_post)
         
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bạn không có quyền truy cập trang này!', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    try:
        # Thống kê cơ bản
        order_count = Order.query.count()
        new_order_count = Order.query.filter_by(status='pending').count()
        product_count = Product.query.count()
        user_count = User.query.count()
        
        # Tính tổng doanh thu
        total_revenue = db.session.query(func.sum(Order.total_price))\
            .filter(Order.status == 'completed')\
            .scalar() or 0
        
        # Đơn hàng gần đây
        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
        
        # Thống kê doanh thu theo tháng
        current_year = datetime.utcnow().year
        monthly_revenue = db.session.query(
            func.strftime('%m', Order.created_at).label('month'),
            func.sum(Order.total_price).label('revenue')
        ).filter(
            Order.status == 'completed',
            func.strftime('%Y', Order.created_at) == str(current_year)
        ).group_by('month').all()
        
        # Đảm bảo dữ liệu không None trước khi chuyển thành JSON
        revenue_labels = [f'Tháng {m[0]}' for m in monthly_revenue] if monthly_revenue else []
        revenue_data = [float(m[1] or 0) for m in monthly_revenue] if monthly_revenue else []
        
        # Top sản phẩm bán chạy
        top_products = db.session.query(
            Product.name,
            func.sum(OrderItem.quantity).label('total_sold')
        ).join(OrderItem).join(Order).filter(
            Order.status == 'completed'
        ).group_by(Product.id).order_by(
            func.sum(OrderItem.quantity).desc()
        ).limit(5).all()
        
        # Đảm bảo dữ liệu không None
        product_labels = [p[0] for p in top_products] if top_products else []
        product_data = [int(p[1] or 0) for p in top_products] if top_products else []
        
        # Debug: In ra dữ liệu trước khi chuyển thành JSON
        print("Revenue Labels:", revenue_labels)
        print("Revenue Data:", revenue_data)
        print("Product Labels:", product_labels)
        print("Product Data:", product_data)
        
        return render_template('admin/dashboard.html',
                             active_page='dashboard',
                             order_count=order_count,
                             new_order_count=new_order_count,
                             product_count=product_count,
                             user_count=user_count,
                             total_revenue=total_revenue,
                             recent_orders=recent_orders,
                             revenue_labels=json.dumps(revenue_labels, ensure_ascii=False),
                             revenue_data=json.dumps(revenue_data),
                             product_labels=json.dumps(product_labels, ensure_ascii=False),
                             product_data=json.dumps(product_data))
                             
    except Exception as e:
        print(f"Error in dashboard: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Có lỗi xảy ra khi tải trang dashboard', 'error')
        return redirect(url_for('home'))

@app.route('/admin/order/<int:order_id>/details')
@login_required
@admin_required
def get_order_details(order_id):
    order = Order.query.get_or_404(order_id)
    
    items = []
    for item in order.order_items:
        items.append({
            'product_name': item.product.name,
            'variant_name': item.variant.name if item.variant else 'N/A',
            'price': item.price,
            'quantity': item.quantity,
            'subtotal': item.subtotal
        })
    
    return jsonify({
        'id': order.id,
        'shipping_name': order.shipping_name,
        'shipping_phone': order.shipping_phone,
        'shipping_address': order.shipping_address,
        'payment_method': order.payment_method,
        'status': order.status_display,
        'created_at': order.created_at.strftime('%d-%m-%Y %H:%M'),
        'total_price': order.total_price,
        'items': items
    })

@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
def admin_update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    
    if data.get('status') in ['pending', 'processing', 'completed', 'cancelled']:
        order.status = data['status']
        order.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Trạng thái không hợp lệ'})

@app.route('/admin/orders/export/<format>')
@login_required
@admin_required
def export_orders(format):
    orders = Order.query.order_by(Order.created_at.desc()).all()
    
    if format == 'excel':
        # Implement Excel export
        pass
    elif format == 'pdf':
        # Implement PDF export
        pass
    
    return redirect(url_for('manage_orders'))

@app.route('/admin/manage_posts')
@login_required
@admin_required
def manage_posts():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('admin/manage_posts.html', 
                         posts=posts,
                         active_page='posts')

@app.route('/admin/manage_orders')
@login_required
@admin_required
def manage_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin/manage_orders.html', 
                         orders=orders,
                         active_page='orders')

@app.route('/admin/manage_users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/manage_users.html', 
                         users=users,
                         active_page='users')

@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
def user_update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['pending', 'completed', 'cancelled']:
        order.status = new_status
        db.session.commit()
        flash(f'Đã cập nhật trạng thái đơn hàng thành {new_status}', 'success')
    return redirect(url_for('manage_orders'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if current_user.id == user_id:
        flash('Không thể xóa tài khoản của chính mình!', 'danger')
        return redirect(url_for('manage_users'))
        
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Đã xóa người dùng thành công!', 'success')
    return redirect(url_for('manage_users'))

@app.route('/admin/user/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        
        # Kiểm tra username đã tồn tại
        if User.query.filter_by(username=username).first():
            flash('Tên người dùng đã tồn tại!', 'danger')
            return redirect(url_for('manage_users'))
            
        # Kiểm tra email đã tồn tại
        if User.query.filter_by(email=email).first():
            flash('Email đã tồn tại!', 'danger')
            return redirect(url_for('manage_users'))
        
        # Tạo user mới
        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            is_admin=is_admin
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Đã thêm người dùng thành công!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Có lỗi xảy ra khi thêm người dùng!', 'danger')
            print(str(e))
            
        return redirect(url_for('manage_users'))
        
    return render_template('admin/add_user.html', active_page='users')

@app.route('/blog')
@app.route('/blog/page/<int:page>')
def blog(page=1):
    per_page = 9  # Số bài viết mỗi trang
    
    # Debug: In ra tất cả bài viết trong database
    all_posts = Post.query.all()
    print(f"Tổng số bài viết trong DB: {len(all_posts)}")
    for p in all_posts:
        print(f"ID: {p.id}, Title: {p.title}")
    
    # Lấy các bài viết đã publish và sắp xếp theo thời gian mới nhất
    posts = Post.query\
        .order_by(Post.date_posted.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Debug: In thông tin về các bài viết được lấy
    print(f"Số bài viết hiển thị: {len(posts.items)}")
    for post in posts.items:
        print(f"""
        Bài viết:
        - ID: {post.id}
        - Tiêu đề: {post.title}
        - Ngày đăng: {post.date_posted}
        """)
    
    return render_template('blog.html',
                         title='Blog',
                         posts=posts.items,
                         page=page,
                         pages=posts.pages)

# Định nghĩa các đường dẫn upload
IMAGE_UPLOADS = os.path.join(app.root_path, 'static', 'uploads', 'images')
UPLOAD_FOLDERS = {
    'products': os.path.join(app.root_path, 'static', 'uploads', 'images', 'products'),
    'variants': os.path.join(app.root_path, 'static', 'uploads', 'images', 'variants'),
    'posts': os.path.join(app.root_path, 'static', 'uploads', 'images', 'posts')
}

def create_upload_folders():
    """Tạo các thư mục upload nếu chưa tồn tại"""
    try:
        # Tạo thư mục gốc
        base_path = os.path.join(app.root_path, 'static', 'uploads', 'images')
        os.makedirs(base_path, exist_ok=True)
        print(f"Thư mục gốc: {base_path}")
        
        # Tạo các thư mục con
        for folder_name, folder_path in UPLOAD_FOLDERS.items():
            os.makedirs(folder_path, exist_ok=True)
            print(f"Đã tạo thư mục {folder_name}: {folder_path}")
            
            # Kiểm tra quyền ghi
            if os.access(folder_path, os.W_OK):
                print(f"Thư mục {folder_name} có quyền ghi")
            else:
                print(f"CẢNH BÁO: Thư mục {folder_name} không có quyền ghi")
                
            # Liệt kê nội dung thư mục
            files = os.listdir(folder_path)
            print(f"Nội dung thư mục {folder_name}: {files}")
            
    except Exception as e:
        print(f"Lỗi khi tạo thư mục: {str(e)}")

def save_image(file, subfolder):
    try:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"
            
            # Đường dẫn thư mục upload
            upload_folder = os.path.join(
                app.root_path,
                'static',
                'uploads',
                'images',
                subfolder
            )
            
            # Tạo thư mục nếu chưa tồn tại
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            print(f"Đã lưu file tại: {file_path}")
            return filename
            
    except Exception as e:
        print(f"Lỗi khi lưu file: {str(e)}")
        return None

# Thêm hàm kiểm tra và tạo thư mục
def ensure_upload_folders():
    """Đảm bảo các thư mục upload tồn tại"""
    base_path = os.path.join(app.root_path, 'static', 'uploads', 'images')
    folders = ['products', 'variants', 'posts']
    
    for folder in folders:
        folder_path = os.path.join(base_path, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"Đã tạo thư mục: {folder_path}")

# Gọi hàm khi khởi động app
_upload_folders_created = False

@app.before_request
def setup_folders():
    global _upload_folders_created
    if not _upload_folders_created:
        ensure_upload_folders()
        _upload_folders_created = True

# Cập nhật route upload ảnh sản phẩm
@app.route('/admin/product/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_product_image():
    try:
        file = request.files.get('image')
        image_path = save_image(file, 'products')
        if image_path:
            return jsonify({
                'success': True,
                'url': url_for('static', filename=image_path)
            })
        return jsonify({
            'success': False,
            'message': 'Lỗi khi upload ảnh'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

# Cập nhật route upload ảnh bài viết
@app.route('/admin/post/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_post_image():
    try:
        # Xử lý upload từ URL
        image_url = request.form.get('url')
        if image_url:
            filename = download_image_from_url(image_url, UPLOAD_FOLDERS['posts'])
            if filename:
                image_path = os.path.join('uploads', 'images', 'posts', filename)
                return jsonify({
                    'uploaded': 1,
                    'url': url_for('static', filename=image_path),
                    'fileName': filename
                })

        # Xử lý upload file
        file = request.files.get('upload')
        image_path = save_image(file, 'posts')
        if image_path:
            return jsonify({
                'uploaded': 1,
                'url': url_for('static', filename=f'uploads/images/posts/{image_path}'),
                'fileName': os.path.basename(image_path)
            })

        return jsonify({
            'uploaded': 0,
            'error': {'message': 'Không thể upload ảnh'}
        })

    except Exception as e:
        return jsonify({
            'uploaded': 0,
            'error': {'message': str(e)}
        })

# Cập nhật route upload ảnh biến thể
@app.route('/admin/variant/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_variant_image():
    try:
        file = request.files.get('image')
        image_path = save_image(file, 'variants')
        if image_path:
            return jsonify({
                'success': True,
                'url': url_for('static', filename=image_path)
            })
        return jsonify({
            'success': False,
            'message': 'Lỗi khi upload ảnh'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

def delete_image(image_path):
    """
    Hàm chung để xóa file ảnh
    - image_path: đường dẫn tương đối của file trong thư mục static
    """
    try:
        if image_path:
            full_path = os.path.join(app.root_path, 'static', image_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
    except Exception as e:
        print(f"Lỗi khi xóa ảnh: {str(e)}")
    return False

@app.route('/chinh-sach')
def policies():
    return render_template('policies.html')

@app.route('/chinh-sach-bao-mat')
def privacy_policy():
    return render_template('privacy.html', current_time=datetime.now())

@app.route('/chinh-sach-van-chuyen')
def shipping_policy():
    return render_template('shipping.html', current_time=datetime.now())

@app.route('/chinh-sach-doi-tra')
def return_policy():
    return render_template('return.html', current_time=datetime.now())

@app.route('/chinh-sach-thanh-toan')
def payment_policy():
    return render_template('payment.html', current_time=datetime.now())

@app.context_processor
def inject_categories():
    def get_categories():
        return Category.query.all()
    return dict(categories=get_categories())

def download_image_from_url(url, upload_folder):
    """
    Tải ảnh từ URL và lưu vào thư mục upload
    Returns: tên file đã lưu hoặc None nếu có lỗi
    """
    try:
        # Tải ảnh từ URL
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return None
            
        # Lấy tên file từ URL hoặc tạo tên ngẫu nhiên
        filename = os.path.basename(url)
        if not filename or not allowed_file(filename):
            # Tạo tên file ngẫu nhiên với phần mở rộng từ Content-Type
            ext = response.headers.get('content-type', '').split('/')[-1]
            if ext in ['jpeg', 'jpg', 'png', 'gif']:
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            else:
                return None
                
        # Đảm bảo tên file an toàn
        filename = secure_filename(filename)
        
        # Tạo đường dẫn đầy đủ và lưu file
        file_path = os.path.join(upload_folder, filename)
        os.makedirs(upload_folder, exist_ok=True)
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        return filename
        
    except Exception as e:
        print(f"Lỗi khi tải ảnh từ URL: {str(e)}")
        return None

def verify_image_path(image_name, subfolder):
    """Kiểm tra và trả về đường dẫn ảnh hợp lệ"""
    if not image_name:
        return None
        
    # Kiểm tra các vị trí có thể có ảnh
    possible_paths = [
        os.path.join(app.root_path, 'static', 'uploads', 'images', subfolder, image_name),
        os.path.join(app.root_path, 'static', 'uploads', 'img', image_name),
        os.path.join(app.root_path, 'static', 'img', image_name)
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            # Trả về đường dẫn tương đối từ thư mục static
            return os.path.join('uploads', 'images', subfolder, image_name)
            
    return 'img/default-variant.jpg'  # Trả về ảnh mặc định nếu không tìm thấy



@app.route('/process_payment', methods=['POST'])
def process_payment():
    shipping_name = request.form['name']
    shipping_phone = request.form['phone']
    shipping_address = request.form['address']
    payment_method = request.form['payment_method']
    total_price = calculate_total_price()  # Hàm giả định để tính tổng giá

    # Tạo đơn hàng mới
    new_order = Order(
        user_id=current_user.id,  # Giả định bạn có thông tin người dùng hiện tại
        shipping_name=shipping_name,
        shipping_phone=shipping_phone,
        shipping_address=shipping_address,
        total_price=total_price,
        payment_method=payment_method
    )

    # Lưu đơn hàng vào cơ sở dữ liệu
    db.session.add(new_order)
    db.session.commit()
    
    # Gửi tin nhắn đến Telegram
    chat_id = '6580174494'  # Thay thế bằng chat ID của bạn

    # Tạo thông điệp chi tiết cho từng sản phẩm trong giỏ hàng
    cart_items = session.get('cart', [])
    message = f"Thông tin đơn hàng:\nTên: {shipping_name}\nSố điện thoại: {shipping_phone}\nĐịa chỉ: {shipping_address}\nPhương thức thanh toán: {payment_method}\nTổng giá: {total_price} ₫\n\nChi tiết sản phẩm:\n"

    for item in cart_items:
        product = Product.query.get(item['product_id'])
        variant = Variant.query.get(item['variant_id'])
        quantity = item['quantity']
        if product and variant:
            message += f"Sản phẩm: {product.name}, Biến thể: {variant.name}, Số lượng: {quantity}\n"

    result = send_message_to_telegram(chat_id, message)

    if result.get("ok"):
        flash('Thông tin đơn hàng đã được gửi thành công!', 'success')
    else:
        flash('Có lỗi xảy ra khi gửi thông tin!', 'danger')

    return redirect(url_for('cart'))  # Quay lại trang giỏ hàng

def calculate_total_price():
    # Giả định bạn có một danh sách các sản phẩm trong giỏ hàng
    total = 0
    for item in session['cart']:
        product = Product.query.get(item['product_id'])
        variant = Variant.query.get(item['variant_id'])
        if product and variant:
            total += variant.value * item['quantity']
    return total

def send_message_to_telegram(chat_id, message):
    TOKEN = '7234592257:AAGyRzMsMS2jlHWGpWKihI6jfcDFsPPv6hw'  # Thay thế bằng token của bạn
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=data)
    return response.json()
@app.route('/aboutus')
def aboutus():
    return render_template('aboutus.html',current_time=datetime.now())

@app.route('/chinh-sach-affiliate-tobe')
def affiliatepolicy():
    return render_template('affiliatepolicy.html',current_time=datetime.now())

@app.route('/admin/posts/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)

    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        # ... (Cập nhật các trường khác của bài viết nếu cần) ...

        db.session.commit()
        flash('Bài viết đã được cập nhật!', 'success')
        return redirect(url_for('view_post', slug=post.slug))

    return render_template('admin/edit_post.html', post=post)