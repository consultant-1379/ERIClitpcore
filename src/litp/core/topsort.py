##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

"""
Topology Sort algorithm

Original Source {{{ http://code.activestate.com/recipes/577413/ (r1)
"""

from itertools import chain
flat = chain.from_iterable

from litp.core.exceptions import CyclicGraphException


def topsort(graph):
    """
    :param dict graph: A dictionary representing the graph to be sorted. Keys
    are strings representing nodes and values are sets of strings representing
    that node's dependencies
    :return A generator yielding a list of node names sorted in alphabetical
    order such that each value yielded by the generator has no dependency
    against values yielded by any subsequent call.
    """
    if not graph:
        return
    for node, node_dependencies in graph.items():
        node_dependencies.discard(node)

    nodes_not_in_keys = set(flat(graph.itervalues())) - set(graph.iterkeys())

    graph.update(
        dict(
            (node, set()) for node in nodes_not_in_keys
        )
    )

    while True:
        leaf_nodes = set(node for (node, dep) in graph.iteritems() if not dep)
        if not leaf_nodes:
            break

        yield sorted(leaf_nodes)

        # Remove nodes without dependencies from the graph as well as other
        # nodes' dependencies to them
        graph = dict(
            (node, (dep - leaf_nodes)) for (node, dep) in graph.iteritems()
                    if node not in leaf_nodes
        )

    if graph:
        exc = CyclicGraphException("A cyclic dependency exists in graph",
                                   graph)
        raise exc
