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
from litp.core.task import ConfigTask

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class LinuxFirewallPlugin(Plugin):
    """
    LITP linux firewall plugin.

    Provides configuration of iptables and ip6tables.

    """
    DEFAULT_ACTION = 'accept'
    DEFAULT_PROTO = 'tcp'
    DEFAULT_STATE = 'NEW'
    DEFAULT_CHAIN = 'INPUT'
    DEFAULT_PROVIDER = 'iptables'
    OUTPUT_CHAIN = 'OUTPUT'
    IP6TABLES_PROVIDER = 'ip6tables'
    DEFAULT_PREPEND = '1'
    IPV6 = ' ipv6'

    def _validate_firewall_rule_name_conflicts(self, nodes, clusters):
        errors = []
        for node in nodes:
            rules = node.query("firewall-rule")
            rules_by_name = {}
            for rule in rules:
                rules_list = rules_by_name.get(rule.name, [])
                rules_list.append(rule.get_vpath())
                rules_by_name[rule.name] = rules_list
            for cluster in clusters:
                if node in cluster.nodes:
                    cluster_rules = cluster.configs.\
                                        query("firewall-rule")
                    for rule in cluster_rules:
                        rules_list = rules_by_name.get(
                                rule.name, [])
                        rules_list.append(rule.get_vpath())
                        rules_by_name[rule.name] = rules_list

            for rule_name, rule_paths in rules_by_name.iteritems():
                if len(rule_paths) > 1:
                    errors.extend([
                        ValidationError(
                            item_path=rule_path,
                            error_message=(
                                "%s is not unique on node %s"
                                % (rule_name, node.hostname))
                        ) for rule_path in rule_paths]
                    )
        return errors

    def _validate_firewall_config_conflicts(self, clusters):
        errors = []
        for cluster in clusters:
            cluster_configs = cluster.query('firewall-cluster-config')
            for cconfig in cluster_configs:
                node_configs = cluster.query('firewall-node-config')
                for nconfig in node_configs:
                    if cconfig.drop_all != nconfig.drop_all:
                        errors.append(
                            ValidationError(
                                item_path=cconfig.get_vpath(),
                                error_message=(
                                    "Conflicting firewall "
                                    "config drop_all selection: "
                                    "set to '%s' at cluster level"
                                    % (cconfig.drop_all))))
                        errors.append(
                            ValidationError(
                                item_path=nconfig.get_vpath(),
                                error_message=(
                                    "Conflicting firewall "
                                    "config drop_all selection: "
                                    "set to '%s' at node level"
                                    % (nconfig.drop_all))))
        return errors

    def validate_model(self, plugin_api_context):
        """
        This plugin validates the model to ensure that:

        - 'firewall-node-config' and 'firewall-cluster-config' model items \
don't have conficting 'drop_all' values
        - 'firewall-rule' model items don't have conflicting 'name' values

        """
        errors = []

        nodes = (plugin_api_context.query("node") +
                 plugin_api_context.query("ms"))
        clusters = plugin_api_context.query("cluster")

        errors.extend(self._validate_firewall_config_conflicts(clusters))
        errors.extend(
                self._validate_firewall_rule_name_conflicts(nodes, clusters))

        return errors

    def create_configuration(self, plugin_api_context):
        """
        This plugin provides tasks to configure iptables and ip6tables \
based on the specified firewall rules and configuration.

        *Example CLI for configuring a rule on a cluster"

        .. code-block:: bash

            litp create -p /deployments/dep1/clusters/c1/configs/fw_config \
-t firewall-cluster-config -o drop_all=false
            litp create -p /deployments/dep1/clusters/c1/configs/fw_config/\
rules/fw_001 -t firewall-rule -o name="0010 basetcp" dport="9999

        *Example CLI for configuring a rule on a node*

        .. code-block:: bash

            litp create -p /deployments/dep1/clusters/c1/nodes/node1/\
configs/fw_node_config -t firewall-cluster-config -o drop_all=true
            litp create -p /deployments/dep1/clusters/c1/nodes/node1/\
configs/fw_node_config/fw_001 -t firewall-rule -o name="0110 basetcp" \
dport="9999,1234"

        *Example XML for configuring a rule on a node*

        .. code-block:: bash
            <?xml version='1.0' encoding='utf-8'?>
            <litp:firewall-node-config xmlns:xsi="http://www.w3.org/2001/XML\
Schema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation=\
"http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="fw_node_config">
                <drop_all>true</drop_all>
                <rules>
                    <litp:firewall-rule id="fw_001">
                        <dport>1234,9999</dport>
                        <name>0110 basetcp</name>
                    </litp:firewall-rule>
                </rules>
            </litp:firewall-node-config>
        """
        tasks = []
        for node in plugin_api_context.query("node") + \
                    plugin_api_context.query("ms"):
            for firewall_config in node.query("firewall-node-config"):
                for rule in firewall_config.rules:
                    if rule.is_initial() or rule.is_updated():
                        tasks.extend(self.create_firewall_tasks(
                            node, rule))
                if firewall_config.is_initial() or \
                        firewall_config.is_updated():
                    tasks.append(self.create_firewall_config_task(
                        node, firewall_config, firewall_config.drop_all))

        for cluster in plugin_api_context.query("cluster"):
            for firewall_config in cluster.query("firewall-cluster-config"):
                for node in cluster.nodes:
                    for rule in firewall_config.rules:
                        if rule.is_initial() or rule.is_updated() or \
                                node.is_initial():
                            tasks.extend(self.create_firewall_tasks(
                                node, rule, cluster.item_id))
                    if firewall_config.is_initial() or \
                            firewall_config.is_updated():
                        tasks.append(self.create_firewall_config_task(
                            node, firewall_config,
                            firewall_config.drop_all, cluster.item_id))

        return tasks

    def create_firewall_tasks(self, node, rule, cluster_id=''):
        tasks = []
        task_props = {}
        allproviders = False
        allchains = False

        values = {"name": rule.name}
        if not rule.chain:
            allchains = True
        if not rule.provider:
            allproviders = True

        if rule.proto:
            values["proto"] = rule.proto
        if rule.action:
            values["action"] = rule.action
        else:
            if not rule.jump:
                values["action"] = self.DEFAULT_ACTION

        if rule.sport:
            sportlist = rule.sport.split(',')
            values["sport"] = sportlist
            # if state or proto not set, set to defaults
            if not rule.state:
                values["state"] = self.DEFAULT_STATE
            if not rule.proto:
                values["proto"] = self.DEFAULT_PROTO
        if rule.dport:
            dportlist = rule.dport.split(',')
            values["dport"] = dportlist
            # if state or proto not set, set to defaults
            if not rule.state:
                values["state"] = self.DEFAULT_STATE
            if not rule.proto:
                values["proto"] = self.DEFAULT_PROTO

        if rule.state:
            # split state if it has a ','
            statelist = rule.state.split(',')
            values["state"] = statelist
        if rule.source:
            if '-' in rule.source:
                values["src_range"] = rule.source
            else:
                values["source"] = rule.source
        if rule.destination:
            if '-' in rule.destination:
                values["dst_range"] = rule.destination
            else:
                values["destination"] = rule.destination
        if rule.iniface:
            values["iniface"] = rule.iniface
        if rule.outiface:
            values["outiface"] = rule.outiface
        if rule.icmp:
            values["icmp"] = rule.icmp
        if rule.chain:
            values["chain"] = rule.chain
        else:
            values["chain"] = self.DEFAULT_CHAIN
        if rule.provider:
            values["provider"] = rule.provider
        else:
            values["provider"] = self.DEFAULT_PROVIDER
        if rule.log_level:
            values["log_level"] = rule.log_level
        if rule.log_prefix:
            values["log_prefix"] = rule.log_prefix
        if rule.jump:
            values["jump"] = rule.jump
        if rule.table:
            values["table"] = rule.table
        if rule.toports:
            values["toports"] = rule.toports
        if rule.setdscp:
            values["setdscp"] = rule.setdscp
        values['title'] = rule.name.replace(" ", "_")
        task_props['rule1'] = values

        if allchains:
            # clone values and set chain
            valuesoutput = values.copy()
            valuesoutput["chain"] = self.OUTPUT_CHAIN
            # generate unique name
            valuesoutput["name"] = (self.DEFAULT_PREPEND + str(values["name"]))
            if rule.iniface:
                valuesoutput["outiface"] = valuesoutput["iniface"]
                valuesoutput.pop("iniface")
            task_props['rule2'] = valuesoutput

        if allproviders:
            ipv4addrs = False
            # should not clone an ipv4 rule which includes ipv4 addr
            if rule.source:
                if not ":" in rule.source:
                    ipv4addrs = True
            if rule.destination:
                if not ":" in rule.destination:
                    ipv4addrs = True
            if not ipv4addrs:
                # clone values and set chain
                valuesip6 = values.copy()
                valuesip6["provider"] = self.IP6TABLES_PROVIDER
                valuesip6["name"] = str(values["name"] + self.IPV6)
                task_props['rule3'] = valuesip6

                if allchains:
                    # clone values and set chain
                    valuesip6out = valuesip6.copy()
                    valuesip6out["chain"] = self.OUTPUT_CHAIN
                    valuesip6out["name"] = self.DEFAULT_PREPEND + \
                            str(valuesip6["name"])
                    if rule.iniface:  # change to outiface
                        valuesip6out["outiface"] = valuesip6out["iniface"]
                        valuesip6out.pop("iniface")
                    task_props['rule4'] = valuesip6out

        rule_id = "%s_%s_%s" % (cluster_id, node.item_id, rule.item_id)
        firewall_rule_task = self.create_firewall_rule_task(
                node, rule, rule_id, task_props)
        tasks.append(firewall_rule_task)
        return tasks

    def create_firewall_rule_task(self, node, rule, rule_id, properties):
        action = "Adding"
        if rule.is_updated():
            action = "Updating"
        desc = '%s firewall rule "%s" on %s' % (
                                    action, rule.name, node.hostname)
        return ConfigTask(
                          node=node,
                          model_item=rule,
                          description=desc,
                          call_type="firewalls::rules",
                          call_id=rule_id,
                          **properties
        )

    def create_firewall_config_task(self, node, config, drop_all,
                                    cluster_id=''):
        action = "Adding"
        drop_all_snippet = ""
        if config.is_updated():
            action = "Updating"
        if drop_all == "true":
            drop_all_snippet = "and drop all rules "
        desc = '%s LITP firewall rules %son %s' % (
                                  action, drop_all_snippet, node.hostname)
        config_id = "%s_%s_%s" % (cluster_id, node.item_id, config.item_id)
        return ConfigTask(
                          node=node,
                          model_item=config,
                          description=desc,
                          call_type="firewalls::config",
                          call_id=config_id,
                          drop_all=drop_all
        )
