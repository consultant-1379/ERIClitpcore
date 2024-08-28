from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import PropertyType
from litp.core.validators import ValidationError
from litp.core.validators import ItemValidator
from litp.core.validators import NotEmptyStringValidator


class Story6861Extension(ModelExtension):

    def define_property_types(self):
        return[
            PropertyType(
                'some_string',
                regex=r'^.*$',
                validators=[NotEmptyStringValidator()]
            )
        ]

    def define_item_types(self):

        return [
            ItemType(
                'story6861',
                extend_item='software-item',
                validators=[Validator()],
                name=Property('any_string'),
                description=Property('some_string', updatable_plugin=True),
                fail=Property('path_string', updatable_plugin=True)
            )
        ]

class Validator(ItemValidator):
    def validate(self, properties):
        if properties.get('description') == 'model_item_validation_fail' and \
                properties.get('fail') == '/fail/path/property':
            return ValidationError("Story6861 Error TC02")
