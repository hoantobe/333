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



# Gọi hàm khi khởi động app


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
                             product_id=product_id,
                             data=data )
    except Exception as template_error:
        print(f"Template error: {str(template_error)}")
        raise
                             
@app.route('/cart')
@login_required
def cart():
    cart_items = session.get('cart', [])
    total_price = sum(item['price'] * item['quantity'] for item in cart_items if 'price' in item)
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

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
        query = query.order_by(Product.discounted_price.asc() if Product.discounted_price else Product.original_price.asc())
    elif sort == 'price-desc':
        query = query.order_by(Product.discounted_price.desc() if Product.discounted_price else Product.original_price.desc())
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

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    try:
        data = request.get_json()
        variant_id = data.get('variant')
        quantity = data.get('quantity')

        if not variant_id:
            return jsonify({'success': False, 'message': 'Không có biến thể được chọn'})

        if not quantity or not isinstance(quantity, int) or quantity <= 0:
            return jsonify({'success': False, 'message': 'Số lượng không hợp lệ'})

        quantity = int(quantity)

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
                'price': variant.value,
                'image': variant.image_file if variant.image_file else 'default-variant.jpg'
            })

        session['cart'] = cart
        session.modified = True

        return jsonify({'success': True, 'message': 'Đã thêm vào giỏ hàng thành công!'})

    except Exception as e:
        print(f"Error in add_to_cart: {str(e)}")  # Log lỗi để debug
        return jsonify({'success': False, 'message': 'Có lỗi xảy ra khi thêm vào giỏ hàng'})


