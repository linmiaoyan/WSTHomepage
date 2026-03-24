"""
FastAPI主应用
"""
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pathlib import Path
import config

from app.sessions import (
    admin_sessions,
    teacher_sessions,
    verify_admin_session,
    create_admin_session,
    remove_admin_session,
    verify_teacher_session,
    create_teacher_session,
    remove_teacher_session,
)

# 创建FastAPI应用
app = FastAPI(
    title="教师数据自填系统",
    description="教师个人信息数据库管理系统",
    version="1.0.0"
)

# 添加请求验证错误处理
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """处理请求验证错误，返回更友好的错误信息"""
    errors = []
    for error in exc.errors():
        field = '.'.join(str(loc) for loc in error.get('loc', []))
        msg = error.get('msg', '')
        errors.append(f"{field}: {msg}")
    return JSONResponse(
        status_code=422,
        content={"detail": errors if len(errors) > 1 else (errors[0] if errors else "请求数据验证失败")}
    )

# 挂载静态文件
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 注册路由
from app.routers import teachers, templates, tasks, questionnaires
from app.routers import seals
from app.routers import vl
from app.routers.import_router import router as import_router
from app.database import get_db

app.include_router(teachers.router)
app.include_router(templates.router)
app.include_router(tasks.router)
app.include_router(questionnaires.router)
app.include_router(seals.router)
app.include_router(vl.router)
app.include_router(import_router)


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """首页 - 重定向到查询页面"""
    return RedirectResponse(url="/query")


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """管理员登录页面"""
    return_url = request.query_params.get("return_url", "/admin")
    # 转义所有CSS和JavaScript中的花括号，只保留需要插入变量的地方
    login_html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>管理员登录</title>
        <link href="/static/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .login-card {{
                max-width: 400px;
                width: 100%;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }}
            .card-header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 15px 15px 0 0 !important;
            }}
        </style>
    </head>
    <body>
        <div class="card login-card">
            <div class="card-header text-center">
                <h4>管理员登录</h4>
            </div>
            <div class="card-body">
                <form id="login-form">
                    <div class="mb-3">
                        <label for="password" class="form-label">管理员密码</label>
                        <input type="password" class="form-control" id="password" required>
                    </div>
                    <div id="error-message" class="alert alert-danger" style="display: none;"></div>
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary">登录</button>
                    </div>
                </form>
            </div>
        </div>
        <script>
            document.getElementById('login-form').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const password = document.getElementById('password').value;
                const response = await fetch('/admin/login', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{password: password}})
                }});
                if (response.ok) {{
                    const data = await response.json();
                    localStorage.setItem('admin_token', data.token);
                    const returnUrl = new URLSearchParams(window.location.search).get('return_url') || '{return_url}';
                    window.location.href = returnUrl;
                }} else {{
                    const error = await response.json();
                    const errorDiv = document.getElementById('error-message');
                    errorDiv.textContent = error.detail || '登录失败';
                    errorDiv.style.display = 'block';
                }}
            }});
        </script>
    </body>
    </html>
    """
    return login_html


@app.post("/admin/login")
async def admin_login(request: Request):
    """管理员登录验证"""
    from pydantic import BaseModel
    
    class LoginRequest(BaseModel):
        password: str
    
    try:
        data = await request.json()
        login_req = LoginRequest(**data)
        
        if login_req.password == config.ADMIN_PASSWORD:
            token = create_admin_session()
            from fastapi.responses import JSONResponse
            response = JSONResponse({"token": token, "message": "登录成功"})
            response.set_cookie(key="admin_token", value=token, httponly=True, max_age=86400)  # 24小时
            return response
        raise HTTPException(status_code=401, detail="密码错误")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"登录失败: {str(e)}")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """管理员页面（需要登录）"""
    # 从请求头或localStorage获取token（前端会通过header传递）
    token = request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")
    
    # 如果没有token，检查URL参数（用于首次登录后的跳转）
    if not token:
        token = request.query_params.get("token")
    
    if not verify_admin_session(token):
        return RedirectResponse(url="/admin/login")
    
    html_file = Path(__file__).parent.parent / "templates" / "index.html"
    if html_file.exists():
        html_content = html_file.read_text(encoding="utf-8")
        # 注入token到localStorage
        html_content = html_content.replace(
            '<script src="/static/js/main.js"></script>',
            f'''<script>
                localStorage.setItem('admin_token', '{token}');
            </script>
            <script src="/static/js/main.js"></script>'''
        )
        return html_content
    return """
    <html>
        <head><title>教师数据自填系统</title></head>
        <body>
            <h1>页面加载失败</h1>
        </body>
    </html>
    """


@app.get("/confirm/{share_token}", response_class=HTMLResponse)
async def confirm_page(share_token: str):
    """教师确认页面"""
    html_file = Path(__file__).parent.parent / "templates" / "confirm.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return """
    <html>
        <head><title>问卷信息确认</title></head>
        <body>
            <h1>页面加载失败</h1>
        </body>
    </html>
    """


@app.get("/admin/edit-placeholder", response_class=HTMLResponse)
async def edit_placeholder_page(request: Request):
    """PDF占位符编辑页面（需要管理员权限）"""
    # 从cookie获取token
    token = request.cookies.get("admin_token")
    
    # 如果没有token，检查URL参数（用于首次登录后的跳转）
    if not token:
        token = request.query_params.get("token")
    
    if not verify_admin_session(token):
        # 如果验证失败，重定向到登录页面，并带上返回URL
        return_url = str(request.url)
        return RedirectResponse(url=f"/admin/login?return_url={return_url}")
    
    html_file = Path(__file__).parent.parent / "templates" / "edit_placeholder.html"
    if html_file.exists():
        html_content = html_file.read_text(encoding="utf-8")
        # 注入token到localStorage（edit_placeholder.html中已经有API_BASE和fetch重写逻辑）
        html_content = html_content.replace(
            '</head>',
            f'''<script>
                // 确保token已设置（edit_placeholder.html中的代码会使用它）
                localStorage.setItem('admin_token', '{token}');
            </script>
            </head>'''
        )
        return html_content
    return """
    <html>
        <head><title>编辑PDF占位符</title></head>
        <body>
            <h1>页面加载失败</h1>
        </body>
    </html>
    """


@app.get("/query", response_class=HTMLResponse)
async def query_page():
    """用户查询页面"""
    html_file = Path(__file__).parent.parent / "templates" / "query.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return """
    <html>
        <head><title>查询我的填表结果</title></head>
        <body>
            <h1>页面加载失败</h1>
        </body>
    </html>
    """


@app.get("/teacher/login", response_class=HTMLResponse)
async def teacher_login_page(request: Request):
    """教师登录页面"""
    return_url = request.query_params.get("return_url", "/teacher/dashboard")
    login_html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>教师登录</title>
        <link href="/static/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .login-card {{
                max-width: 400px;
                width: 100%;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }}
            .card-header {{
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white;
                border-radius: 15px 15px 0 0 !important;
            }}
        </style>
    </head>
    <body>
        <div class="card login-card">
            <div class="card-header text-center">
                <h4><i class="bi bi-person-circle"></i> 教师登录</h4>
            </div>
            <div class="card-body">
                <form id="login-form">
                    <div class="mb-3">
                        <label for="id_number" class="form-label">身份证号 *</label>
                        <input type="text" class="form-control" id="id_number" required>
                    </div>
                    <div class="mb-3">
                        <label for="phone" class="form-label">手机号 *</label>
                        <input type="text" class="form-control" id="phone" required>
                    </div>
                    <div id="error-message" class="alert alert-danger" style="display: none;"></div>
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary">登录</button>
                    </div>
                </form>
            </div>
        </div>
        <script>
            document.getElementById('login-form').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const idNumber = document.getElementById('id_number').value.trim();
                const phone = document.getElementById('phone').value.trim();
                const response = await fetch('/api/teacher/login', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{id_number: idNumber, phone: phone}})
                }});
                if (response.ok) {{
                    const data = await response.json();
                    localStorage.setItem('teacher_token', data.token);
                    localStorage.setItem('teacher_id', data.teacher_id);
                    const returnUrl = new URLSearchParams(window.location.search).get('return_url') || '{return_url}';
                    window.location.href = returnUrl;
                }} else {{
                    const error = await response.json();
                    const errorDiv = document.getElementById('error-message');
                    errorDiv.textContent = error.detail || '登录失败，请检查身份证号和手机号是否正确';
                    errorDiv.style.display = 'block';
                }}
            }});
        </script>
    </body>
    </html>
    """
    return login_html


