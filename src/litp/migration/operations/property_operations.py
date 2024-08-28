from litp.migration.operations import BaseOperation
from litp.core.litp_logging import LitpLogger
from litp.core.model_type import Property

log = LitpLogger()


class AddProperty(BaseOperation):
    """
    Operation which adds a new property type to the model.
    """

    def __init__(self, item_type_id, property_name, property_value=''):
        """
        :param item_type_id: Identifier of the new type for the property.
        :type  item_type_id: str
        :param property_name: Name of the property to be added to the model.
        :type  property_name: str
        :param property_value: Value to set the new property to.
        :type  property_value: str

        """
        self.item_type_id = item_type_id
        self.property_name = property_name
        self.property_value = property_value

    def mutate_forward(self, model_manager):
        """
        Migrate the model forward by adding the new property.
        :param model_manager: The model manager to add the new property to.
        :type model_manager: litp.core.model_manager.ModelManager

        """
        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            log.trace.info("Adding property '%s' to '%s'" %
                           (self.property_name, item.get_vpath()))
            item.update_properties({self.property_name: self.property_value})

    def mutate_backward(self, model_manager):
        """
        Migrate the model backwards by removing the new property.
        :param model_manager: The model manager to add the new property to.
        :type model_manager: litp.core.model_manager.ModelManager

        """
        if self.property_name not in \
                model_manager.item_types[self.item_type_id].structure:
            log.trace.info(
                'Invalid property \'{it}\' - continuing migration'.format(
                    it=self.property_name
                )
            )

        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            log.trace.info("Removing property '%s' from '%s'" %
                           (self.property_name, item.get_vpath()))
            item.update_properties({self.property_name: None})


class RemoveProperty(AddProperty):
    """
    Operation which removes a property type from the model.
    Note: If a property_value is specified it will be used as a default \
          value for backward migrations.
    """

    def mutate_forward(self, model_manager):
        """
        Migrate the model forwards by removing a property.
        :param model_manager: The model manager to remove the property from.
        :type model_manager: litp.core.model_manager.ModelManager

        """
        super(RemoveProperty, self).mutate_backward(model_manager)

    def mutate_backward(self, model_manager):
        """
        Migrate the model backwards by adding a property.
        :param model_manager: The model manager to add the property to.
        :type model_manager: litp.core.model_manager.ModelManager

        """
        super(RemoveProperty, self).mutate_forward(model_manager)


class RenameProperty(BaseOperation):
    """
    Operation which renames a property type in the model.
    """

    def __init__(self, item_type_id, old_property_name, new_property_name):
        """
        :param item_type_id: Identifier type of the property to be renamed.
        :type  item_type_id: str
        :param old_property_name: Name of the property to be renamed from.
        :type  old_property_name: str
        :param new_property_value: Name of the property to be renamed to.
        :type  new_property_value: str

        """

        self.item_type_id = item_type_id
        self.old_property_name = old_property_name
        self.new_property_name = new_property_name

    def _rename_property(self, item, old_property_name,
                        new_property_name, model_manager):
        old_property = item.item_type.structure.get(old_property_name)
        if not (old_property and isinstance(old_property, Property)):
            raise ValueError(
                "Property '{0}' is not present on item type '{1}'".format(
                    old_property_name,
                    self.item_type_id
                )
            )

        old_property_value = getattr(item, old_property_name, None)
        if old_property_value:
            log.trace.info("Renaming property '%s' to '%s' on '%s'" %
                           (old_property_name,
                            new_property_name,
                            item.get_vpath()))
            item.update_properties({new_property_name: old_property_value})
            item.update_properties({old_property_name: None})

    def mutate_forward(self, model_manager):
        """
        Migrate the model forwards by renaming a property.
        :param model_manager: The model manager to rename the property in.
        :type model_manager: litp.core.model_manager.ModelManager

        """

        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            self._rename_property(
                item, self.old_property_name, self.new_property_name,
                    model_manager)

    def mutate_backward(self, model_manager):
        """
        Migrate the model backwards by restoring the name of a property.
        :param model_manager: The model manager to restore the property name\
            in.
        :type model_manager: litp.core.model_manager.ModelManager

        """

        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            self._rename_property(
                item, self.new_property_name, self.old_property_name,
                    model_manager)
