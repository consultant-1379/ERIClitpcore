from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.core.exceptions import ViewError


class FuturePropertyExtension(ModelExtension):
    def define_item_types(self):
        return [
            ItemType(
                "test_item",
                extend_item="software-item",
                name=Property("any_string"),
                version=Property("any_string", updatable_plugin=True),
                evaluate_once=Property("basic_boolean",
                    default="false"),
                viewerror_on_runtime=Property("basic_boolean",
                    default="false",
                    updatable_plugin=True),
                test_item_view=View("software-item",
                    FuturePropertyExtension.test_item_view),
                exception_view=View("software-item",
                    FuturePropertyExtension.exception_view),
                viewerror_view=View("software-item",
                    FuturePropertyExtension.viewerror_view),
                viewerror_on_runtime_view=View("software-time",
                    FuturePropertyExtension.viewerror_on_runtime_view),
            ),
        ]

    @staticmethod
    def test_item_view(model_manager, query_item):
        return 'PREFIX_' + query_item.version + '_SUFFIX'

    @staticmethod
    def viewerror_view(model_manager, query_item):
        raise ViewError("ViewError raised deliberately")

    @staticmethod
    def exception_view(model_manager, query_item):
        raise 1/0

    @staticmethod
    def viewerror_on_runtime_view(model_manager, query_item):
        if query_item.viewerror_on_runtime == "true":
            raise ViewError("ViewError raised deliberately on runtime")
        return "No error"
