##############################################################################
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from time import localtime, strftime

from litp.core.config import config
from litp.core.litp_logging import LitpLogger
import os.path

log = LitpLogger()


def generate_dot_diagram(graph_dict):
    # only imports here to avoid dot_parser import message
    import pydot

    graph = pydot.Dot()
    # pylint: disable=E1101
    graph.set_nodesep(1.5)
    graph.set_ranksep(1)
    # pylint: enable=E1101

    def elem_name(item):
        return (getattr(item, 'task_id', None) or
                getattr(item, 'item_id', None) or
                str(item))

    for task, requires in graph_dict.items():
        class_name = elem_name(task)
        class_node = pydot.Node(
            name=class_name,
            shape='Mrecord',
            URL=class_name
        )
        graph.add_node(class_node)
        for req in requires:

            require_name = elem_name(req)
            require_edge = pydot.Edge(
                class_name,
                require_name,
                arrowhead="empty"
            )
            graph.add_edge(require_edge)
        class_name = ""

    base_path = config.get('task_graph_save_location')

    if base_path:
        graph_name = strftime("graph_%Y%m%d%H%M%S.dot", localtime())
        graph_full_path = os.path.join(base_path, graph_name)
        try:
            graph.write(graph_full_path)
        except IOError as ex:
            log.trace.error("Could not create"
                            " dot file for graph:"
                            " {0}".format(ex))
            return None
        return graph_full_path
    else:
        return None