@app.post("/api/teacher/login")
async def teacher_login(request: Request, db: Session = Depends(get_db)):
    """教师登录验证"""
    from pydantic import BaseModel
    from app.models import Teacher
    
    class LoginRequest(BaseModel):
        id_number: str
        phone: str
    
    try:
        data = await request.json()
        login_req = LoginRequest(**data)
        
        # 验证教师身份
        teacher = db.query(Teacher).filter(
            Teacher.id_number == login_req.id_number,
            Teacher.phone == login_req.phone
        ).first()
        
        if teacher:
            token = create_teacher_session(teacher.id)
            from fastapi.responses import JSONResponse
            response = JSONResponse({
                "token": token,
                "teacher_id": teacher.id,
                "teacher_name": teacher.name,
                "message": "登录成功"
            })
            response.set_cookie(key="teacher_token", value=token, httponly=True, max_age=86400 * 7)  # 7天
            return response
        else:
            raise HTTPException(status_code=401, detail="身份证号或手机号错误")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"登录失败: {str(e)}")


@app.get("/teacher/dashboard", response_class=HTMLResponse)
async def teacher_dashboard(request: Request):
    """教师个人中心页面（需要登录）"""
    token = request.headers.get("X-Teacher-Token") or request.cookies.get("teacher_token")
    
    if not token:
        token = request.query_params.get("token")
    
    teacher_id = verify_teacher_session(token)
    if not teacher_id:
        return RedirectResponse(url="/teacher/login")
    
    html_file = Path(__file__).parent.parent / "templates" / "teacher_dashboard.html"
    if html_file.exists():
        html_content = html_file.read_text(encoding="utf-8")
        # 注入token到localStorage
        html_content = html_content.replace(
            '<script src="/static/js/bootstrap.bundle.min.js"></script>',
            f'''<script>
                localStorage.setItem('teacher_token', '{token}');
                localStorage.setItem('teacher_id', '{teacher_id}');
            </script>
            <script src="/static/js/bootstrap.bundle.min.js"></script>'''
        )
        return html_content
    
    # 如果模板文件不存在，返回简单的HTML
    return f"""
    <html>
        <head>
            <title>教师个人中心</title>
            <link href="/static/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-5">
                <h1>教师个人中心</h1>
                <p>教师ID: {teacher_id}</p>
                <p>请创建 teacher_dashboard.html 模板文件</p>
            </div>
        </body>
    </html>
    """


