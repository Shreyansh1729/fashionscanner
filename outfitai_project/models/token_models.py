# outfitai_project/models/token_models.py
from pydantic import BaseModel
from typing import Optional
import uuid

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    sub: Optional[str] = None # 'sub' is the standard JWT subject claim