from litp.data.types import Base as DbBase
from litp.data.passwd_history import PasswordHistory as PasswdHist


class PasswordHistoryInfo(PasswdHist, DbBase):
    def __init__(self, user, passwd, date):
        self.username = user
        self.passwd = passwd
        self.datecreated = date
