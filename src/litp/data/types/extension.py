from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy import Index


class Extension(object):
    __tablename__ = "extensions"

    name = Column("name", Unicode, primary_key=True)
    _model_id = Column("model_id", Unicode, primary_key=True)
    classpath = Column("classpath", Unicode, nullable=False)
    version = Column("version", Unicode, nullable=False)

    __table_args__ = (Index("ix_extensions_classpath_model_id", "classpath",
        "model_id", unique=True),)
