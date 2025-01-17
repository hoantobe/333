// Hàm hiển thị thông báo
function showNotification(message, type = 'success') {
    // Sử dụng Toastr
    toastr[type](message, '', {
        "closeButton": true,
        "progressBar": true,
        "positionClass": "toast-top-right",
        "timeOut": "5000"
    });
}

// Xử lý xóa sản phẩm
function deleteProduct(id) {
    if (confirm('Bạn có chắc chắn muốn xóa sản phẩm này?')) {
        fetch(`/admin/delete_product/${id}`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(data.message, 'success');
                // Thêm hiệu ứng fade out trước khi xóa
                const element = document.querySelector(`#product-${id}`);
                element.style.transition = 'opacity 0.5s ease';
                element.style.opacity = '0';
                setTimeout(() => element.remove(), 500);
            } else {
                showNotification(data.message, 'error');
            }
        })
        .catch(error => {
            showNotification('Có lỗi xảy ra khi xóa sản phẩm', 'error');
        });
    }
}

// Xử lý xóa bài viết
function deletePost(id) {
    if (confirm('Bạn có chắc chắn muốn xóa bài viết này?')) {
        fetch(`/admin/post/${id}/delete`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(data.message, 'success');
                const element = document.querySelector(`#post-${id}`);
                element.style.transition = 'opacity 0.5s ease';
                element.style.opacity = '0';
                setTimeout(() => element.remove(), 500);
            } else {
                showNotification(data.message, 'error');
            }
        })
        .catch(error => {
            showNotification('Có lỗi xảy ra khi xóa bài viết', 'error');
        });
    }
}

// Xử lý xóa người dùng
function deleteUser(id) {
    if (confirm('Bạn có chắc chắn muốn xóa người dùng này?')) {
        fetch(`/admin/user/${id}/delete`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(data.message, 'success');
                const element = document.querySelector(`#user-${id}`);
                element.style.transition = 'opacity 0.5s ease';
                element.style.opacity = '0';
                setTimeout(() => element.remove(), 500);
            } else {
                showNotification(data.message, 'error');
            }
        })
        .catch(error => {
            showNotification('Có lỗi xảy ra khi xóa người dùng', 'error');
        });
    }
} 
