from litp.core.model_type import PROPERTY_READ
from litp.core.model_type import PROPERTY_WRITE
from litp.core.model_type import Property
from litp.core.model_type import View
from litp.core.model_type import Collection
from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.core.validators import ValidationError
from litp.core.litp_logging import LitpLogger
import litp.core.constants as constants


log = LitpLogger()


class ModelValidator(object):
    def __init__(self, model_manager):
        self.model_manager = model_manager

    def validate_properties(self, item_type, properties,
                            access=PROPERTY_WRITE, is_reference=False):
        errors = []

        errors.extend(self._check_allowed_properties(item_type, properties))
        errors.extend(self._check_property_access(
            item_type, properties, access))
        # If validation errors occur for property, skip item type validation
        prop_valid_errors = self._run_property_validators(
                item_type, properties)
        if prop_valid_errors:
            errors.extend(prop_valid_errors)
        if not is_reference:
            errors.extend(
                self._check_required_properties(item_type, properties))
            if not prop_valid_errors:
                errors.extend(
                    self._run_item_type_validators(item_type, properties))
        return errors

    def _check_allowed_properties(self, item_type, properties):
        errors = []
        for prop_name in properties:
            if not (
                prop_name in item_type.structure and
                isinstance(item_type.structure[prop_name], (Property, View))
            ):
                errors.append(ValidationError(
                    property_name=prop_name,
                    error_message=(
                        '"%s" is not an allowed property of %s' %
                        (prop_name, item_type.item_type_id)),
                    error_type=constants.PROP_NOT_ALLOWED_ERROR
                ))
        return errors

    def _check_property_access(self, item_type, properties, access):
        errors = []
        if access == PROPERTY_READ:
            return errors
        for prop_name in properties:
            if prop_name not in item_type.structure:
                continue
            ptype = item_type.structure[prop_name]
            if isinstance(ptype, View):
                errors.append(ValidationError(
                    property_name=prop_name,
                    error_message=(
                        '"%s" is a read-only view of %s' %
                        (prop_name, item_type.item_type_id)),
                    error_type=constants.PROP_NOT_ALLOWED_ERROR
                ))
        return errors

    def _run_property_validators(self, item_type, properties):
        errors = []
        for name, instance in item_type.structure.iteritems():
            if isinstance(instance, Property) and name in properties:
                errors.extend(self._run_property_type_validators(
                    instance.prop_type, name, properties[name]))
        return errors

    def _run_property_type_validators(self, property_type,
                                      property_name, property_value):
        errors = []
        for validator in property_type.validators:
            err = validator.validate(property_value)
            if err:
                # If a property validation error occurs, return error
                # immediately and skip other validations for that property
                err.property_name = property_name
                errors.append(err)
                return errors
        return errors

    def _clear_property_validator(self, item, name):
        errors = []
        prop = item.item_type.structure[name]
        if not item.source and prop.required and prop.default is None:
            errors.append(ValidationError(
                property_name=name,
                error_message=(
                    'ItemType "%s" is required to have a '
                    'property with name "%s"' %
                    (item.item_type.item_type_id, name)
                ),
                error_type=constants.MISSING_REQ_PROP_ERROR
            ))
        return errors

    def _check_required_properties(self, item_type, properties):
        errors = []
        for name, instance in item_type.structure.iteritems():
            if not (
                isinstance(instance, Property) and
                instance.required and
                name not in properties
            ):
                continue
            if not instance.default:
                errors.append(ValidationError(
                    property_name=name,
                    error_message=(
                        'ItemType "%s" is required to have a '
                        'property with name "%s"' %
                        (item_type.item_type_id, name)
                    ),
                    error_type=constants.MISSING_REQ_PROP_ERROR
                ))
        return errors

    def _run_item_type_validators(self, item_type, properties):
        errors = []
        for validator in item_type.validators:
            err = validator.validate(properties)
            if err:
                errors.append(err)
        return errors

    def validate_item_type(self, item_type, item, properties=None,
                           access=PROPERTY_WRITE):
        """Validates the given ModelItem instance with regards to its ItemType.

        Checks that the ModelItem instance has the required children.
        Validate that the Collection structural members of the given ItemType
        have an acceptable number of items within them.
        Validates the properties of the given ModelItem instance.

        :param item_type: ItemType of the ModelItem to validate
        :type  instance: :class:`litp.core.model_type.ItemType`
        :param   item: ModelItem instance to validate
        :type    item: :class:`litp.core.model_item.ModelItem`

        :returns: A list either empty or containing Exception objects
        :rtype:   list
        """
        errors = []

        if isinstance(item, (CollectionItem, RefCollectionItem)):
            return errors

        properties = item.get_merged_properties(skip_views=True)

        for err in self._check_required_children(
                item_type, item.children):
            if not err.item_path:
                err.item_path = item.vpath
            errors.append(err)

        for name, instance in item_type.structure.iteritems():
            if name not in item.children:
                continue
            child_item = item.children[name]

            err = self._validate_item_type_instance(instance, child_item)
            if err:
                errors.extend(err)

        for err in self.validate_properties(item_type, properties, access):
            err.item_path = item.vpath
            errors.append(err)

        return errors

    def _check_required_children(self, item_type, children):
        errors = []
        err_msg = 'ItemType "%s" is required to have a "%s" with name ' \
                  '"%s" and type "%s"'
        for name, instance in item_type.structure.iteritems():
            if isinstance(instance, (Property, View, Collection)):
                continue
            if not instance.required:
                continue
            if name not in children:
                msg = err_msg % (
                    item_type.item_type_id,
                    instance.__class__.__name__.lower(),
                    name,
                    instance.item_type_id
                )
                errors.append(ValidationError(
                    item_path='',
                    error_message=msg,
                    error_type=constants.MISSING_REQ_ITEM_ERROR
                ))
            else:
                child_item = children[name]
                if (
                    child_item.is_for_removal() and
                    not child_item.parent.is_for_removal()
                ):
                    errors.append(ValidationError(
                        item_path=child_item.vpath,
                        error_message=(
                            "This item is required and cannot be removed"),
                        error_type=constants.MISSING_REQ_ITEM_ERROR
                    ))
        return errors

    def _validate_item_type_instance(self, instance, item):
        """Validate the number of children in a Collection.

        Ensure that a Collection has not less than the minimum or not
        more than the maximum number of allowed items within it.

        :param instance: Structural member of the ModelItems ItemType
        :type  instance: :class:`litp.core.model_type._BaseStructure`
        :param   item: ModelItem to instance validate
        :type    item: :class:`litp.core.model_item.ModelItem`

        :returns: A list either empty or containing Exception objects
        :rtype:   list
        """
        errors = []
        if isinstance(instance, Collection):
            children_present = []
            if (
                item.parent_vpath and
                (item.parent.is_for_removal() or item.parent.is_removed())
            ):
                children_present = item.children
            else:
                children_present = [
                    child for child in item.children.itervalues()
                    if not child.is_for_removal() and not child.is_removed()
                ]

            if len(children_present) < instance.min_count:
                errors.append(ValidationError(
                    item_path=item.vpath,
                    error_message=(
                        "This collection requires a minimum of %s "
                        "items not marked for removal" % instance.min_count),
                    error_type=constants.CARDINALITY_ERROR
                ))
            elif len(children_present) > instance.max_count:
                errors.append(ValidationError(
                    item_path=item.vpath,
                    error_message=(
                        "This collection is limited to a maximum of %s "
                        "items not marked for removal" % instance.max_count),
                    error_type=constants.CARDINALITY_ERROR
                ))
        return errors
