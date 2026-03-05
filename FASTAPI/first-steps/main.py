import os
from datetime import datetime
from fastapi import FastAPI, Query, HTTPException, Path, status, Depends
from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field, field_validator, EmailStr, ConfigDict
import uvicorn
from math import ceil
from sqlalchemy import (
    create_engine,
    Integer,
    String,
    Text,
    DateTime,
    select,
    func,
    UniqueConstraint,
    ForeignKey,
    Table,
    Column,
)
from sqlalchemy.orm import (
    sessionmaker,
    Session,
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
    joinedload,
)
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from colorama import Fore
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./blog.db")  ##motor://ruta


engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {
        "check_same_thread": False
    }  ##permite que varios threads usen esta conexión

engine = create_engine(
    DATABASE_URL, echo=True, future=True, **engine_kwargs
)  # engine: El objeto que maneja la conexión real a la base de datos.
# echo= muestra por consola las querys a la bd, future= usa la API moderna de sqlAlchemy.

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, class_=Session
)


class Base(DeclarativeBase):
    pass


post_tags = Table(  # tabla intermedia
    "post_tags",
    Base.metadata,
    Column("post_id", ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class AuthorORM(Base):  # authors y post se relacionan(1 a N)
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    posts: Mapped[List["PostORM"]] = relationship(back_populates="author")


class TagORM(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)

    posts: Mapped[List["PostORM"]] = relationship(
        secondary=post_tags, back_populates="tags", lazy="selectin"
    )


class PostORM(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("title", name="unique_post_title"),)  # tupla
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        "create_at", DateTime, default=datetime.utcnow
    )

    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("authors.id"))
    author: Mapped[Optional["AuthorORM"]] = relationship(back_populates="posts")

    tags: Mapped[List["TagORM"]] = relationship(
        secondary=post_tags,
        back_populates="posts",
        lazy="selectin",
        passive_deletes=True,
    )


Base.metadata.create_all(bind=engine)  # crea tablas en caso de que mo existan - dev


def get_db():
    db = SessionLocal()
    try:
        yield db  # igual a return pero no finaliza la ejecución [PAUSA]
    finally:
        db.close()


############# fin de db config ###################33
app = FastAPI(title="Mini Blog")


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


BAD_WORDS = ["porn", "xxx", "tits", "boobs", "dick", "cock", "pussy", "coochie"]


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
    author: Optional[Author] = None

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


@app.get("/")
def home():
    return {"message": "Bienvenidos a mini blog!"}


@app.get(
    "/posts", response_model=PaginatedPost
)  # una lista de muchos postPublic es la response
def list_posts(
    text: Optional[str] = Query(
        default=None,
        deprecated=True,
        description="Parámetro obsoleto, usa 'query o search' en su lugar.",
    ),
    query: Optional[str] = Query(
        default=None,
        description="texto para buscar por titulo",
        alias="search",  ##alias para el query (var)
        min_length=3,
        max_length=50,
        pattern=r"^[\w\sáéíóúÁÉÍÓÚüÜ-]+$",
    ),
    per_page: int = Query(
        10,
        ge=1,
        le=50,
        description="Numero de resultados (1-50)",
    ),
    page: int = Query(
        1,
        ge=1,
        description="Número de página (Mayor o igual a uno)",
    ),
    order_by: Literal["id", "title"] = Query(
        "id",
        description="Campo de orden",
    ),
    direction: Literal["asc", "desc"] = Query(
        "asc",
        description="Dirección de orden",
    ),
    db: Session = Depends(get_db),
):

    results = select(PostORM)
    query = query or text

    if query:
        results = results.where(
            PostORM.title.ilike(f"%{query}%")
        )  # filtramos con la query

    total = db.scalar(select(func.count()).select_from(results.subquery())) or 0
    total_pages = ceil(total / per_page) if total > 0 else 0

    current_pages = 1 if total_pages == 0 else min(page, total_pages)

    if order_by == "id":
        order_col = PostORM.id
    else:
        order_col = func.lower(PostORM.title)

    results = results.order_by(
        order_col.asc() if direction == "asc" else order_col.desc()
    )
    # results = sorted(
    #     results, key=lambda post: post[order_by], reverse=(direction == "desc"))
    if total_pages == 0:
        items = []
    else:
        start = (current_pages - 1) * per_page
        items = db.execute(results.limit(per_page).offset(start)).scalars().all()

    has_prev = current_pages > 1
    has_next = current_pages < total_pages if total_pages > 0 else False
    return PaginatedPost(
        page=current_pages,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        order_by=order_by,
        direction=direction,
        search=query,
        items=items,
    )


