##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.base_plugin_api import BasePluginApi
from litp.core.constants import UPGRADE_SNAPSHOT_NAME
from litp.core.exceptions import NoMatchingActionError, NoSnapshotItemError
from litp.core.snapshot_model_api import SnapshotModelApi
from litp.data.data_manager import DataManager
from litp.data.constants import SNAPSHOT_PLAN_MODEL_ID_PREFIX


class PluginApiContext(BasePluginApi):
    """
    Plugin API context provided to plugin's methods
    """
    def __init__(self, model_manager):
        self._cached_snapshot_model = None
        # This is set in execution_manager
        self.exclude_nodes = set()
        super(PluginApiContext, self).__init__(
                model_manager=model_manager)

    def _snapshot_object(self):
        """
        Helper for snapshot_name and snapshot_action. Returns the snapshot
        object that is being used in the current plan, or None if no snapshot
        is being created
        """
        snapshot_object = self.query('snapshot-base', active='true')
        if snapshot_object:
            if len(snapshot_object) == 1:
                return snapshot_object[0]
            raise Exception('Found more than one active snapshots.')
        return None

    def snapshot_name(self):
        """
        Returns a string containing the snapshot name of the current snapshot
        or empty string if no matching object is found

        :returns: string with id matching name
        :rtype: str
        """
        snap = self._snapshot_object()
        if snap:
            return snap.item_id
        return ''

    def is_snapshot_action_forced(self):
        """
        Returns whether the remove or restore snapshot action is forced
        with -f option

        :returns: boolean with the presence of the flag
        :rtype: bool
        """
        snap = self._snapshot_object()
        if snap:
            return snap.force == 'true'
        return False

    def snapshot_model(self):
        """
        Returns the :class:`litp.core.snapshot_model_api.SnapshotModelApi`
        for the current snapshot or None if no snapshot is present.

        :returns: the :class:`litp.core.snapshot_model_api.SnapshotModelApi` \
        for the current snapshot or None.

        :rtype: :class:`litp.core.snapshot_model_api.SnapshotModelApi` or None
        """
        if self.snapshot_action() not in ('restore', 'remove'):
            return None
        live_model_data_manager = self._model_manager.data_manager
        data_manager = DataManager(live_model_data_manager.session)
        model_manager = self._model_manager.copy()
        data_manager.configure(
            model_manager,
            SNAPSHOT_PLAN_MODEL_ID_PREFIX + self.snapshot_name()
        )
        model_manager.data_manager = data_manager
        return SnapshotModelApi(model_manager)

    def snapshot_action(self):
        """
        Returns action to execute in the snapshot plan. That can be:
        'create'
        'remove'
        'restore'
        Or raises an exception if no matching action was found

        :returns: action type
        :rtype: str
        """
        snapshot = self._snapshot_object()
        if snapshot:
            if snapshot.is_for_removal():
                return 'remove'
            elif snapshot.is_initial():
                return 'create'
            elif snapshot.is_applied() and snapshot.timestamp and\
                                     snapshot.item_id == UPGRADE_SNAPSHOT_NAME:
                # timestamp needs to be valid, see litpcds-8537
                # only upgrade snapshots can be restored
                return 'restore'
            raise NoMatchingActionError("Could not determine the action to do "
                            "for snapshot"
                            " \"{0}\". Removing that snapshot might solve "
                            "the problem.".format(snapshot.item_id))
        raise NoSnapshotItemError("Could not determine the action to do, "
                        "snapshot not found")

    def remove_item(self, vpath):
        """
        Method to allow a plugin to remove an item and it's children.
        """
        return self._model_manager.remove_item(vpath)
