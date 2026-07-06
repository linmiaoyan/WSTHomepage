document.addEventListener('DOMContentLoaded', function() {
    // 表单验证
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (form.hasAttribute('novalidate')) {
                return;
            }
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Bootstrap btn-check 已通过 label[for] 关联 radio，无需再手动绑定 click
    // 自动隐藏提示消息
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s ease';
            setTimeout(() => alert.remove(), 500);
        }, 3000);
    });
}); 