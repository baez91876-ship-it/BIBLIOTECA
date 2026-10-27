"""Agrega usuarios, roles y refresh tokens almacenados por JTI.

Revision ID: 0003_usuarios_y_refresh_tokens
Revises: 0002_multa_pagada
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_usuarios_y_refresh_tokens"
down_revision = "0002_multa_pagada"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("intentos_fallidos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("socio_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "intentos_fallidos >= 0",
            name="intentos_no_negativos",
        ),
        sa.CheckConstraint(
            "rol IN ('socio', 'bibliotecario', 'administrador')",
            name="rol_valido",
        ),
        sa.ForeignKeyConstraint(
            ["socio_id"],
            ["socios.id"],
            name="fk_usuarios_socio_id_socios",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usuarios"),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
        sa.UniqueConstraint("socio_id", name="uq_usuarios_socio_id"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reemplazado_por", sa.String(length=36), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_refresh_tokens_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name="pk_refresh_tokens"),
    )
    op.create_index(
        "ix_refresh_tokens_usuario_id", "refresh_tokens", ["usuario_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_usuario_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("usuarios")
