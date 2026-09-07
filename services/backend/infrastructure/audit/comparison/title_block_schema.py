from pydantic import BaseModel
from typing import Optional

class SingleTitleBlockFields(BaseModel):
    SCALE: Optional[str] = None
    TITLE: Optional[str] = None
    DWG_NO: Optional[str] = None
    DRAWN: Optional[str] = None
    DESIGNED: Optional[str] = None
    QTY: Optional[str] = None
