from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None

class FolderUpdate(BaseModel):
    name: str

class FileListCreate(BaseModel):
    filename: str
    description: Optional[str] = None
    required: int = 1
