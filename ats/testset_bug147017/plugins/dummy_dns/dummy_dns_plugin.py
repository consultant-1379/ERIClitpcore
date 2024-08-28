# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
# pylint: disable=undefined-variable
from litp.core.litp_logging import LitpLogger
from litp.core.plugin import Plugin
from litp.core.task import ConfigTask
from litp.core.validators import ValidationError

log = LitpLogger()

from litp.core.translator import Translator
t = Translator('ERIClitpdnsclient_CXP9031073')
_ = t._


class DNSClientPlugin(Plugin):
    """
    Enables management of the DNS client configuration file, namely
    resolv.conf. Update and remove reconfiguration actions are supported for \
    this plugin.
    """
    def _validate_nameservers(self, client):
        errors = []
        if not client.is_for_removal():
            name_servers = client.query("nameserver")
            nameserverkeys = {}
            for name_server in name_servers:
                if not name_server.is_for_removal():
                    if nameserverkeys.get(name_server.position):
                        errors.append(
                            ValidationError(
                                item_path=name_server.get_vpath(),
                                error_message=_('DUPLICATE_NS_POS')\
                                    % name_server.position))
                        errors.append(
                            ValidationError(
                            item_path=nameserverkeys.get(name_server.position),
                                error_message=_('DUPLICATE_NS_POS')\
                                    % name_server.position))
                    else:
                        nameserverkeys[name_server.position] =\
                            name_server.get_vpath()
        return errors

    def validate_model(self, plugin_api_context):
        """
        The validation ensures that only one dns-client
        may be configured per node and that there are no
        duplicate nameserver positions.

        .. warning::
          - Only IPv4 and IPv6 addresses are permitted.
          - No more than 3 nameservers are permitted.
          - No more than 6 search names are permitted.
          - Search names are restricted to at most 256 characters in length.
        """
        errors = []
        nodes = plugin_api_context.query("node") + \
            plugin_api_context.query("ms")
        for node in nodes:
            clients = node.query("dns-client")
            num_clients = []
            for client in clients:
                if not client.is_for_removal():
                    num_clients.append(client)
            for client in num_clients:
                if len(num_clients) > 1:
                    errors.append(ValidationError(
                        item_path=client.get_vpath(),
                        error_message=_('ONLY_ONE_DNSCLIENT_PER_NODE')
                        ))
            for client in clients:
                errors.extend(self._validate_nameservers(client))
        return errors

    def _replace_right(self, source, target, replacement, replacements=None):
        return replacement.join(source.rsplit(target, replacements))

    def _upcase_first_letter(self, s):
        return s[0].upper() + s[1:]

    def create_configuration(self, plugin_api_context):
        """
        *Example CLI for setting up a DNS client configuration with \
        nameservers:*

        .. code-block:: bash

           litp create -t dns-client -p /deployments/local_vm/clusters/\
cluster1/nodes/node1/configs/dns_client -o \
search=exampleone.com,exampletwo.com,examplethree.com

           litp create -t nameserver -p /deployments/local_vm/\
clusters/cluster1/nodes/node1/configs/dns_client/\
nameservers/my_name_server_A -o ipaddress=10.10.10.1 position=1

           litp create -t nameserver -p /deployments/\
local_vm/clusters/cluster1/nodes/node1/configs/dns_client/\
nameservers/my_name_server_B -o ipaddress=10.10.10.7 position=2

           litp create -t nameserver -p /deployments/local_vm/\
clusters/cluster1/nodes/node1/configs/dns_client/\
nameservers/my_name_server_C -o ipaddress=2001:4860:0:1001::68 position=3

        *Example CLI for updating a nameserver:*

        .. code-block:: bash

          litp update -p /deployments/local_vm/clusters/cluster1/nodes/\
node1/configs/dns_client/nameservers/my_name_server_C -o ipaddress=192.168.1.1

        *Example CLI for removing a nameserver:*

        .. code-block:: bash

         litp remove -p /deployments/local_vm/clusters/cluster1/nodes/\
node1/configs/dns_client/nameservers/my_name_server_C

        For more information, see "Manage DNS Client Configuration" \
from :ref:`LITP References <litp-references>`.

         """

        tasks = []
        task = None
        nodes = plugin_api_context.query("node") +\
            plugin_api_context.query("ms")
        for node in nodes:
            clients = node.query("dns-client")
            for client in clients:
                client_searches = ""
                if getattr(client, "search", None):
                    client_searches = client.search.replace(',', ' ')
                name_1, name_2, name_3 = "", "", ""
                nameserver_update = False
                for nameserver in client.nameservers:
                    if nameserver.is_updated():
                        nameserver_update = True
                    elif (nameserver.is_initial() and not client.is_initial()
                          and not client.is_for_removal()):
                        nameserver_update = True
                    elif (nameserver.is_for_removal()
                          and not client.is_initial()
                          and not client.is_for_removal()):
                        nameserver_update = True
                    if not nameserver.is_for_removal():
                        if nameserver.position == '1':
                            name_1 = nameserver.ipaddress
                        elif nameserver.position == '2':
                            name_2 = nameserver.ipaddress
                        elif nameserver.position == '3':
                            name_3 = nameserver.ipaddress
                call_id = "%s_%s" % (
                        node.hostname,
                        client.get_vpath())
                operation = ""
                if client.is_initial():
                    operation = "create DNS client configuration"
                elif client.is_updated() or nameserver_update is True:
                    operation = "update DNS client configuration"
                elif client.is_for_removal():
                    operation = "remove DNS client configuration"
                    client_searches = ""
                conf_desc1 = ("%s on node \"%s\"" %
                            (operation, node.hostname))
                if nameserver_update or not client.is_applied():
                    task = ConfigTask(
                            node,
                            client,
                            self._upcase_first_letter(conf_desc1),
                            "dnsclient::nameserver",
                            call_id,
                            search=client_searches,
                            name1=name_1,
                            name2=name_2,
                            name3=name_3
                            )
                    for nameserver in client.nameservers:
                        task.model_items.add(nameserver)
                    task.model_items.add(client.nameservers)
                    tasks.append(task)
        return tasks
