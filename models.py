from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="member")  # admin or member
    created_at = Column(DateTime, default=datetime.utcnow)

class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    level = Column(Integer, default=1)  # 1=一级, 2=二级
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    files = relationship("FileList", back_populates="folder")

class FileList(Base):
    __tablename__ = "file_list"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"))
    filename = Column(String)
    description = Column(Text, nullable=True)
    required = Column(Integer, default=1)  # 1=必传, 0=可选
    created_at = Column(DateTime, default=datetime.utcnow)

    folder = relationship("Folder", back_populates="files")
    uploads = relationship("Upload", back_populates="file_list")

class Upload(Base):
    __tablename__ = "uploads"
    id = Column(Integer, primary_key=True, index=True)
    file_list_id = Column(Integer, ForeignKey("file_list.id"))
    uploader_id = Column(Integer, ForeignKey("users.id"))
    actual_filename = Column(String)
    file_path = Column(String)
    file_size = Column(Integer)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    file_list = relationship("FileList", back_populates="uploads")
    user = relationship("User")
