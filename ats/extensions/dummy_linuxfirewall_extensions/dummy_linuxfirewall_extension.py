##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.model_type import ItemType, Property, PropertyType, Collection
from litp.core.extension import ModelExtension
from litp.core.validators import RestrictedPropertiesValidator

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class LinuxFirewallExtension(ModelExtension):
    """
    LinuxFirewall Model Extension
    """

    def define_property_types(self):
        restricted_names = [
            '000 puppet',
            '1000 puppet out',
            '001 mco',
            '1001 mco out',
            '002 ntp',
            '1002 ntp out',
            '996 cobblertcp',
            '1996 cobblertcp out',
            '997 cobblerudp',
            '1997 cobblerudp out',
            '998 ssh',
            '1998 ssh out',
            '900 related established',
            '1900 related established',
            '901 local loop',
            '1901 local loop',
            '000 puppet v6',
            '1000 puppet v6',
            '900 related established v6',
            '1900 related established v6',
            '901 local loop v6',
            '1901 local loop v6',
            '999 drop all',
            '1999 drop all',
            '999 drop all v6'
        ]
        property_types = []
        property_types.append(PropertyType("firewall_rule_name",
            regex=r"^[0-9]+[A-Za-z0-9 ]+$",
            validators=[RestrictedPropertiesValidator(restricted_names)]))
        property_types.append(PropertyType("firewall_rule_proto",
                                    regex=r"^(tcp|udp|icmp|ipv6-icmp|esp|ah|"\
                                          "vrrp|igmp|ipencap|ospf|gre|all)$"))
        property_types.append(PropertyType("firewall_rule_action",
                                           regex=r"^(accept|drop)$"))
        property_types.append(PropertyType("firewall_rule_port",
                                           regex=r"^[0-9,-]{0,}[0-9]+$"))
        property_types.append(PropertyType("firewall_rule_state",
                regex=r"^(NEW|ESTABLISHED|RELATED|INVALID|NEW,ESTABLISHED,"
                      "RELATED|ESTABLISHED,RELATED|RELATED,ESTABLISHED)$"))
        property_types.append(PropertyType("firewall_rule_ip_range",
                                           regex=r"^[0-9a-fA-F.:/-]+$"))
        property_types.append(PropertyType("firewall_rule_icmp",
                regex=r"^(0|8|echo-reply|echo-request)$"))
        property_types.append(PropertyType("firewall_rule_chain",
                regex=r"^(INPUT|OUTPUT|FORWARD|REROUTING|POSTROUTING)$"))
        property_types.append(PropertyType("firewall_rule_provider",
                                           regex=r"^(iptables|ip6tables)$"))
        property_types.append(PropertyType("firewall_rule_log_level",
            regex=r"^(panic|alert|crit|err|warn|warning|notice|info|debug)$"))
        property_types.append(PropertyType("firewall_rule_string",
                                           regex=r"^[A-Za-z_]+$"))
        property_types.append(PropertyType("firewall_rule_table",
            regex=r"^(nat|filter|mangle|raw|rawpost|broute)$"))
        property_types.append(PropertyType("firewall_rule_setdscp",
                                           regex=r"^0[xX][0-9a-fA-F]+$"))
        property_types.append(PropertyType("firewall_rule_limit",
            regex=r"^([0-9]+/sec|[0-9]+/min|[0-9]+/hour|[0-9]+/day)$"))
        return property_types

    def define_item_types(self):
        item_types = []
        item_types.append(
          ItemType("firewall-node-config",
                   extend_item="node-config",
                   item_description="A node level firewall configuration.",
                   drop_all=Property("basic_boolean",
                                     default="true",
                                     prop_description='Add the drop rule for'
                                                      ' iptables/ip6tables'),
                   rules=Collection("firewall-rule"))
        )
        item_types.append(
          ItemType("firewall-cluster-config",
                   extend_item="cluster-config",
                   item_description="A cluster level firewall configuration.",
                   drop_all=Property("basic_boolean",
                                     default="true",
                                     prop_description='Add the drop rule for'
                                                      ' iptables/ip6tables'),
                   rules=Collection("firewall-rule"))
        )
        item_types.append(
          ItemType("firewall-rule",
            item_description="A firewall rule.",

            name=Property("firewall_rule_name",
                          prop_description="name of the firewall rule",
                          required=True),
            proto=Property("firewall_rule_proto",
                           prop_description="rule protocol"),
            action=Property("firewall_rule_action",
                            prop_description="action: accept or drop"),
            sport=Property("firewall_rule_port",
                           prop_description="sport: source port"),
            dport=Property("firewall_rule_port",
                           prop_description="dport: destination port"),
            state=Property("firewall_rule_state",
                           prop_description="state"),
            source=Property("firewall_rule_ip_range",
                            prop_description="source ip/range"),
            destination=Property("firewall_rule_ip_range",
                                 prop_description="destination ip/range"),
            iniface=Property("basic_string",
                             prop_description="iniface network interface"),
            outiface=Property("basic_string",
                              prop_description="outiface network interface"),
            icmp=Property("firewall_rule_icmp",
                          prop_description="icmp"),
            chain=Property("firewall_rule_chain",
                           prop_description="chain"),
            provider=Property("firewall_rule_provider",
                              prop_description="provider iptables/ip6tables"),
            limit=Property("firewall_rule_limit",
                           prop_description="limit"),
            log_level=Property("firewall_rule_log_level",
                               prop_description="log level"),
            log_prefix=Property("firewall_rule_string",
                                prop_description="log prefix"),
            jump=Property("firewall_rule_string",
                          prop_description="jump"),
            table=Property("firewall_rule_table",
                           prop_description="table"),
            toports=Property("firewall_rule_port",
                             prop_description="toports"),
            setdscp=Property("firewall_rule_setdscp",
                             prop_description="setdscp")
          )
        )
        return item_types