@app.get("/posts/by-tags", response_model=List[PostPublic])
def filter_by_tags(
    tags: List[str] = Query(
        ...,
        min_length=1,
        description="Una o más etiquetas. Ejemplo: ?tags=python&tags=fastapi",
    ),
    db: Session = Depends(get_db),
):
    normalized_tag_names = [tag.strip().lower() for tag in tags if tag.strip().lower()]
    if not normalized_tag_names:
        return []
    post_list = (
        select(PostORM)
        .options(
            selectinload(PostORM.tags),
            joinedload(PostORM.author),
        )
        .where(PostORM.tags.any(func.lower(TagORM.name).in_(normalized_tag_names)))
        .order_by(PostORM.id.asc())
    )
    posts = db.execute(post_list).scalars().all()

    return posts


@app.get(
    "/posts/{post_id}",
    response_model=Union[PostPublic, PostSummary],
    response_description="Post Encontrado",
)  # evalua ambos modelos con Union, para elegir el modelo de respuesta
def get_post(
    post_id: int = Path(
        ...,
        ge=1,
        title="ID del post",
        description="Identificador entero del post - mayor a 1",
        examples=1,
    ),
    include_content: Optional[bool] = Query(
        default=None, description="Bool para filtrar contenido"
    ),
    db: Session = Depends(get_db),
):
    post_find = select(PostORM).where(PostORM.id == post_id)

    post = db.execute(post_find).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    if include_content:
        return PostPublic.model_validate(post, from_attributes=True)
    return PostSummary.model_validate(post, from_attributes=True)


@app.post(
    "/posts",
    response_model=PostPublic,
    response_description="Post Creado(OK)",
    status_code=status.HTTP_201_CREATED,
)
def create_post(post: PostCreate, db: Session = Depends(get_db)):
    author_obj = None
    if post.author:
        author_obj = db.execute(
            select(AuthorORM).where(AuthorORM.email == post.author.email)
        ).scalar_one_or_none()
        if not author_obj:
            author_obj = AuthorORM(name=post.author.name, email=post.author.email)

            db.add(author_obj)
            db.flush()

    new_post = PostORM(title=post.title, content=post.content, author=author_obj)
    db.add(new_post)

    for tag in post.tags:
        tag_obj = db.execute(
            select(TagORM).where(TagORM.name.ilike(tag.name))
        ).scalar_one_or_none()

        if not tag_obj:
            tag_obj = TagORM(name=tag.name)
            db.add(tag_obj)
            db.flush()
        new_post.tags.append(tag_obj)  # MUCHOS A MUCHOS
    try:
        db.commit()
        db.refresh(new_post)
        return new_post
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El titulo ya existe")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al crear el post")


@app.put(
    "/posts/{post_id}",
    response_model=PostPublic,
    response_description="Post actualizado",
    response_model_exclude_none=True,
)
def update_post(post_id: int, data: PostUpdate, db: Session = Depends(get_db)):
    post = db.get(PostORM, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    updates = data.model_dump(exclude_unset=True)

    for key, value in updates.items():
        setattr(post, key, value)

    try:
        db.add(post)
        db.commit()
        db.refresh(post)
        return post
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al guardar los cambios")


@app.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post_to_delete = db.get(PostORM, post_id)

    if not post_to_delete:
        raise HTTPException(status_code=404, detail="Post no encontrado")

    try:
        db.delete(post_to_delete)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al eliminar el post")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
