import gettext
import os
from gettext import NullTranslations


class Translator(object):
    def __init__(self, module):
        self.module = module
        self.t = None
        self.setup()

    def _(self, msg):
        if isinstance(self.t, NullTranslations):
            self.setup()
        return self.t.ugettext(msg)

    def setup(self):
        locale_dir = '/opt/ericsson/nms/litp/share/locale'
        if 'LITP_LOCALE_DIR' in os.environ:
            locale_dir = os.environ.get('LITP_LOCALE_DIR')
        self.t = gettext.translation(
            self.module, localedir=locale_dir, fallback=True, languages=['en'])
