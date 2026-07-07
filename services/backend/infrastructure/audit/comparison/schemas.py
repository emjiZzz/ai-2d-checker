from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class Coordinate2D(BaseModel):
    x: float
    y: float

    @classmethod
    def from_list(cls, l: List[float]) -> "Coordinate2D":
        if not isinstance(l, list) or len(l) != 2:
            raise ValueError("Coordinate list must have exactly 2 elements")
        return cls(x=float(l[0]), y=float(l[1]))

    def to_list(self) -> List[float]:
        return [self.x, self.y]

class BoundingBox2D(BaseModel):
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @classmethod
    def from_tuple(cls, t: tuple) -> "BoundingBox2D":
        if not isinstance(t, (tuple, list)) or len(t) != 4:
            raise ValueError("Bounding box must have exactly 4 elements")
        return cls(xmin=float(t[0]), ymin=float(t[1]), xmax=float(t[2]), ymax=float(t[3]))

    def to_tuple(self) -> tuple:
        return (self.xmin, self.ymin, self.xmax, self.ymax)

class ComparisonEntityDTO(BaseModel):
    handle: str
    text: str
    coordinates: Optional[Coordinate2D] = None
    bbox: Optional[BoundingBox2D] = None
