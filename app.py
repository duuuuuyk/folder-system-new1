from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from typing import List, Optional
import os
import shutil
import uuid
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from models import Base, User, Folder, FileList, Upload
from schemas import UserCreate, UserLogin, FolderCreate, FolderUpdate, FileListCreate, Token
from database import engine, get_db

app = FastAPI(title="文件夹管理系统", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str = None):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def get_current_user(token: str = None, db: Session = None):
    payload = verify_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    if db:
        return db.query(User).filter(User.id == int(user_id)).first()
    return None

# 上传目录
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 挂载静态文件
if os.path.exists(UPLOAD_DIR):
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 初始化默认用户
db = next(get_db())
admin = db.query(User).filter(User.username == "admin").first()
if not admin:
    admin = User(username="admin", password_hash=pwd_context.hash("admin123"), role="admin")
    member = User(username="member1", password_hash=pwd_context.hash("member123"), role="member")
    db.add(admin)
    db.add(member)
    db.commit()

# 初始化示例文件夹
if db.query(Folder).count() == 0:
    folder1 = Folder(name="项目文档", parent_id=None, level=1, created_by=1)
    folder2 = Folder(name="技术方案", parent_id=None, level=1, created_by=1)
    folder3 = Folder(name="需求文档", parent_id=1, level=2, created_by=1)
    folder4 = Folder(name="设计文档", parent_id=1, level=2, created_by=1)
    db.add_all([folder1, folder2, folder3, folder4])
    db.commit()
    
    # 示例文件清单
    files = [
        FileList(folder_id=1, filename="项目计划书.docx", description="项目整体计划", required=1),
        FileList(folder_id=1, filename="项目启动会.pptx", description="启动会议PPT", required=1),
        FileList(folder_id=2, filename="技术架构图.png", description="系统架构设计", required=1),
        FileList(folder_id=2, filename="接口文档.docx", description="API接口文档", required=0),
        FileList(folder_id=3, filename="需求说明书.docx", description="完整需求说明", required=1),
        FileList(folder_id=4, filename="UI设计稿.sketch", description="UI设计源文件", required=1),
    ]
    db.add_all(files)
    db.commit()
db.close()

# ============ 认证接口 ============
@app.post("/api/auth/register", response_model=dict)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    hashed = pwd_context.hash(user.password)
    new_user = User(username=user.username, password_hash=hashed, role="member")
    db.add(new_user)
    db.commit()
    return {"message": "注册成功"}

