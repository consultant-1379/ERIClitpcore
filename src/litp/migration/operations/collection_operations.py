from litp.migration.operations import BaseOperation
from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class AddCollectionBase(BaseOperation):
    def __init__(self, item_type_id, collection_name, collection_item_type):
        self.item_type_id = item_type_id
        self.collection_name = collection_name
        self.collection_item_type = collection_item_type
        self._log_template = None

    def _create_collection(self, model_manager, parent, item_type, item_id):
        raise NotImplementedError

    def mutate_forward(self, model_manager):
        if self.collection_item_type not in model_manager.item_types:
            raise ValueError(
                'Invalid item type {it}'.format(
                    it=self.collection_item_type
                )
            )
        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            item_type = model_manager.item_types[self.collection_item_type]
            if self._log_template:
                log.trace.info(
                    self._log_template.format(
                        col=self.collection_name,
                        type=self.collection_item_type,
                        vpath=item.vpath
                    )
                )
            collection = self._create_collection(
                model_manager, item, item_type, self.collection_name)
            if item.source_vpath:
                collection.source_vpath = \
                    item.source_vpath + "/" + self.collection_name

    def mutate_backward(self, model_manager):
        pass


class AddCollection(AddCollectionBase):
    """
    Operation which adds a new collection type to the model.
    """

    def __init__(self, item_type_id, collection_name, collection_item_type):
        """
        :param item_type_id: Identifier of the ItemType that has \
                                the collection.
        :type  item_type_id: str
        :param collection_name: Name of a collection to be put into the \
                                ItemType. It's an item_id.
        :type  collection_name: str
        :param collection_item_type: Identifier of the ItemType that the \
                                collection stores.
        :type  collection_item_type: str

        """
        super(AddCollection, self).__init__(item_type_id, collection_name,
                                collection_item_type)
        self._log_template = 'Creating Collection \'{col}\' of type {type} '\
            'on {vpath}'

    def _create_collection(self, model_manager, parent, item_type, item_id):
        return model_manager._create_collection_item(
            parent, item_type, item_id, None)


class AddRefCollection(AddCollectionBase):
    """
    Operation which adds a new reference collection type to the model.
    """
    def __init__(self, item_type_id, collection_name, collection_item_type):
        """
        :param item_type_id: Identifier of the ItemType that has \
                                the reference collection.
        :type  item_type_id: str
        :param collection_name: Name of a reference collection to be \
                                put into the ItemType. It's an item_id.
        :type  collection_name: str
        :param collection_item_type: Identifier of the ItemType that the \
                                reference collection stores.
        :type  collection_item_type: str

        """

        super(AddRefCollection, self).__init__(item_type_id, collection_name,
                                collection_item_type)
        self._log_template = 'Creating RefCollection \'{col}\' of type {type}'\
            ' on {vpath}'

    def _create_collection(self, model_manager, parent, item_type, item_id):
        return model_manager._create_refcollection_item(
            parent, item_type, item_id, None)


class UpdateCollectionType(BaseOperation):
    """
    Operation which updates the item type contained by a \
collection in the model.
    """

    def __init__(self, item_type_id, collection_name,
                 old_item_type, new_item_type):
        """
        :param item_type_id: Identifier of the ItemType that has \
                             the collection.
        :type  item_type_id: str
        :param collection_name: Name of the collection to update.
        :type  collection_name: str
        :param old_item_type: Old ItemType of the collection.
        :type  old_item_type: str
        :param old_item_type: New ItemType of the collection.
        :type  old_item_type: str

        """
        self.item_type_id = item_type_id
        self.collection_name = collection_name
        self.old_item_type = old_item_type
        self.new_item_type = new_item_type

    def mutate_forward(self, model_manager):
        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            if self.collection_name in item.children:
                collection = getattr(item, self.collection_name)

                new_item_type = model_manager.item_types[self.new_item_type]
                old_item_type = model_manager.item_types[self.old_item_type]
                if len(collection) > 0:
                    # We can only allow changing  the collection type to a
                    # supertype, eg. disk -> disk-base
                    if not new_item_type in \
                            model_manager._all_supertypes(old_item_type):
                        log.trace.info('Cannot convert collection {vpath} ' \
                            'from \'{old_it}\' to non-supertype ' \
                            '\'{new_it}\''.format(
                                vpath=collection.vpath,
                                old_it=self.old_item_type,
                                new_it=self.new_item_type,
                            )
                        )
                        continue

                log.trace.info(
                    'Converting collection {vpath} to \'{it}\''.format(
                        vpath=collection.vpath,
                        it=self.new_item_type,
                    )
                )
                collection._item_type = new_item_type
                log.trace.info(repr(collection))

    def mutate_backward(self, model_manager):
        matched_items = model_manager.find_modelitems(self.item_type_id)
        for item in matched_items:
            if self.collection_name in item.children:
                collection = getattr(item, self.collection_name)

                new_item_type = model_manager.item_types[self.new_item_type]
                old_item_type = model_manager.item_types[self.old_item_type]
                if len(collection) > 0:
                    # We can only allow changing  the collection type to a
                    # supertype, eg. disk -> disk-base
                    if not new_item_type in \
                            model_manager._all_supertypes(old_item_type):
                        log.trace.info('Cannot convert collection {vpath} ' \
                            'from \'{new_it}\' to non-subtype ' \
                            '\'{old_it}\''.format(
                                vpath=collection.vpath,
                                old_it=self.old_item_type,
                                new_it=self.new_item_type,
                            )
                        )
                        continue

                log.trace.info(
                    'Converting collection {vpath} to \'{it}\''.format(
                        vpath=collection.vpath,
                        it=self.old_item_type,
                    )
                )
                collection._item_type = old_item_type
