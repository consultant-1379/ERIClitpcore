##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.plugin import Plugin
from litp.core.validators import ValidationError
import functools
import litp.core.constants as constants
from litp.core.exceptions import CyclicGraphException, ModelManagerException
from litp.core.task import CallbackTask, ConfigTask
from litp.core.exceptions import CallbackExecutionException
from litp.core.model_manager import QueryItem
from litp.core.node_utils import wait_for_node_down,\
    wait_for_node_puppet_applying_catalog_valid
from litp.core.rpc_commands import RpcCommandProcessorBase,\
                                   RpcExecutionException,\
                                   reduce_errs


class CorePlugin(Plugin):

    """LITP core plugin. Provides validators for model and core item types."""

    def validate_model(self, api_context):
        """
        Performs model integrity validation. The validation rules enforced by
        this plugin are:

        - The `name` properties of `network` items must be unique.

        - The `hostname` property must be unique across all nodes as well as
          the MS.

        - For every `clustered-service` item in a `cluster` item's `services`
          collection, the comma-separated values present in the
          `clustered-service`'s `node_list` property must be the item_ids of
          nodes in that cluster and mustn't appear more than once.

        - For every `clustered-service` item in a `cluster` item's `services`
          collection, the comma-separated values present in the
          `dependency_list` property must be the item_ids of
          `clustered-service` items in that cluster's `services` collection.

        - For every `clustered-service` item in a `cluster` item's `services`
          collection, the comma-separated values present in the
          `dependency_list` property must not include the `clustered-service`'s
          own item_id.

        - For every `cluster` item in a `deployment` item's `clusters`
          collection, the cluster's `dependency_list` doesn't include a
          dependency on another cluster that either directly or indirectly
          depends on the original cluster.

        - For every `cluster` item in a `deployment` item's `clusters`
          collection, the cluster's `dependency_list` doesn't include more
          than the number of siblings it can have in a deployment's 'clusters'
          collection.

        - For every `cluster` item in a `deployment` item's `clusters`
          collection, the cluster's `dependency_list` doesn't include its own
          item_id.

        - For every `cluster` item in a `deployment` item's `clusters`
          collection, if the cluster item is not for removal the cluster's
          `dependency_list` includes only the item_ids of sibling clusters
          within that deployment that are not marked for removal.

        - For every `cluster` item in a `deployment` item's `clusters`
          collection, the cluster's `dependency_list` must not include
          duplicate item_ids.
        """
        errors = []
        errors.extend(self._validate_network_unique_names(api_context))
        errors.extend(self._validate_clustered_service_node_list(api_context))
        errors.extend(
            self._validate_clustered_service_dependency_list(api_context))
        errors.extend(
            self._validate_clustered_service_does_not_depend_on_self(
                api_context))
        errors.extend(self._validate_duplicate_hostnames(api_context))
        errors.extend(
            self._validate_cluster_no_cyclical_dependencies(api_context)
        )
        errors.extend(self._validate_cluster_dependency_list(api_context))
        errors.extend(self._validate_single_sshd_config_on_ms(api_context))
        return errors

    def _validate_single_sshd_config_on_ms(self, api):
        errors = []

        sshd_configs = [conf for conf in api.query('sshd-config')
                        if not conf.is_for_removal()]

