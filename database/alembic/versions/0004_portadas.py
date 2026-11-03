"""Agrega referencias opcionales de portadas de Cloudinary."""

import sqlalchemy as sa
from alembic import op

revision = "0004_portadas"
down_revision = "0003_usuarios_y_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("libros", sa.Column("portada_url", sa.String(1000), nullable=True))
    op.add_column("libros", sa.Column("portada_public_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("libros", "portada_public_id")
    op.drop_column("libros", "portada_url")
