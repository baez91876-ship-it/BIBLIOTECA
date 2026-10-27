"""Estado inicial del esquema del Taller 1.

Revision ID: 0001_estado_inicial
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_estado_inicial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("nacionalidad", sa.String(length=60), nullable=True),
        sa.Column("anio_nacimiento", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_autores"),
        sa.UniqueConstraint("nombre", name="uq_autores_nombre"),
    )
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=50), nullable=False),
        sa.Column("descripcion", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_categorias"),
        sa.UniqueConstraint("nombre", name="uq_categorias_nombre"),
    )
    op.create_table(
        "socios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("telefono", sa.String(length=15), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_alta",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_socios"),
        sa.UniqueConstraint("email", name="uq_socios_email"),
    )
    op.create_table(
        "libros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("isbn", sa.String(length=13), nullable=False),
        sa.Column("anio_publicacion", sa.Integer(), nullable=False),
        sa.Column("ejemplares", sa.Integer(), nullable=False),
        sa.Column("autor_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["autor_id"],
            ["autores.id"],
            name="fk_libros_autor_id_autores",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_libros"),
        sa.UniqueConstraint("isbn", name="uq_libros_isbn"),
    )
    op.create_table(
        "libro_categoria",
        sa.Column("libro_id", sa.Integer(), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["categorias.id"],
            name="fk_libro_categoria_categoria_id_categorias",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["libro_id"],
            ["libros.id"],
            name="fk_libro_categoria_libro_id_libros",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("libro_id", "categoria_id", name="pk_libro_categoria"),
    )
    op.create_table(
        "prestamos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("libro_id", sa.Integer(), nullable=False),
        sa.Column("socio_id", sa.Integer(), nullable=False),
        sa.Column(
            "fecha_prestamo",
            sa.Date(),
            server_default=sa.func.current_date(),
            nullable=False,
        ),
        sa.Column("fecha_limite", sa.Date(), nullable=False),
        sa.Column("fecha_devolucion", sa.Date(), nullable=True),
        sa.Column(
            "multa",
            sa.Numeric(precision=10, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["libro_id"],
            ["libros.id"],
            name="fk_prestamos_libro_id_libros",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["socio_id"],
            ["socios.id"],
            name="fk_prestamos_socio_id_socios",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prestamos"),
    )


def downgrade() -> None:
    op.drop_table("prestamos")
    op.drop_table("libro_categoria")
    op.drop_table("libros")
    op.drop_table("socios")
    op.drop_table("categorias")
    op.drop_table("autores")
