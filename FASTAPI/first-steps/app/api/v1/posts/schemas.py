from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator, EmailStr, ConfigDict

BAD_WORDS = ["pochola"]


class Tag(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Nombre de la etiqueta",
    )
    model_config = ConfigDict(from_attributes=True)


class Author(BaseModel):
    name: str = Field(
        ..., min_length=2, max_length=30, description="Nombre del autor del post"
    )
    email: EmailStr = Field(..., description="Email del autor del post")
    model_config = ConfigDict(from_attributes=True)


class PostBase(BaseModel):
    title: str
    content: str
    tags: Optional[List[Tag]] = Field(default_factory=list)
    author: Optional[Author] = None
    model_config = ConfigDict(from_attributes=True)


class PostCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Titulo del post (min 3 caracteres y max 100 caracteres)",
        examples=["Mi primer post con FastAPI"],
    )  # elipsis = espera contenido
    content: Optional[str] = Field(
        default="Contenido no disponible",
        min_length=10,
        description="Contenido del Post",
        examples=["Este es un contenido valido por que tiene 10 caracteres o más"],
    )
    tags: List[Tag] = Field(default_factory=list)
    # author: Optional[Author] = None

    @field_validator("title")  # evalua el campo titulo
    @classmethod  # ocupa la clase (nombre del modelo, manipula el valor a nivel clase)
    def not_allowed_title(cls, value: str) -> str:
        for word in BAD_WORDS:
            if word in value.lower():
                raise ValueError(f"El titulo no puede contener la palabra: {word}")
        return value
        # if "spam" in value.lower():
        #     raise ValueError("El titulo no puede contener la palabra: spam")
        # return value


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=100)
    content: Optional[str] = None


class PostPublic(PostBase):  # hereda title y content
    id: int

    model_config = ConfigDict(
        from_attributes=True
    )  # pydantic entienda que recibe un obj de sqlAlchemy y lo convierte en un json


class PostSummary(BaseModel):
    id: int
    title: str

    model_config = ConfigDict(from_attributes=True)


class PaginatedPost(BaseModel):
    page: int
    per_page: int  # limit
    total: int
    total_pages: int
    has_prev: bool
    has_next: bool
    order_by: Literal["id", "title"]
    direction: Literal["asc", "desc"]
    search: Optional[str] = None
    items: list[PostPublic]
