"""Agrega el estado de pago de las multas históricas.

Revision ID: 0002_multa_pagada
Revises: 0001_estado_inicial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_multa_pagada"
down_revision = "0001_estado_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prestamos",
        sa.Column("multa_pagada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(sa.text("UPDATE prestamos SET multa_pagada = false"))


def downgrade() -> None:
    op.drop_column("prestamos", "multa_pagada")
