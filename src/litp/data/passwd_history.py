from sqlalchemy import Column, UnicodeText, String, DateTime
from litp.data.types import Base


class PasswordHistory(Base):  # pylint: disable=W0232
    __tablename__ = "pg_passwd_hist"

    username = Column("usename", String(length=64), nullable=False)
    passwd = Column("passwd", UnicodeText(), primary_key=True,
                    nullable=False)
    datecreated = Column("datecreated", DateTime(timezone=True),
                    nullable=False)
