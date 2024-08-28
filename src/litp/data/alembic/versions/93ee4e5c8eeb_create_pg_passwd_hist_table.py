# pylint: disable=E1101,C0103,C0111
# revision identifiers, used by Alembic.
revision = '93ee4e5c8eeb'
down_revision = '06933a183e73'
branch_labels = None
depends_on = None

import datetime
from alembic import op
import sqlalchemy as sa


def upgrade():
    pg_passwd_hist_table = \
        op.create_table('pg_passwd_hist',
                        sa.Column('usename', sa.String(length=64),
                                  nullable=False),
                        sa.Column('passwd', sa.UnicodeText(), nullable=False),
                        sa.Column('datecreated', sa.DateTime(timezone=True),
                                  nullable=False),
                        sa.PrimaryKeyConstraint('passwd',
                                                name=op.f('pk_pg_passwd_hist'))
                       )

    op.execute(pg_passwd_hist_table.insert() \
               .values(usename='postgres',
                       passwd=u'md5958e1c4182a7ba15d80dd107f211e35a',
                       datecreated=datetime.datetime.now())
              )
    pass


def downgrade():
    raise NotImplementedError("No downgrades.")
    # pylint: disable=W0101
    op.drop_table('pg_passwd_hist')
    pass
