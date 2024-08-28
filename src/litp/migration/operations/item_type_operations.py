from litp.migration.operations import BaseOperation
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class RenameItemType(BaseOperation):

    def __init__(self, current_item_type_id, new_item_type_id):
        """
        :param current_item_type_id: Identifier of the item type to be renamed.
        :type  current_item_type_id: str
        :param new_item_type_id: Identifier of the item type to be renamed to.
        :type  new_item_type_id: str

        """

        self.current_item_type_id = current_item_type_id
        self.new_item_type_id = new_item_type_id

    def mutate_forward(self, model_manager):
        """
        Migrate the model forward by renaming the item type.
        :param model_manager: The model manager to rename the item type in.
        :type model_manager: litp.core.model_manager.ModelManager

        """
        if self.new_item_type_id not in model_manager.item_types:
            raise ValueError(
                'Invalid item type {it}'.format(
                    it=self.new_item_type_id
                )
            )

        matched_items = model_manager.find_modelitems(
            self.current_item_type_id)
        for item in matched_items:
            log.trace.info(
                'Converting {vpath} to item type {it}'.format(
                    vpath=item.vpath,
                    it=self.new_item_type_id
                )
            )
            item._item_type = model_manager.item_types.get(
                self.new_item_type_id, None)

    def mutate_backward(self, model_manager):
        """
        Migrate the model backwards by restoring the previous name of the \
            item type.
        :param model_manager: The model manager to restore the renamed item \
            type in.
        :type model_manager: litp.core.model_manager.ModelManager

        """
        if self.new_item_type_id not in model_manager.item_types:
            raise ValueError(
                'Invalid item type {it}'.format(
                    it=self.new_item_type_id
                )
            )

        matched_items = model_manager.find_modelitems(self.new_item_type_id)
        for item in matched_items:
            log.trace.info(
                'Converting {vpath} to item type {it}'.format(
                    vpath=item.vpath,
                    it=self.current_item_type_id
                )
            )
            item._item_type = model_manager.item_types.get(
                self.current_item_type_id, None)
