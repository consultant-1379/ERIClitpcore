from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.core.exceptions import ViewError

class Dummy10168Extension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "cluster10168",
                extend_item="cluster",
                ordering_behaviour=Property(
                    "basic_string",
                    default="forward",
                ),
                node_upgrade_ordering=View(
                    "basic_list",
                    Dummy10168Extension.view_behaviours_dispatcher
                ),
            ),
            ItemType(
                "cluster10168_no_view",
                extend_item="cluster",
            )
        ]

    @staticmethod
    def view_behaviours_dispatcher(plugin_api_context, view_query_item):
        handlers = {
            'forward': Dummy10168Extension.forward_order,
            'reverse': Dummy10168Extension.reverse_order,
            'deliberate_exception': Dummy10168Extension.deliberate_view_error,
            'uncaught_exception': Dummy10168Extension.uncaught_exception,
            'non_list_object': Dummy10168Extension.non_list,
            'malformed': Dummy10168Extension.malformed_list,
            'incomplete': Dummy10168Extension.incomplete_list,
            'none': Dummy10168Extension.return_none,
        }
        return handlers[view_query_item.ordering_behaviour](plugin_api_context, view_query_item)

    @staticmethod
    def forward_order(context, view_qi):
        node_item_ids = []
        for node_qi in view_qi.nodes:
            node_item_ids.append(str(node_qi.item_id))
        node_item_ids.sort()
        return node_item_ids

    @staticmethod
    def reverse_order(context, view_qi):
        node_item_ids = []
        for node_qi in view_qi.nodes:
            node_item_ids.append(str(node_qi.item_id))
        node_item_ids.sort(reverse=True)
        return node_item_ids

    @staticmethod
    def deliberate_view_error(context, view_qi):
        raise ViewError("Oh noes!")

    @staticmethod
    def uncaught_exception(context, view_qi):
        return 1/0

    @staticmethod
    def non_list(context, view_qi):
        return {'A': 42, 'Q': None}

    @staticmethod
    def malformed_list(context, view_qi):
        return [1,2,3]

    @staticmethod
    def return_none(context, view_qi):
        return None

    @staticmethod
    def incomplete_list(context, view_qi):
        ids = Dummy10168Extension.forward_order(context, view_qi)
        ids.pop()
        return ids
