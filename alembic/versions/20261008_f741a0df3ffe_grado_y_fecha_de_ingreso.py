"""grado y fecha de ingreso de usuarios

Revision ID: f741a0df3ffe
Revises: 0cbe3604220d
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f741a0df3ffe'
down_revision: Union[str, Sequence[str], None] = '0cbe3604220d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuarios', sa.Column('grado', sa.Integer(), server_default='0', nullable=False))
    op.add_column('usuarios', sa.Column('fecha_ingreso', sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f('ck_usuarios_grado_valido'), 'usuarios', 'grado BETWEEN 0 AND 6'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_usuarios_grado_valido'), 'usuarios', type_='check')
    op.drop_column('usuarios', 'fecha_ingreso')
    op.drop_column('usuarios', 'grado')