@app.route('/remove_from_cart/<int:product_id>/<int:variant_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id, variant_id):
    if 'cart' in session:
        session['cart'] = [item for item in session['cart'] 
                          if not (item['product_id'] == product_id and item['variant_id'] == variant_id)]
        session.modified = True
        flash('Sản phẩm đã được xóa khỏi giỏ hàng!', 'success')
    return redirect(url_for('cart'))



@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = 'remember' in request.form  # Kiểm tra nếu người dùng chọn "Nhớ mật khẩu"

        user = User.query.filter_by(username=username).first()
        if user and password:
            login_user(user, remember=remember)
            flash('Đăng nhập thành công!', 'success')
            return jsonify({'success': True, 'redirect_url': url_for('home')})
        else:
            return jsonify({'success': False, 'message': 'Sai tài khoản hoặc mật khẩu!'})
    return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ!'})

@app.route('/logout')
def logout():
    logout_user()
    session.pop('user', None)
    flash('Bạn đã đăng xuất thành công!', 'success')
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

        flash('Bạn đã đăng kí thành công!', 'success')
        return redirect(url_for('home', show_login_modal=True))

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
            # Lấy thông tin cơ bản của sản phẩm
            name = request.form.get('name')
            category_id = request.form.get('category')
            original_price = request.form.get('original_price')
            discounted_price = request.form.get('discounted_price') or None
            description = request.form.get('description')

            # Xử lý danh mục mới nếu có
            new_category_name = request.form.get('new_category')
            if new_category_name:
                new_category = Category(name=new_category_name)
                db.session.add(new_category)
                db.session.flush()  # Để lấy ID của danh mục mới
                category_id = new_category.id

            # Xử lý upload hình ảnh sản phẩm
            image_urls = []
            if 'image_files' in request.files:
                for file in request.files.getlist('image_files'):
                    image_url = save_image(file, 'products')  # Hàm lưu ảnh
                    if image_url:
                        image_urls.append(image_url)

            # Tạo sản phẩm mới
            new_product = Product(
                name=name,
                original_price=float(original_price),
                discounted_price=float(discounted_price) if discounted_price else None,
                description=description,
                category_id=int(category_id),
                image_files=image_urls
            )
            db.session.add(new_product)
            db.session.flush()  # Để lấy `id` của sản phẩm mới

            # Xử lý biến thể
            variant_names = request.form.getlist('variant_name[]')
            variant_prices = request.form.getlist('variant_price[]')
            variant_images = request.files.getlist('variant_image[]')

            for i, variant_name in enumerate(variant_names):
                # Kiểm tra xem có giá trị tương ứng hay không
                variant_price = variant_prices[i] if i < len(variant_prices) else None
                variant_image = variant_images[i] if i < len(variant_images) else None

                # Upload ảnh biến thể nếu có
                variant_image_url = save_image(variant_image, 'variants') if variant_image else None

                # Thêm biến thể mới
                new_variant = Variant(
                    name=variant_name,
                    value=float(variant_price),
                    image_file=variant_image_url,
                    product_id=new_product.id
                )
                db.session.add(new_variant)

            db.session.commit()
            flash('Sản phẩm đã được thêm thành công!', 'success')
            return redirect(url_for('manage_products'))

        except Exception as e:
            db.session.rollback()
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
    
    if request.method == 'POST':
        try:
            # Cập nhật thông tin cơ bản
            product.name = request.form.get('name')
            product.price = float(request.form.get('price'))
            product.description = request.form.get('description')
            product.category_id = int(request.form.get('category'))

            # Xử lý ảnh sản phẩm mới (upload lên Cloudinary)
            if 'image_files' in request.files:
                new_images = request.files.getlist('image_files')
                for image in new_images:
                    if image and allowed_file(image.filename):
                        upload_result = cloudinary.uploader.upload(image)  # Tải ảnh lên Cloudinary
                        if upload_result:
                            if not product.image_files:
                                product.image_files = []
                            product.image_files.append(upload_result['public_id'])
                            print(f"Đã thêm ảnh mới từ Cloudinary: {upload_result['public_id']}")

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
                        
                        # Cập nhật ảnh nếu có (upload lên Cloudinary)
                        if image and image.filename:
                            upload_result = cloudinary.uploader.upload(image)  # Tải ảnh lên Cloudinary
                            if upload_result:
                                variant.image_file = upload_result['public_id']
                                print(f"Đã cập nhật ảnh biến thể từ Cloudinary: {upload_result['public_id']}")
                    else:
                        # Thêm biến thể mới
                        variant = Variant(
                            name=name,
                            value=float(value),
                            product_id=product.id
                        )
                        if image and image.filename:
                            upload_result = cloudinary.uploader.upload(image)  # Tải ảnh lên Cloudinary
                            if upload_result:
                                variant.image_file = upload_result['public_id']
                                print(f"Đã thêm ảnh cho biến thể mới từ Cloudinary: {upload_result['public_id']}")
                        db.session.add(variant)
                        print(f"Đã thêm biến thể mới: {name}")

            db.session.commit()
            flash('Sản phẩm đã được cập nhật thành công!', 'success')
            return redirect(url_for('manage_products'))

        except Exception as e:
            db.session.rollback()
            flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
            return redirect(url_for('edit_product', id=id))

    # GET request
    categories = Category.query.all()
    # Hiển thị ảnh cũ từ Cloudinary
    image_urls = product.image_files  # Các URL ảnh từ Cloudinary
    return render_template('admin/edit_product.html', 
                         product=product,
                         categories=categories,
                         image_urls=image_urls)


@app.route('/admin/delete_product/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_product(id):
    try:
        # Tìm sản phẩm
        product = Product.query.get_or_404(id)
        
        # Xóa các biến thể trước
        Variant.query.filter_by(product_id=id).delete()
        
        # Xóa các file ảnh từ Cloudinary
        if product.image_files:
            for image in product.image_files:
                try:
                    cloudinary.uploader.destroy(image)
                    print(f"Đã xóa file ảnh từ Cloudinary: {image}")
                except Exception as e:
                    print(f"Lỗi khi xóa file ảnh từ Cloudinary: {str(e)}")
        
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
        print(f"Lỗi khi xóa sản phẩm: {str(e)}")
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
            content = request.form['content']  # Lấy nội dung HTML từ CKEditor
            
            # Xử lý ảnh
            image_url = None
            if 'image_file' in request.files:
                image_file = request.files['image_file']
                if image_file and allowed_file(image_file.filename):
                    # Tải ảnh lên Cloudinary
                    upload_result = cloudinary.uploader.upload(image_file, folder='posts')
                    image_url = upload_result.get('secure_url')
            
            # Xử lý video
            video_url = None
            if 'video_file' in request.files:
                video_file = request.files['video_file']
                if video_file and allowed_file(video_file.filename):
                    # Tải video lên Cloudinary
                    upload_result = cloudinary.uploader.upload(video_file, folder='videos', resource_type='video')
                    video_url = upload_result.get('secure_url')
            
            # Tạo bài viết mới
            post = Post(
                title=title,
                content=content,  # Lưu nội dung HTML
                user_id=current_user.id,
                image_url=image_url,
                video_url=video_url
            )
            
            db.session.add(post)
            db.session.commit()
            flash('Bài viết đã được tạo thành công!', 'success')
            return redirect(url_for('posts'))
        
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
                    # Xóa ảnh cũ từ Cloudinary nếu có
                    if post.image_file:
                        cloudinary.uploader.destroy(post.image_file)

                    # Tải ảnh mới lên Cloudinary
                    upload_result = cloudinary.uploader.upload(image_file)
                    post.image_file = upload_result['public_id']

            # Xử lý file video mới
            if 'video_file' in request.files:
                video_file = request.files['video_file']
                if video_file and video_file.filename:
                    # Xóa video cũ từ Cloudinary nếu có
                    if post.video_file:
                        cloudinary.uploader.destroy(post.video_file, resource_type='video')

                    # Tải video mới lên Cloudinary
                    upload_result = cloudinary.uploader.upload(video_file, resource_type='video')
                    post.video_file = upload_result['public_id']

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
        
        # Xóa file ảnh từ Cloudinary nếu có
        if post.image_file:
            try:
                cloudinary.uploader.destroy(post.image_file)
                print("Đã xóa file ảnh từ Cloudinary")
            except Exception as e:
                print(f"Lỗi khi xóa file ảnh từ Cloudinary: {str(e)}")
        
        # Xóa file video từ Cloudinary nếu có
        if post.video_file:
            try:
                cloudinary.uploader.destroy(post.video_file, resource_type='video')
                print("Đã xóa file video từ Cloudinary")
            except Exception as e:
                print(f"Lỗi khi xóa file video từ Cloudinary: {str(e)}")
        
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
            func.month(Order.created_at).label('month'),
            func.sum(Order.total_price).label('revenue')
        ).filter(
            Order.status == 'completed',
            func.year(Order.created_at) == current_year
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
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name='dwkkugzxr',
    api_key='668853365344795',
    api_secret='M7NtkNjdkMrLHAxKh2IeyrRMfxQ'
)

def save_image(file, folder):
    try:
        if file and allowed_file(file.filename):
            # Upload file lên Cloudinary
            upload_result = cloudinary.uploader.upload(file, folder=folder)
            return upload_result['secure_url']  # Trả về URL của ảnh trên Cloudinary
    except Exception as e:
        print(f"Lỗi khi upload lên Cloudinary: {str(e)}")
        return None
from cloudinary.utils import cloudinary_url
@app.context_processor
def utility_processor():
    def get_cloudinary_url(public_id):
        return cloudinary_url(public_id)[0]
    return dict(cloudinary_url=get_cloudinary_url)

# Cập nhật route upload ảnh sản phẩm
@app.route('/admin/product/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_product_image():
    try:
        file = request.files.get('image')
        image_url = save_image(file, 'products')  # Sử dụng hàm save_image đã sửa
        if image_url:  # Lấy URL từ Cloudinary
            return jsonify({
                'success': True,
                'url': image_url  # Trả về URL trực tiếp từ Cloudinary
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
UPLOAD_FOLDERS = {
    'products': os.path.join(app.root_path, 'static', 'uploads', 'images', 'products'),
    'variants': os.path.join(app.root_path, 'static', 'uploads', 'images', 'variants'),
    'categories': os.path.join(app.root_path, 'static', 'uploads', 'images', 'categories')
}

@app.route('/admin/post/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_post_image():
    try:
        # Xử lý upload từ URL và tải lên Cloudinary
        image_url = request.form.get('url')
        if image_url:
            # Tải ảnh từ URL và upload trực tiếp lên Cloudinary
            image_url = upload_image_to_cloudinary(image_url)  # Truyền URL trực tiếp cho Cloudinary
            if image_url:
                return jsonify({
                    'uploaded': 1,
                    'url': image_url,  # URL từ Cloudinary
                    'fileName': image_url.split('/')[-1]  # Lấy tên file từ URL
                })

        # Xử lý upload file và tải lên Cloudinary
        file = request.files.get('upload')
        if file and allowed_file(file.filename):
            image_url = upload_image_to_cloudinary(file)  # Tải ảnh lên Cloudinary
            if image_url:
                return jsonify({
                    'uploaded': 1,
                    'url': image_url,  # URL từ Cloudinary
                    'fileName': file.filename
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


def upload_image_to_cloudinary(file):
    try:
        # Nếu file là ảnh tải lên Cloudinary
        upload_result = cloudinary.uploader.upload(file)
        return upload_result['secure_url']  # Lấy URL ảnh đã upload lên Cloudinary
    except Exception as e:
        print(f"Lỗi khi tải ảnh lên Cloudinary: {str(e)}")
        return None

# Cập nhật route upload ảnh biến thể
@app.route('/admin/variant/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_variant_image():
    try:
        file = request.files.get('image')
        image_url = save_image(file, 'variants')  # Upload lên Cloudinary và lấy URL
        if image_url:
            return jsonify({
                'success': True,
                'url': image_url  # Trả về URL trực tiếp từ Cloudinary
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
def delete_image(public_id):
    """
    Hàm chung để xóa file ảnh
    - image_path: đường dẫn tương đối của file trong thư mục static
    """
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result['result'] == 'ok'
    except Exception as e:
        print(f"Lỗi khi xóa ảnh trên Cloudinary: {str(e)}")
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

@app.route('/buy_now/<int:product_id>', methods=['POST'])
@login_required
def buy_now(product_id):
    try:
        data = request.get_json()
        variant_id = data.get('variant')
        quantity = data.get('quantity')

        if not variant_id:
            return jsonify({'success': False, 'message': 'Vui lòng chọn biến thể!'})

        if not quantity or not isinstance(quantity, int) or quantity <= 0:
            return jsonify({'success': False, 'message': 'Số lượng không hợp lệ!'})

        # Cập nhật giỏ hàng
        session['cart'] = [{
            'product_id': product_id,
            'variant_id': int(variant_id),
            'quantity': quantity,
        }]
        session.modified = True

        return jsonify({'success': True, 'redirect_url': url_for('checkout')})

    except Exception as e:
        print(f"Lỗi mua ngay: {e}")
        return jsonify({'success': False, 'message': 'Có lỗi xảy ra!'})