@app.post("/api/auth/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not pwd_context.verify(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    access_token = create_access_token(data={"sub": str(db_user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
def get_me(token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"id": user.id, "username": user.username, "role": user.role}

# ============ 文件夹接口 ============
@app.get("/api/folders")
def get_folders(token: str = None, db: Session = Depends(get_db)):
    folders = db.query(Folder).all()
    result = []
    for f in folders:
        total = db.query(FileList).filter(FileList.folder_id == f.id).count()
        uploaded = db.query(Upload).join(FileList).filter(FileList.folder_id == f.id).count()
        required_total = db.query(FileList).filter(FileList.folder_id == f.id, FileList.required == 1).count()
        required_uploaded = db.query(Upload).join(FileList).filter(
            FileList.folder_id == f.id, FileList.required == 1
        ).count()
        
        if total == 0:
            status = "empty"
        elif required_total == 0 or required_uploaded == required_total:
            status = "complete"
        elif uploaded > 0:
            status = "partial"
        else:
            status = "pending"
        
        result.append({
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "level": f.level,
            "total_files": total,
            "uploaded_files": uploaded,
            "required_files": required_total,
            "required_uploaded": required_uploaded,
            "status": status
        })
    return result

@app.post("/api/folders")
def create_folder(folder: FolderCreate, token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    new_folder = Folder(
        name=folder.name,
        parent_id=folder.parent_id,
        level=2 if folder.parent_id else 1,
        created_by=user.id
    )
    db.add(new_folder)
    db.commit()
    return {"id": new_folder.id, "message": "创建成功"}

@app.put("/api/folders/{folder_id}")
def update_folder(folder_id: int, folder: FolderUpdate, token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    db_folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not db_folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    db_folder.name = folder.name
    db.commit()
    return {"message": "更新成功"}

@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int, token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    db.query(FileList).filter(FileList.folder_id == folder_id).delete()
    db.query(Folder).filter(Folder.id == folder_id).delete()
    db.commit()
    return {"message": "删除成功"}

# ============ 文件清单接口 ============
@app.get("/api/folders/{folder_id}/file-list")
def get_file_list(folder_id: int, token: str = None, db: Session = Depends(get_db)):
    files = db.query(FileList).filter(FileList.folder_id == folder_id).all()
    result = []
    for f in files:
        upload = db.query(Upload).filter(Upload.file_list_id == f.id).first()
        result.append({
            "id": f.id,
            "filename": f.filename,
            "description": f.description,
            "required": f.required,
            "uploaded": upload is not None,
            "uploader": upload.user.username if upload else None,
            "uploaded_at": upload.uploaded_at.isoformat() if upload else None,
            "file_size": upload.file_size if upload else None
        })
    return result

@app.post("/api/folders/{folder_id}/file-list")
def add_file_list(folder_id: int, file: FileListCreate, token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    new_file = FileList(
        folder_id=folder_id,
        filename=file.filename,
        description=file.description,
        required=file.required
    )
    db.add(new_file)
    db.commit()
    return {"id": new_file.id, "message": "添加成功"}

@app.delete("/api/file-list/{file_id}")
def delete_file_list(file_id: int, token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    db.query(Upload).filter(Upload.file_list_id == file_id).delete()
    db.query(FileList).filter(FileList.id == file_id).delete()
    db.commit()
    return {"message": "删除成功"}

# ============ 上传接口 ============
@app.post("/api/uploads/{file_list_id}")
def upload_file(file_list_id: int, file: UploadFile = File(...), token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    
    file_list_item = db.query(FileList).filter(FileList.id == file_list_id).first()
    if not file_list_item:
        raise HTTPException(status_code=404, detail="文件清单不存在")
    
    # 检查文件扩展名
    ext = os.path.splitext(file_list_item.filename)[1]
    actual_ext = os.path.splitext(file.filename)[1]
    
    # 保存文件
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_size = os.path.getsize(file_path)
    
    # 删除旧上传记录
    old_upload = db.query(Upload).filter(Upload.file_list_id == file_list_id).first()
    if old_upload:
        if os.path.exists(os.path.join(UPLOAD_DIR, old_upload.actual_filename)):
            os.remove(os.path.join(UPLOAD_DIR, old_upload.actual_filename))
        db.delete(old_upload)
    
    # 创建新记录
    new_upload = Upload(
        file_list_id=file_list_id,
        uploader_id=user.id,
        actual_filename=unique_filename,
        file_path=file_path,
        file_size=file_size
    )
    db.add(new_upload)
    db.commit()
    
    return {"message": "上传成功", "filename": unique_filename}

@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: int, token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    
    if user.role != "admin" and upload.uploader_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除")
    
    if os.path.exists(upload.file_path):
        os.remove(upload.file_path)
    
    db.delete(upload)
    db.commit()
    return {"message": "删除成功"}

@app.get("/api/my-uploads")
def my_uploads(token: str = None, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    
    uploads = db.query(Upload).filter(Upload.uploader_id == user.id).all()
    result = []
    for u in uploads:
        result.append({
            "id": u.id,
            "filename": u.file_list.filename,
            "file_size": u.file_size,
            "uploaded_at": u.uploaded_at.isoformat(),
            "folder_name": u.file_list.folder.name
        })
    return result

# ============ 前端页面 ============
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
