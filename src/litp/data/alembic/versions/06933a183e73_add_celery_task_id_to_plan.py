# pylint: disable=E1101,C0103,C0111
# revision identifiers, used by Alembic.
revision = '06933a183e73'
down_revision = '46c857af5e01'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        'plans', sa.Column('celery_task_id', sa.UnicodeText(), nullable=True))
    pass


def downgrade():
    raise NotImplementedError("No downgrades.")
    # pylint: disable=W0101
    pass
