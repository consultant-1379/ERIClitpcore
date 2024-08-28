from litp.migration import BaseMigration
from litp.migration.operations import BaseOperation
from netaddr import IPNetwork

class NetworkPrefixOperation(BaseOperation):
    '''
    Migration operation for prefix-less IPv4 networks
    '''

    def __init__(self, item_type_id, property_name):
        '''
        :param item_type_id: Identifier of the new type for the property.
        :type  item_type_id: str
        :param property_name: Name of the property holding an IPv4 network
        :type  property_name: str
        '''

        self.item_type_id = item_type_id
        self.property_name = property_name

    def mutate_forward(self, model_manager):
        '''
        Rewrites the property holding an IPv4 network on all items of the type
        passed to the constructor so that prefix-less IPv4 networks have an
        explicit prefix derived from classful addressing rules. Values that do
        include a prefix are left untouched.

        :param model_manager: The model manager to add the new property to.
        :type model_manager: litp.core.model_manager.ModelManager
        '''
        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            if not hasattr(item, self.property_name):
                continue
            # We may already have a prefix
            network_spec = getattr(item, self.property_name)
            if not network_spec or '/' in network_spec:
                continue

            extant_network = IPNetwork(network_spec, implicit_prefix=True)
            new_value = '{0}/{1}'.format(network_spec, extant_network.prefixlen)
            item.set_property(self.property_name, new_value)

    def mutate_backward(self, model_manager):
        '''
        Does nothing, on the basis that we do not want to remove network
        prefixes.

        :param model_manager: The model manager to add the new property to.
        :type model_manager: litp.core.model_manager.ModelManager
        '''
        pass


class Migration(BaseMigration):
    '''
    Migrates potentially prefix-less IPv4 network values present in properties.
    '''

    version = '1.9.13'
    operations = [NetworkPrefixOperation('network', 'subnet')]
