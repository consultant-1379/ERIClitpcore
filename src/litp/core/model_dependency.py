from collections import defaultdict

from litp.core.model_type import Collection
from litp.core.model_type import RefCollection


class ModelDependencyHelper(object):
    def __init__(self, model_manager):
        self.model_manager = model_manager
        self._direct_extended_by = None
        self._direct_extends = None
        self._indirect_type_extensions = {}

    @property
    def item_types(self):
        return self.model_manager.item_types

    def reset(self):
        '''
        Clears the cached representation of item type extension relationships.
        '''
        self._direct_extended_by = None
        self._direct_extends = None
        self._indirect_type_extensions.clear()

    def _populate_direct_item_type_extensions(self):
        '''
        Populate a dictionary of direct extension relationships between item
        types.
        '''

        direct_type_extensions = defaultdict(set)
        reverse_direct_type_extensions = defaultdict(str)
        for item_type_id, item_type in self.item_types.iteritems():
            if item_type.extend_item:
                # Key is EXTENDED BY value
                direct_type_extensions[item_type.extend_item].add(item_type_id)
                # Key EXTENDS value
                reverse_direct_type_extensions[item_type_id] = \
                        item_type.extend_item
        self._direct_extended_by = direct_type_extensions
        self._direct_extends = reverse_direct_type_extensions

    def get_extending_types(self, item_type):
        '''
        Takes a litp.core.model_type.ItemType` instance and recursively
        builds a list of the IDs of all item types that directly or indirectly
        extend it.

        The ID of ``item_type`` isn't part of this method's output.

        :param item_type: An item type
        :type item_type: :class:`~litp.core.model_type.ItemType`

        :rtype: list
        '''

        if self._direct_extended_by is None:
            self._populate_direct_item_type_extensions()

        cached_extending_types = self._indirect_type_extensions.get(
            item_type.item_type_id
        )
        if cached_extending_types:
            return cached_extending_types

        extending_types = []
        # We're initially iterating over direct extension relationships
        for extending_type_id in self._direct_extended_by[
                    item_type.item_type_id
                ]:
            extending_types.append(extending_type_id)

            extending_type = self.item_types[extending_type_id]
            extending_types.extend(self.get_extending_types(extending_type))

        self._indirect_type_extensions[item_type.item_type_id] = \
                extending_types
        return extending_types

    def _get_extended_types(self, item_type):
        '''
        Takes a litp.core.model_type.ItemType` instance and recursively
        builds a list of the IDs of all item types that it directly or
        indirectly extends.

        The ID of ``item_type`` isn't part of this method's output.

        :param item_type: An item type
        :type item_type: :class:`~litp.core.model_type.ItemType`

        :rtype: list
        '''

        if self._direct_extends is None:
            self._populate_direct_item_type_extensions()

        extended_types = []
        extended_type_id = self._direct_extends[item_type.item_type_id]
        if extended_type_id:
            extended_types.append(extended_type_id)
            extended_type = self.item_types[extended_type_id]
            extended_types.extend(self._get_extended_types(extended_type))

        return extended_types

    def _get_all_required_siblings(self, item_type, structure_element):
        '''
        Takes a :class:`~litp.core.model_type.ItemType` instance and a
        structural element within that type (eg. a
        :class:`~litp.core.model_type.Child` or
        :class:`~litp.core.model_type.RefCollection`) and recursively builds a
        list of the structural names of all siblings in ``item_type`` that
        directly or indirectly require ``structure_element``.

        The structural name of ``structure_element`` in ``item_type`` isn't
        part of this method's output.

        :param item_type: The item type within which ``structure_element`` is
            defined.
        :type item_type: :class:`~litp.core.model_type.ItemType`

        :param structure_element: An element in ``item_type``'s structure.
        :type structure_element: For instance,
            :class:`~litp.core.model_type.Reference` or
            :class:`~litp.core.model_type.Collection`

        :return: A list of the structural names of all elements in
            ``item_type``'s structure that directly or indirectly require
            ``structure_element``.
        :rtype: list
        '''

        required_siblings = []

        for required_sibling_id in structure_element._require.split(","):
            required_siblings.append(required_sibling_id)

            sibling_instance = item_type.structure[required_sibling_id]
            if sibling_instance._require:
                required_siblings.extend(
                    self._get_all_required_siblings(
                        item_type, sibling_instance
                    )
                )
        return required_siblings

    def _get_recursive_dependencies(
                self,
                current_ancestor_type,
                current_ancestor_vpath,
                target_item_ancestors
            ):
        '''
        Recursively builds a set comprising the vpaths of all model items
        required by a certain item (the target item) or any of its ancestors.

        Takes arguments that describe an ancestor of the target item, builds a
        set comprising the vpaths of all items directly or indirectly required
        by that ancestor and adds to that set the output of the method called
        on the next ancestor.

        :param current_ancestor_type: The item type the ancestor item at
            ``current_ancestor_vpath`` is to be **parsed as**
        :type current_ancestor_type: :class:`~litp.core.model_type.ItemType`

        :param current_ancestor_vpath: The vpath of the item in the target
            item's ancestry up to which we've already gathered required items
        :type current_ancestor_vpath: str

        :param target_item_ancestors: A list comprising all vpath tokens of a
            given :class:`~litp.core.model_item.ModelItem` that are below
            the item at ``current_ancestor_vpath``
        :type target_item_ancestors: list

        :return: A set comprising the vpaths of the items required by the item
            at ``current_ancestor_vpath`` and all of its ancestors.
        :rtype: set
        '''

        target_item_remaining_ancestors = list(
            target_item_ancestors
        )
        next_ancestor_id = target_item_remaining_ancestors.pop(0)

        next_ancestor_required_vpaths = set()

        # This condition may be met when we collect the dependencies defined
        # by an item type other than the explicit type of the current ancestor
        # (eg. a type that the current ancestor's type extends)
        if next_ancestor_id not in current_ancestor_type.structure:
            return next_ancestor_required_vpaths

        next_ancestor_item = current_ancestor_type.structure[next_ancestor_id]
        if next_ancestor_item._require:
            required_siblings = self._get_all_required_siblings(
                current_ancestor_type, next_ancestor_item
            )
            for sibling_id in required_siblings:
                next_ancestor_required_vpaths.add(
                    "/".join([current_ancestor_vpath, sibling_id])
                )

        next_ancestor_vpath = "/".join([
            current_ancestor_vpath, next_ancestor_id
        ])

        # Collection and RefCollection instances don't have a structure, so we
        # skip them.
        if target_item_remaining_ancestors and \
                isinstance(next_ancestor_item, (Collection, RefCollection)):
            next_ancestor_id = target_item_remaining_ancestors.pop(0)
            next_ancestor_vpath = "/".join([
                next_ancestor_vpath, next_ancestor_id
            ])

        type_of_next_ancestor_item = self.model_manager.query_by_vpath(
            next_ancestor_vpath
        )._item_type

        if target_item_remaining_ancestors:
            # Recursion. We'll look at the items that are below
            # next_ancestor_item
            next_ancestor_required_vpaths.update(
                self._get_recursive_dependencies_all_extended_types(
                    type_of_next_ancestor_item,
                    next_ancestor_vpath,
                    target_item_remaining_ancestors
                )
            )

        return next_ancestor_required_vpaths

    def _get_recursive_dependencies_all_extended_types(
                self,
                current_ancestor_type,
                current_ancestor_vpath,
                target_item_ancestors
            ):
        '''
        This is a proxy for _get_recursive_dependencies that calls it for
        ``item_type`` and every item type it extends and returns the union
        of all the results.

        :param current_ancestor_type: The item type the item at
            ``current_ancestor_vpath`` is **defined as**
        :type current_ancestor_type: :class:`~litp.core.model_type.ItemType`

        :param current_ancestor_vpath: The vpath of the item in the target
            item's ancestry up to which we've already gathered required items
        :type current_ancestor_vpath: str

        :param target_item_ancestors: A list comprising all vpath tokens of the
            target item that are below the item at ``current_ancestor_vpath``
        :type target_item_ancestors: list

        :return: A set comprising the vpaths of the items required by the item
            at ``current_ancestor_vpath`` and all of its ancestors.
        :rtype: set
        '''
        deps = set()

        # A list comprising the ID of ``item_type`` and every item type that
        # it extends.
        possible_item_type_ids = [current_ancestor_type.item_type_id]
        possible_item_type_ids.extend(
            self._get_extended_types(current_ancestor_type)
        )

        for possible_item_type_id in possible_item_type_ids:
            deps.update(
                self._get_recursive_dependencies(
                    self.item_types[possible_item_type_id],
                    current_ancestor_vpath,
                    target_item_ancestors
                )
            )

        return deps

    def _get_all_required_items(self, vpath):
        '''
        Builds and returns a set comprising the vpaths of all the items
        directly or indirectly required by the item whose vpath is passed as
        argument or any of its ancestors.

        :param vpath: The vpath of a :class:`~litp.core.model_item.ModelItem`
            in the model
        :type vpath: str

        :return: A set comprising the vpaths of all the items directly or
            indirectly required by the item at ``vpath``.
        :rtype: set
        '''

        if vpath == "/":
            return set()

        # A list of the item's direct ancestors. The first token is a
        # structural element of the root item type, the last token is the
        # item_id of the ModelItem whose vpath is passed as argument.
        path_tokens = vpath.split("/")
        path_tokens.pop(0)

        root_type_id = self.model_manager.get_item("/").item_type_id
        root_type = self.item_types[root_type_id]

        return self._get_recursive_dependencies(root_type, "", path_tokens)

    def get_filtered_deps(self, vpath, vpaths):
        '''
        Builds and returns a set comprising all the vpaths of all items
        required by the item at ``vpath`` that are part of the ``vpaths``
        iterable.

        :param vpath: The vpath of a :class:`~litp.core.model_item.ModelItem`
        :type vpath: str

        :param vpaths: An iterable sequence of vpaths
        :type vpaths: set
        '''

        item_deps = self._get_all_required_items(vpath)
        deps = set()
        for vpath in vpaths:
            for item_dependency in item_deps:
                if vpath.startswith(item_dependency):
                    deps.add(vpath)
                    break
        return deps
