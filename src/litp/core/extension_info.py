from litp.data.types import Base as DbBase
from litp.data.types import Extension as DbExtension
from litp.data.constants import LIVE_MODEL_ID


class ExtensionInfo(DbExtension, DbBase):
    def __init__(self, name, classpath, version, _model_id=LIVE_MODEL_ID):
        self.name = name
        self.classpath = classpath
        self.version = version
        self._model_id = _model_id
