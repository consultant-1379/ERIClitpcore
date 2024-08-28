# pylint: disable=E1101,C0103,C0111
# revision identifiers, used by Alembic.
revision = 'dfe3a5eb2c33'
down_revision = '93ee4e5c8eeb'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    stmt = 'UPDATE tasks SET kwargs= '
    stmt += 'REGEXP_REPLACE(kwargs, '
    stmt += '\'"type": "Class", "value": "lvm::volume\[([a-zA-Z0-9_-]*)\]"\', '
    stmt += '\'"type": "Lvm::Volume", "value": "\\1"\') '
    stmt += 'WHERE kwargs LIKE \'%\"require\": '
    stmt += '[{\\"type\\": \\"Class\\", \\"value\\": \\"lvm::volume%\';'
    op.execute(stmt)


def downgrade():
    stmt = 'UPDATE tasks SET kwargs= '
    stmt += 'REGEXP_REPLACE(kwargs, '
    stmt += '\'"type": "Lvm::Volume", "value": "([a-zA-Z0-9_-]*)"\', '
    stmt += '\'"type": "Class", "value": "lvm::volume[\\1]"\') '
    stmt += 'WHERE kwargs LIKE \'%\"require\": '
    stmt += '[{\\"type\\": \\"Lvm::Volume\\", \\"value\\": %\';'
    op.execute(stmt)
