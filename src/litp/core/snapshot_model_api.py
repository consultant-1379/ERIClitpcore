from litp.core.model_manager import QueryItem
from litp.core.litp_logging import LitpLogger


log = LitpLogger()


class SnapshotModelApi(object):
    """
    Provides plugins with a read-only, queryable view of the deployment model
    as it was when a snapshot was created.
    """

    def __init__(self, model_manager):
        self._model_manager = model_manager

    def query_by_vpath(self, vpath):
        """
        Return a :class:`litp.core.model_manager.QueryItem` object that matches
        the specified vpath.

        If no :class:`litp.core.model_manager.QueryItem` is found, then None is
        returned.

        **Example Usage:**

            The following code will return a QueryItem if the vpath exists:

            .. code-block:: python

                item = self.api.query_by_vpath("/foo")

            Assuming the below vpath does not exist, None will be returned:

            .. code-block:: python

                no_item = self.api.query_by_vpath("is/not/there")

        :param vpath: :class:`litp.core.model_manager.ModelItem` vpath.
        :type  vpath: str

        :returns: :class:`litp.core.model_manager.QueryItem` found \
                based on the specified criteria.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None

        """
        try:
            model_item = self._model_manager.query_by_vpath(vpath)
            query_item = QueryItem(self._model_manager, model_item)
            return query_item
        except Exception:  # pylint: disable=W0703
            return None

    def query(self, item_type_id, **properties):
        """
        Return a list of :class:`litp.core.model_manager.QueryItem` objects
        that match specified criteria.

        Using a :class:`litp.core.model_manager.QueryItem` the plugin
        developer can update a :class:`litp.core.model_type.Property`
        of an item in the model if the property was defined with
        updatable_plugin=True argument.

        **Example Usage:**

            Given that the following item type is defined:

            .. code-block:: python

                ItemType("foobar",
                    name=Property("basic_string"),
                    time=Property("basic_string", updatable_plugin=True))

            The following code is valid:

            .. code-block:: python

                for item in api.query("foobar"):
                    item.time = "sometime"
                    # this would raise AttributeError:
                    # item.name = "some new name"

        :param item_type_id: Item type id of item to search for.
        :type  item_type_id: str
        :param   properties: Properties of the item to use as search criteria.
        :type    properties: dict

        :returns: list of :class:`litp.core.model_manager.QueryItem` found \
                based on the specified criteria.
        :rtype:   list
        """
        model_items = self._model_manager.query(item_type_id, **properties)
        query_items = []
        for model_item in model_items:
            query_item = QueryItem(self._model_manager, model_item)
            query_items.append(query_item)
        return query_items
