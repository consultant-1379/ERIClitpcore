# pylint: disable=E1101,C0103,C0111
# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    raise NotImplementedError("No downgrades.")
    # pylint: disable=W0101
    ${downgrades if downgrades else "pass"}
