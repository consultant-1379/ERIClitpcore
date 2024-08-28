from sqlalchemy import Column
from sqlalchemy import Unicode


class Plugin(object):
    __tablename__ = "plugins"

    name = Column("name", Unicode, primary_key=True)
    classpath = Column(
        "classpath", Unicode, nullable=False, unique=True, index=True)
    version = Column("version", Unicode, nullable=False)
