##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import os
import re

SITE_TEMPLATE = """
{node_imports}

node default {{}}
"""

MS_NODE_TEMPLATE = """
{classdecs}
node "{hostname}" {{

    class {{'litp::ms_node':}}

{notifies}
}}
"""

MN_NODE_TEMPLATE = """
{classdecs}
node "{hostname}" {{

    class {{'litp::mn_node':
        ms_hostname => "{ms_hostname}",
        cluster_type => "{cluster_type}"
        }}

{notifies}
}}
"""

CLASSDEC_TEMPLATE = """class task_{task_unique_id}(){{
    {task_type} {{ "{task_id}":
{params}
    }}
}}

"""

CLASSDEC_TEMPLATE_UUDID = """class task_{task_unique_id}(){{
    {task_type} {{ "{task_id}":
        tag => ["tuuid_{task_uuid}",],
{params}
    }}
}}

"""


NOTIFIES_TEMPLATE = """
    class {{'task_{task_unique_id}':{requires}
    }}

"""


def clean_hostname(hostname):
    return hostname.replace(".", "_")


def _old_classdec(node):
    return node.get_vpath().strip("/").replace("/", "_") + "_cfg"


class PuppetManagerTemplates(object):
    def __init__(self, puppet_manager):
        self.manager = puppet_manager

    def _format_param(self, name, value):
        if name in ["require", "subscribe"]:
            return self._format_require_param(name, value)
        elif isinstance(value, list):
            return self._format_list(name, value)
        elif isinstance(value, dict):
            return self._format_dict(name, value)
        if name:
            return "        {name} => {value}".format(
                name=self._format_param_name(name),
                value=self._format_param_value(value))
        else:
            return "        {value}".format(
                value=self._format_param_value(value))

    def _format_require_param(self, name, values):
        return "        {name} => [{values}]".format(
            name=name, values=self._format_require_items(values))

    def _format_require_items(self, items):
        return ",".join(self._format_require_item(item) for item in items)

    def _format_require_item(self, item):
        return "{type}[\"{value}\"]".format(
            type=item['type'], value=item['value'])

    def _format_task_params(self, task):
        return ",\n".join([
            self._format_param(name, value)
            for name, value in sorted(task.kwargs.items())])

    def _format_param_name(self, name):
        if not re.search(r"^[a-z0-9][A-Za-z0-9_]*$", name):
            return "'%s'" % (name)
        else:
            return '%s' % (name)

    def _format_param_value(self, value):
        if not isinstance(value, (str, unicode)):
            value = str(value)
        return "\"%s\"" % re.sub(r"([\"])", r"\\\1", value)

    def _format_dict(self, name, value):
        l = []
        if name:
            l.append('%s => ' % self._format_param_name(name))
        l.append('{\n')
        dict_result = ',\n'.join(
            self._format_param(key, value[key]) for key in value.iterkeys())
        l.append(dict_result)
        l.append('\n        }')
        return "".join(l)

    def _format_list(self, name, value):
        l = []
        if name:
            l.append('%s => ' % self._format_param_name(name))
        l.append('[\n')
        listresult = ',\n'.join(
            self._format_param("", item) for item in value)
        l.append(listresult)
        l.append('\n        ]\n')
        return "".join(l)

    def _format_classdec(self, task):
        if task.uuid:
            return CLASSDEC_TEMPLATE_UUDID.format(
                task_unique_id=task.unique_id,
                task_uuid=task.uuid,
                task_type=task.call_type, task_id=task.call_id,
                params=self._format_task_params(task)
            )
        else:
            return CLASSDEC_TEMPLATE.format(
                task_unique_id=task.unique_id,
                task_type=task.call_type, task_id=task.call_id,
                params=self._format_task_params(task)
            )

    def _format_classdecs(self, tasks):
        return "".join([self._format_classdec(task) for task in tasks])

    def _format_notify(self, task, all_unique_ids):
        if task._requires:
            required_task_ids = list([req for req in task._requires
                                      if req in all_unique_ids and
                                      req not in task._redundant_requires])
            required_task_ids.sort()
            l = []
            l.append('\n        require => [')
            l.append(",".join(['Class["task_%s"]' % req
                                  for req in required_task_ids]))
            l.append(']')
            requires = "".join(l)
        else:
            requires = ""
        return NOTIFIES_TEMPLATE.format(task_unique_id=task.unique_id,
                                        requires=requires)

    def _format_notifies(self, tasks):
        all_unique_ids = [task.unique_id for task in tasks]
        return "".join([self._format_notify(task, all_unique_ids)
                        for task in tasks])

    def _format_old_classdec(self, node_vpath):
        return "%s_cfg" % (node_vpath.strip("/").replace("/", "_"),)

    def create_node_pp(self, node, tasks, ms_hostname, cluster_type):
        if node.item_type.item_type_id == 'ms':
            return MS_NODE_TEMPLATE.format(
                classdecs=self._format_classdecs(tasks),
                notifies=self._format_notifies(tasks),
                hostname=node.hostname)
        else:
            return MN_NODE_TEMPLATE.format(
                classdecs=self._format_classdecs(tasks),
                notifies=self._format_notifies(tasks),
                hostname=node.hostname,
                ms_hostname=ms_hostname,
                cluster_type=cluster_type)

    def old_manifest_file(self, vpath):
        return "import \"%s\"" % os.path.join(
            self.manager.get_litp_root(),
            "etc/puppet/manifests", vpath.lstrip('/'),
            "cfg.pp")
