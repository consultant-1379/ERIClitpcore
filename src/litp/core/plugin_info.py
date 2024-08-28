from litp.data.types import Base as DbBase
from litp.data.types import Plugin as DbPlugin


class PluginInfo(DbPlugin, DbBase):
    def __init__(self, name, classpath, version):
        self.name = name
        self.classpath = classpath
        self.version = version
