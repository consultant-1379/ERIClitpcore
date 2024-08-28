import json
import os
import Cheetah.Filters

from Cheetah.Template import Template


class FilesystemLoader(object):

    def __init__(self, templates_dir):
        self.templates_dir = templates_dir

    def get_template(self, template_name):
        return LitpTemplate(os.path.join(self.templates_dir, template_name))


class LitpTemplate(object):

    def __init__(self, abs_path):
        self.abs_path = abs_path

    def render(self, context):
        tmpl = Template(file=self.abs_path, searchList=[context],
                        filter=JsonFilter)
        return str(tmpl)


class JsonFilter(Cheetah.Filters.Filter):

    def filter(self, val, **kw):
        if isinstance(val, (list, dict)):
            return json.dumps(val)
        else:
            return super(JsonFilter, self).filter(val, **kw)
