from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property, PropertyType
from litp.core.model_type import Collection
from litp.core.validators import ItemValidator, ValidationError


class Dummy13781Extension(ModelExtension):
    """Truncated version of networkapi extension"""

    def define_property_types(self):
        return [
            PropertyType('bonding_mode',
                regex=r'^(0|balance-rr|'
                         '1|active-backup|'
                         '2|balance-xor|'
                         '3|broadcast|'
                         '4|802.3ad|'
                         '5|balance-tlb|'
                         '6|balance-alb)$',
                regex_error_desc='Value must be a valid Bond mode'
            ),
            PropertyType('arp_validate',
                regex=r'^(0|none|'
                         '1|active|'
                         '2|backup|'
                         '3|all)$',
                regex_error_desc='Value must be one of "none", "0", "active", '
                                 '"1", "backup", "2", "all", or "3"',
            )
        ]



    def define_item_types(self):
        return [
            ItemType('bond',
                extend_item='network-interface',
                mode=Property('bonding_mode',
                    prop_description='Bonding mode. '
                                     'Options are 0, 1, 2, 3, 4, 5, 6, '
                                     'balance-rr, active-backup, balance-xor, '
                                     'broadcast, 802.3ad, balance-tlb, '
                                     'balance-alb',
                    required=False,
                    default='1'),
                arp_validate=Property('arp_validate',
                    required=False,
                    updatable_rest=True,
                    updatable_plugin=False),
                validators=[ArpPropertiesValidator()]
            )
        ]


class ArpPropertiesValidator(ItemValidator):

    @staticmethod
    def _arp_monitoring(properties):
        arp_prop_names = ['arp_interval', 'arp_ip_target',
                          'arp_validate', 'arp_all_targets']
        return any(properties.get(prop) for prop in arp_prop_names)

    def validate(self, properties):
        validate = properties.get('arp_validate')
        mode = properties.get('mode')

        if validate and mode not in ['1', 'active-backup']:
            msg = '"arp_validate" is only supported with "mode" property ' \
                  'set to "1" or "active-backup"'
            return ValidationError(property_name='mode',
                                   error_message=msg)

        if mode not in ['0', 'balance-rr',
                        '1', 'active-backup',
                        '2', 'balance-xor',
                        '3', 'broadcast'] and \
            ArpPropertiesValidator._arp_monitoring(properties):

            msg = 'ARP monitoring is only supported with "mode" property ' \
                  'set to one of the following: "0", "balance-rr", ' \
                  '"1", "active-backup", "2", "balance-xor", ' \
                  '"3", "broadcast"'

            return ValidationError(property_name='mode',
                                   error_message=msg)
