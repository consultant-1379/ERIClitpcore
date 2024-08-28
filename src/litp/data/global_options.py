"""
Store for global values like DB version.
"""
from sqlalchemy import Column, Integer, String

from litp.data.types import Base


class GlobalOption(Base):
    # pylint: disable=invalid-name, too-few-public-methods, no-init
    __tablename__ = "global_options"
    id = Column("id", Integer, primary_key=True)
    value = Column("value", String(256))