#       if not sshd_configs:
#           emsg = 'There must be one sshd-config item, none found.'
#           errors.append(ValidationError(error_message=emsg))
#       elif len(sshd_configs) > 1:

        if len(sshd_configs) > 1:
            config_vpaths = ', '.join([conf.get_vpath()
                                 for conf in sshd_configs])
            emsg = 'One sshd-config item supported, more found: %s' % \
                   config_vpaths
            errors.append(ValidationError(item_path=config_vpaths,
                                          error_message=emsg))

        for sshd_config in sshd_configs:
            if not sshd_config.get_ms():
                errors.append(ValidationError(
                    item_path=sshd_config.get_vpath(),
                    error_message='This ItemType is only supported on the MS'))

        return errors

    def _validate_network_unique_names(self, api):
        errors = []
        networks = [net for net in api.query("network")
                    if not net.is_removed() and not net.is_for_removal()]

        existing_names = {}
        for lnetwork in networks:
            net_name = lnetwork.name
            if net_name in existing_names:
                errors.append(ValidationError(
                    lnetwork.get_vpath(),
                    error_message="Network name '%s' already used by '%s'" %
                                  (lnetwork.name, existing_names[net_name])))
            else:
                existing_names[net_name] = lnetwork.get_vpath()

        return errors

    def _validate_clustered_service_node_list(self, api):
        errors = []
        clusters = api.query("cluster", is_for_removal=False)
        for cluster in clusters:
            cluster_nodes_ids = [node.item_id for node in cluster.nodes]
            for service in cluster.services:
                if service.is_for_removal():
                    continue
                node_list_ids = service.node_list.split(',')
                for item_id in node_list_ids:
                    if item_id not in cluster_nodes_ids:
                        errors.append(
                            ValidationError(
                                service.get_vpath(),
                                error_message='Node "{0}/nodes/{1}" does not '
                                'exist. Ensure node_list property is '
                                'correct'.format(
                                    cluster.get_vpath(),
                                    item_id)))
                duplicates = set(item_id for item_id in node_list_ids if
                              node_list_ids.count(item_id) > 1)
                for item_id in duplicates:
                    errors.append(
                        ValidationError(
                            service.get_vpath(),
                            error_message='Only one occurrence of a node with '
                                          'item_id "{0}" is allowed in '
                                          'node_list. Ensure node_list '
                                          'property is '
                                          'correct'.format(item_id)))
        return errors

    def _validate_clustered_service_dependency_list(self, api):
        errors = []
        clusters = api.query("cluster", is_for_removal=False)
        for cluster in clusters:
            services = [service.item_id for service in cluster.services]
            for service in cluster.services:
                if service.dependency_list and not service.is_for_removal():
                    for dep in service.dependency_list.split(','):
                        if dep not in services:
                            errors.append(
                                ValidationError(
                                    service.get_vpath(),
                                    error_message="'{0}/services/{1}' does "
                                    "not exist. Please ensure dependency_list "
                                    "property is correct".format(
                                        cluster.get_vpath(),
                                        dep)))
        return errors

    def _validate_clustered_service_does_not_depend_on_self(self, api):
        errors = []
        clusters = api.query("cluster", is_for_removal=False)
        for cluster in clusters:
            for service in cluster.services:
                if service.dependency_list and not service.is_for_removal():
                    if service.item_id in service.dependency_list.split(','):
                        errors.append(
                            ValidationError(
                                service.get_vpath(),
                                error_message="A service can not depend on "
                                "itself. Please ensure dependency_list "
                                "property is correct"))
        return errors

    @staticmethod
    def _topsort(graph):
        """
        :param dict graph: A dictionary representing the graph to be sorted.
            Keys are strings representing item's and values are sets of strings
            representing that item's dependencies
        :return: A generator yielding a list of item names sorted in
            alphabetical order such that each value yielded by the generator
            has no dependency against values yielded by any subsequent call.
        """
        if not graph:
            return
        for node, node_dependencies in graph.items():
            node_dependencies.discard(node)

        nodes_not_in_keys = functools.reduce(set.union, graph.values()) -\
             set(graph.keys())
        graph.update(
             dict(
                 (node, set()) for node in nodes_not_in_keys
             )
         )

        while True:
            leaf_nodes = set(node for (node, dep) in graph.items() if not dep)
            if not leaf_nodes:
                break

             # Remove nodes without dependencies from the graph as well as
             # other nodes' dependencies to them
            graph = dict(
                 (node, (dep - leaf_nodes)) for (node, dep) in graph.items()
                         if node not in leaf_nodes
             )

        if graph:
            raise CyclicGraphException("A cyclic dependency exists in graph"
                " {0}".format([(node, graph[node]) for node in
                    sorted(graph.keys())]))

    def _validate_cluster_no_cyclical_dependencies(self, api):
        cluster_dependency_graph = {}
        errors = []
        deployments = api.query("deployment")
        for deployment in deployments:
            cluster_ids = [cluster.item_id for cluster in deployment.clusters
                    if not cluster.is_for_removal()]

            cluster_collection = deployment.item_type.structure.get('clusters')
            if cluster_collection:
                max_clusters = cluster_collection.max_count
            else:
                return []

            for cluster in deployment.clusters:
                if not (hasattr(cluster, 'dependency_list') and \
                        cluster.dependency_list):
                    continue

                dependencies = set(token.strip()
                        for token in cluster.dependency_list.split(",")
                )
                cluster_dependency_graph[cluster.item_id] = dependencies

            try:
                self._topsort(cluster_dependency_graph)
            except CyclicGraphException:
                graph_as_list = [str(item_id) \
                    for item_id in sorted(cluster_dependency_graph.keys())]
                graph_as_string = "{0} and {1}".format(
                    ", ".join(
                        ['"{0}"'.format(item) for item in graph_as_list[:-1]]
                    ),
                    '"{0}"'.format(graph_as_list[-1]))
                errors.append(
                    ValidationError(
                        item_path=deployment.clusters.get_vpath(),
                        error_message=('A circular dependency has been '
                            'detected between the following clusters: {0}. '
                            'Check the "dependency_list" property of each '
                            'cluster item to resolve the issue.'.format(
                                 graph_as_string
                            )
                        )
                    )
                )
        return errors

    @staticmethod
    def _cluster_ids(deployment):
        cluster_ids = {'ForRemoval': [], 'NotForRemoval': []}
        for cluster in deployment.clusters:
            if cluster.is_for_removal():
                cluster_ids['ForRemoval'].append(cluster.item_id)
            else:
                cluster_ids['NotForRemoval'].append(cluster.item_id)
        return cluster_ids

    def _validate_cluster_dependency_list(self, api):
        errors = []
        deployments = api.query("deployment")
        for deployment in deployments:
            cluster_ids = self._cluster_ids(deployment)

            cluster_collection = deployment.item_type.structure.get('clusters')
            if cluster_collection:
                max_clusters = cluster_collection.max_count
            else:
                return []

            for cluster in deployment.clusters:
                if not (hasattr(cluster, 'dependency_list') and \
                        cluster.dependency_list):
                    continue

                sibling_dependencies = cluster.dependency_list.split(',')
                max_deps = max_clusters - 1
                if len(sibling_dependencies) > max_deps:
                    errors.append(
                            ValidationError(
                                cluster.get_vpath(),
                                property_name="dependency_list",
                                error_message="A cluster cannot specify more "\
                                    "than {0} sibling dependencies".format(
                                        max_deps
                                    )
                        )
                    )

                if cluster.item_id in sibling_dependencies:
                    errors.append(
                        ValidationError(
                            cluster.get_vpath(),
                            property_name="dependency_list",
                            error_message="A cluster cannot depend on "
                            "itself. Please ensure dependency_list property "
                            "is correct"
                        )
                    )

                if not cluster.is_for_removal():
                    for item_id in sibling_dependencies:
                        if item_id not in cluster_ids['NotForRemoval']:
                            if item_id in cluster_ids['ForRemoval']:
                                msg = ('Cluster "{0}/clusters/{1}" is for '
                                       'removal. Cluster "{0}/clusters/{2}" '
                                       'has a dependency on it and is not '
                                       'for removal'.format
                                       (deployment.get_vpath(),
                                        item_id, cluster.item_id))
                            else:
                                msg = ('Cluster "{0}/clusters/{1}" '
                                       'does not exist.'
                                      ' Ensure dependency_list '
                                       'property is correct'
                                      .format(deployment.get_vpath(), item_id))

                            errors.append(
                                ValidationError(
                                    cluster.get_vpath(),
                                    property_name="dependency_list",
                                    error_message=msg
                                )
                            )

                duplicates = set(item_id for item_id in sibling_dependencies if
                              sibling_dependencies.count(item_id) > 1)
                for item_id in duplicates:
                    errors.append(
                        ValidationError(
                            cluster.get_vpath(),
                            property_name="dependency_list",
                            error_message='Only one occurrence of a cluster '
                                'with item_id "{0}" is allowed in '
                                'dependency_list. Ensure dependency_list '
                                'property is correct'.format(
                                    item_id
                                )
                            )
                    )
        return errors

    def _validate_duplicate_hostnames(self, api):
        errors = []
        claimants = dict()

        nodes = api.query("node")
        nodes.extend(api.query("ms"))
        for node in nodes:
            hostname = node.hostname.lower()
            if hostname not in claimants:
                claimants[hostname] = [node.get_vpath()]
            else:
                claimants[hostname].append(node.get_vpath())

        for hostname in claimants:
            if 1 == len(claimants[hostname]):
                continue
            # We'll tie the ValidationError to the first node claiming that
            # hostname, in alphabetical sort order
            claimants[hostname].sort()
            error = ValidationError(
                    item_path=claimants[hostname][0],
                    error_message="Hostname '{name}' is duplicated across"
                    " {claimants}. All hostnames must be unique.".format(
                        name=hostname.lower(),
                        claimants=", ".join(claimants[hostname])
                        )
                    )
            errors.append(error)
        return errors

    def create_configuration(self, plugin_api_context):
        """
        This plugin currently provides sshd-config configuration task(s).
        """
        tasks = []

        for ms in plugin_api_context.query('ms'):
            for sshd_config in ms.configs.query('sshd-config'):
                if sshd_config.is_initial() or sshd_config.is_updated():
                    value = 'no' if sshd_config.permit_root_login == 'false' \
                            else 'yes'
                    desc = "Set the SSHD config on '%s'" % ms.hostname
                    task = ConfigTask(ms, sshd_config, desc,
                                      "litp::sshd_msnode",
                                      "ms_sshd_config",
                                      permitrootlogin=value)
                    tasks.append(task)

        return tasks

    def validate_reboot_plan(self, model_manager, path):
        errors = []
        try:
            if path:
                item = model_manager.query_by_vpath(path)
                if item.item_type_id != 'node' or item.is_collection():
                    errors.append(ValidationError(
                        item_path=path,
                        error_message="Path must belong to a node",
                        error_type=constants.INVALID_LOCATION_ERROR)
                    )
        except ModelManagerException:
            errors.append(ValidationError(
                item_path=path,
                error_message="Path not found",
                error_type=constants.INVALID_LOCATION_ERROR)
            )
        return errors

    # the following methods need to be here because LITP requires tasks to be
    # added by registered plugins. Since we want this code to live in core
    # the only possible place is here, in the core plugin.
    def create_reboot_tasks(self, model_manager, path):
        tasks = []
        if path:
            item = model_manager.query_by_vpath(path)
            # Items in CallbackTasks need to be QueryItems
            tasks.append(self._get_node_reboot_task(
                QueryItem(model_manager, item)
            ))
        else:
            nodes = (n for n in model_manager.query('node')
                     if not n.is_initial())
            for n in nodes:
                tasks.append(self._get_node_reboot_task(
                    QueryItem(model_manager, n)
                ))
        return tasks

    def _get_node_reboot_task(self, item):
        return CallbackTask(item,
                            'Reboot node "%s"' % item.hostname,
                            self._reboot_node_and_wait,
                            item.hostname,
                            True,
        )

    def _reboot_node_and_wait(self, callback_api, hostname, loose):
        # XXX LITPCDS-9454 stop puppet before rebooting
        call_args = ['service', 'puppet', 'stop', '-y']
        callback_api.rpc_application([hostname], call_args)
        self._execute_rpc_in_callback_task(
            callback_api, [hostname], "core", "reboot"
        )
        wait_for_node_down(callback_api, [hostname], True)
        wait_for_node_puppet_applying_catalog_valid(
            callback_api, [hostname], True, loose=loose)

    def _execute_rpc_in_callback_task(self, cb_api, nodes, agent, action,
                                      action_kwargs=None, timeout=None):
        try:
            bcp = RpcCommandProcessorBase()
            _, errors = bcp.execute_rpc_and_process_result(
                cb_api, nodes, agent, action, action_kwargs, timeout
            )
        except RpcExecutionException as e:
            raise CallbackExecutionException(e)
        if errors:
            raise CallbackExecutionException(','.join(reduce_errs(errors)))