@app.get("/teacher/seal-requests/new", response_class=HTMLResponse)
async def teacher_seal_new_page():
    """教师发起公章审批页面"""
    html_file = Path(__file__).parent.parent / "templates" / "seal_submit.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return """
    <html><body><h1>页面加载失败：seal_submit.html 不存在</h1></body></html>
    """


@app.post("/api/teacher/logout")
async def teacher_logout(request: Request):
    """教师登出"""
    token = request.headers.get("X-Teacher-Token") or request.cookies.get("teacher_token")
    if token:
        remove_teacher_session(token)
    from fastapi.responses import JSONResponse
    response = JSONResponse({"message": "登出成功"})
    response.delete_cookie(key="teacher_token")
    return response


@app.get("/admin/seal-requests", response_class=HTMLResponse)
async def admin_seal_requests_page(request: Request):
    """管理员公章审批列表页（需要登录）"""
    token = request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")
    if not token:
        token = request.query_params.get("token")
    if not verify_admin_session(token):
        return RedirectResponse(url="/admin/login")

    html_file = Path(__file__).parent.parent / "templates" / "seal_admin_requests.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")

    return """
    <html><body><h1>页面加载失败：seal_admin_requests.html 不存在</h1></body></html>
    """


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    """Chrome DevTools应用特定配置（可选）"""
    # 返回空JSON，避免404错误
    # 这是Chrome DevTools的自动请求，用于检查应用特定配置
    from fastapi.responses import JSONResponse
    return JSONResponse({})


@app.on_event("startup")
async def startup_event():
    """启动时初始化数据库"""
    from app.database import init_db
    init_db()
    print("系统启动完成！")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

