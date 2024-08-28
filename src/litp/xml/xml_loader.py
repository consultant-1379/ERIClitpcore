import os
import re
from lxml import etree
from lxml.etree import DocumentInvalid
from litp.core.model_type import Property
from litp.core.model_item import CollectionItem
from litp.core.model_type import Collection
from litp.core.model_item import RefCollectionItem
from litp.core.model_type import RefCollection
from litp.core.validators import ValidationError
from litp.core.litp_logging import LitpLogger
from litp.core.etlogger import ETLogger, et_logged
from litp.core import constants
from litp.core.topsort import topsort
from litp.core.model_manager import ModelManagerException
from litp.enable_metrics import apply_metrics


log = LitpLogger()
etlog = ETLogger(log.trace.debug, "XmlLoader ET")

ALLOWED_ROOTS = [
    'infrastructure',
    'root-deployments-collection',
    'deployments',
    'software',
    'hardware',
    'ms',
]

NON_DELETABLE_PATHS = [
    "/software",
    "/infrastructure",
    "/infrastructure/storage",
    "/infrastructure/networking",
    "/ms",
    "/litp"
]


collection_re = re.compile(r"-collection(-inherit)?$")
inherit_re = re.compile(r"-inherit?$")


def _polish(tagname):
    if tagname is not etree.Comment:
        tagname = tagname.split("}")[-1]
    return tagname


def _getchildren(element):
    return [child for child in element.getchildren()
            if child.tag is not etree.Comment]


def _getfilteredchildren(element):
    children = _getchildren(element)
    children = [child for child in children if _polish(child.tag) in
                ALLOWED_ROOTS]
    return children


def _filter_allowed(keys):
    return [key for key in keys if key.split('/')[1] in ALLOWED_ROOTS]


def _filter_errs(errors):
    return [err for err in errors if
            err.error_type != constants.ITEM_EXISTS_ERROR]


class XmlLoader(object):
    def __init__(self, model_manager, schema_path):
        self.model_manager = model_manager
        self.errors = []
        self.loaded = []
        self.existing_removable_vpaths = []
        self.merge = False
        self.replace = False
        self._inherits = {}

        if schema_path:
            schema_doc = etree.parse(open(schema_path, "r"))
            self._schema = etree.XMLSchema(schema_doc)
        else:
            self._schema = None
        apply_metrics(self)

    @et_logged(etlog)
    def load(self, root_vpath, xml_data, merge=False, replace=False):
        log.audit.info("XML load")
        self._inherits = {}
        self.merge = merge
        if replace:
            self.merge = True
        self.replace = replace
        self.errors = []
        self.loaded = []
        self.existing_removable_vpaths = []

        root_vpath = root_vpath.rstrip('/') or '/'
        existing_item = self.model_manager.get_item(root_vpath)
        if not existing_item:
            return [ValidationError(
                item_path=root_vpath,
                error_message="Path not found",
                error_type=constants.INVALID_LOCATION_ERROR
            )]
        element = etree.XML(xml_data)
        self.errors.extend(self._validate_existing(root_vpath,
                                                   element))
        self.errors.extend(self._validate_path(element, root_vpath))
        try:
            self._validate_xsd_schema(element)
        except DocumentInvalid as invalid_exp:
            self.errors.append(
                ValidationError(
                    item_path=root_vpath,
                    error_message=str(invalid_exp),
                    error_type=constants.INVALID_XML_ERROR)
            )
            if hasattr(self._schema, '_clear_error_log'):
                self._schema._clear_error_log()

        self.errors.extend(self._validate_can_add(element, existing_item))
        id_errs = self._validate_has_ids(element) + \
            self._validate_has_source_paths(element, root_vpath)
        if id_errs:
            self.errors.extend(id_errs)
        if self.merge:
            existing_item = self._get_item_from_element(
                existing_item.get_vpath(), element)
            if not self.replace:
                self.errors.extend(self._validate_can_merge(
                    element, existing_item))

        try:
            self.errors.extend(self._load_model(root_vpath, element))
        except ModelManagerException as e:
            self.errors.append(
                ValidationError(
                    item_path=root_vpath,
                    error_message=str(e))
            )

        self.existing_removable_vpaths = _filter_allowed(
            set(self._removable_vpaths()))

        log.trace.debug("Loaded: %s", self.loaded)
        if self.replace:
            item_id = element.attrib['id'] if 'id' \
                in element.attrib else _polish(element.tag)
            item_id = item_id if item_id != 'root' else ''
            if not self.errors:
                remove_list = self._determine_removals(
                    os.path.join(root_vpath, item_id))
                # check for inherit errors for elements being removed now
                self.errors.extend(self._recheck_inherits(remove_list))
                if not self.errors:
                    self.errors.extend(self._remove_missing(remove_list))
        if not self.errors:
            log.audit.info("XML load successful")
        else:
            log.audit.info("XML load failed")
        self._inherits = {}
        return self.errors

    def _recheck_inherits(self, remove_list):
        errors = []
        for inherit_path, element in self._sorted_inherits():
            model_item = self.model_manager.get_item(inherit_path)
            if model_item and model_item.source and \
                    model_item.source.get_vpath() in remove_list:
                errors.append(ValidationError(
                item_path=inherit_path,
                error_type=constants.METHOD_NOT_ALLOWED_ERROR,
                error_message=(
                    "Can't inherit item that is marked for removal")))
        return errors

    def _removable_vpaths(self):
        vpaths = []
        for item in self.model_manager.query_model():
            if item.is_collection():
                continue
            if item.parent_vpath:
                vpaths.append(item.vpath)
        return vpaths

    def _validate_has_ids(self, element):
        errors = self._validate_id_exists(element)
        for child in _getchildren(element):
            errors.extend(self._validate_id_exists(child))
        return errors

    def _validate_has_source_paths(self, element, vpath):
        errors = self._validate_source_path_exists(element, vpath)
        for child in _getchildren(element):
            errors.extend(self._validate_has_source_paths(
                child, "%s/%s" % (
                    vpath, element.get('id',  _polish(element.tag)))
                )
            )
        return errors

    def _validate_source_path_exists(self, element, vpath):
        element_name = _polish(element.tag)
        if self._is_inherit_item_type(element):
            source_path = element.get('source_path')
            if source_path is None:
                return [ValidationError(
                    item_path=self._remove_root_from_vpath(vpath),
                    error_message="Missing source_path "
                    "in inherit element %s" % (element_name,))]
            inherit_item = self._fetch_inherit_item(vpath, element)
            if (inherit_item and
                inherit_item.item_type_id == _polish(element_name).split(
                    "-inherit")[0] and
                inherit_item.source_vpath != source_path):
                return [ValidationError(
                    item_path=self._remove_root_from_vpath(vpath) + "/" +
                        element.get('id'),
                    error_message='Cannot update source path "%s". %s "%s" '
                        'is already inherited from "%s"' % (
                         source_path,
                         inherit_item.item_type_id,
                         inherit_item.item_id,
                         inherit_item.source_vpath)
                )]
        return []

    def _fetch_inherit_item(self, vpath, element):
        vpath = self._remove_root_from_vpath(vpath)
        inherit_item = None
        try:
            inherit_item = self.model_manager.query_by_vpath(
                vpath + '/' + element.get('id'))
        except ModelManagerException:
            pass  # not found
        return inherit_item

    def _remove_root_from_vpath(self, vpath):
        return re.sub('^//root/', '/', vpath)

    def _validate_xsd_schema(self, element):
        if self._schema:
            log.audit.info("XML validate")
            self._schema.assertValid(element)
            log.audit.info("XML validate successful")
        else:
            log.audit.info("XML is not validated")

    def _validate_can_merge(self, element, existing_item):
        errs = []
        if not existing_item:
            return errs
        errs.extend(self._validate_same_type(element, existing_item))
        for child in _getchildren(element):
            if 'id' not in child.attrib:
                continue
            errs.extend(self._validate_can_merge(
                child, existing_item.children.get(child.attrib['id'], None)))
        return errs

    def _field_in(self, element, existing_item):
        found_field = False
        name = ""
        for name, value in existing_item.children.items():
            if existing_item.is_collection():
                if name == element.attrib['id']:
                    found_field = True
            elif _polish(element.tag) == name:
                found_field = True
        return found_field

    def _validate_unique_items(self, vpath, element):
        errors = []
        ids = []
        for child in element.getchildren():
            if child.attrib.get('id', None):
                if not child.attrib['id'] in ids:
                    ids.append(child.attrib['id'])
                else:
                    errors.append(ValidationError(
                        item_path=vpath,
                        error_message=_polish(child.tag) + " with id: " +
                        child.attrib['id'] + " is not unique under " +
                        _polish(element.tag),
                        error_type=constants.INVALID_XML_ERROR
                    ))
            errors.extend(self._validate_unique_items(vpath, child))
        return errors

    def _validate_can_add(self, element, existing_item):
        errs = self._validate_unique_items(existing_item.get_vpath(), element)
        if not self._is_item_type(element) and \
                not self._is_inherit_item_type(element) and \
                not self._is_collection(element):
            if not self._field_in(element, existing_item):
                errs.append(ValidationError(
                    item_path=existing_item.get_vpath(),
                    error_message=_polish(element.tag) +
                    " cannot be added to " + existing_item.get_vpath(),
                    error_type=constants.INVALID_CHILD_TYPE_ERROR
                ))
        elif self._is_collection(element):
            parent_type_id, item_id = self._extract_collection_details(element)
            parent_type = self.model_manager.item_types[parent_type_id]
            if item_id not in parent_type.structure:
                errs.append(ValidationError(
                    item_path=existing_item.get_vpath(),
                    error_message="Cannot add %s to %s" % (
                        item_id, parent_type),
                    error_type=constants.INVALID_CHILD_TYPE_ERROR
                ))
        return errs

    def _validate_path(self, element, vpath):
        if _polish(element.tag) == "root" and vpath != "/":
            return [ValidationError(
                item_path=vpath,
                error_message="root cannot be added to " + vpath,
                error_type=constants.INVALID_LOCATION_ERROR
            )]
        else:
            return []

    def _is_item_type(self, element):
        return _polish(element.tag) in self.model_manager.item_types

    def _is_inherit_item_type(self, element):
        stripped_element = _polish(element.tag).split("-inherit")[0]
        return _polish(element.tag).endswith("-inherit") \
            and stripped_element in self.model_manager.item_types

    def _remove_inherit_tags(self, element, item):
        tokens = _polish(element.tag).split("-")
        tokens.pop()
        return "-".join(tokens)

    def _element_equals_item(self, element, item):
        result = False
        if item:
            if item.is_collection():
                if self._is_collection(element):
                    return item.item_id == element.attrib['id']
                return False
            elif self._is_inherit_item_type(element):
                result = (item.item_type_id ==
                          self._remove_inherit_tags(element, item))
            else:
                result = (item.item_type_id == _polish(element.tag))
        return result

    def _validate_same_type(self, element, existing_item):
        errs = []
        if not existing_item:
            return errs

        if not self._element_equals_item(element, existing_item):
            _, element_type = self._extract_collection_details(element)

            if existing_item.is_collection() and self._is_collection(element):
                if existing_item.item_id != element.attrib['id']:
                    errs.extend([ValidationError(
                        error_message="Cannot merge from %s to %s" %
                        (existing_item.item_type_id, _polish(element.tag)),
                        error_type=constants.INVALID_XML_ERROR,
                        item_path=existing_item.get_vpath()
                    )])
            log.audit.info("comparing %s %s" %
                           (element_type, existing_item.item_type_id))
            if not self._check_item_extends(element, existing_item):
                errs.extend([ValidationError(
                    error_message="Cannot merge from %s to %s" %
                    (existing_item.item_type_id, _polish(element.tag)),
                    error_type=constants.INVALID_XML_ERROR,
                    item_path=existing_item.get_vpath()
                )])
        return errs

    def _check_item_exists(self, element, existing_item):
        if self._element_equals_item(element, existing_item) \
                or _polish(element.tag) == 'root':
            return [ValidationError(
                item_path=existing_item.get_vpath(),
                error_type=constants.ITEM_EXISTS_ERROR,
                error_message="Item %s already exists" %
                (existing_item.get_vpath(),))]
        return []

    def _get_hierarchy(self, item):
        hierarchy = []
        item_type = item.item_type
        while item_type is not None:
            hierarchy.insert(0, item_type.item_type_id)
            if item_type.extend_item is not None \
                    and not len(item_type.extend_item) < 1:
                item_type = \
                    self.model_manager.item_types[item_type.extend_item]
            else:
                item_type = None
        return hierarchy

    def _check_item_extends(self, element, existing_item):
        _, element_type = self._extract_collection_details(element)
        if existing_item.item_type_id == element_type:
            return True
        hierarchy = self._get_hierarchy(existing_item)
        if element_type in hierarchy and \
            hierarchy.index(element_type) >= \
                hierarchy.index(existing_item.item_type_id):
            return True
        return False

    def _validate_existing(self, root_vpath, element):
        element_name = _polish(element.tag)
        element_name = element_name if element_name != "root" else ""
        if not self.merge and \
                self.model_manager.get_item(root_vpath):
            if 'id' in element.attrib:
                element_id = element.attrib["id"] \
                    if element_name != "" else "/"
                item_path = os.path.join(root_vpath, element_id)
            else:
                item_path = os.path.join(root_vpath, element_name)
            existing = self.model_manager.get_item(item_path)
            if existing:
                return self._check_item_exists(element, existing)
        return []

    def _get_item_from_element(self, vpath, element):
        item = None
        if _polish(element.tag) == 'root':
            item = self.model_manager.get_item("/")
        else:
            item = self.model_manager.get_item(
                vpath + "/" + element.attrib['id'])
        if not item:
            if not vpath.endswith("/"):
                vpath = vpath + "/"
            if 'id' in element.attrib:
                path = vpath + element.attrib['id']
            else:
                path = vpath + _polish(element.tag)
            item = self.model_manager.get_item(path)
        return item

    def _is_collection(self, element):
        if re.search(collection_re, _polish(element.tag)):
            parent_type_id, item_id = self._extract_collection_details(element)
            if parent_type_id is not None:
                parent_type = self.model_manager.item_types[parent_type_id]
                actual_item_type = parent_type.structure[item_id]
                return isinstance(actual_item_type,
                                  (Collection, RefCollection))
        return False

    def _extract_collection_details(self, element):
        element_name = _polish(element.tag)
        sub_collection = re.sub(inherit_re, r'',
                                re.sub(collection_re, r'', element_name))
        if sub_collection in self.model_manager.item_types:
            return [None, sub_collection]
        vals = sub_collection.rsplit("-", 1)
        if len(vals) < 2:
            vals.insert(0, None)
        return vals

    def _is_item_collection(self, item):
        return isinstance(item, (CollectionItem, RefCollectionItem))

    def _validate_id_exists(self, element):
        element_name = _polish(element.tag)
        if 'id' not in element.attrib and \
                element_name in self.model_manager.item_types and \
                not self._is_a_property(element) and \
                element_name != "root":
            return [ValidationError(
                error_message="Missing id in element %s" % (element_name,))]
        return []

    def _is_a_property(self, element):
        element_name = _polish(element.tag)
        return element_name == element.tag

    def _read_all_properties(self, element, vpath):
        properties = {}
        for child in _getchildren(element):
            if 'source_path' not in child.attrib:
                properties[_polish(child.tag)] = child.text

        parent_path, item_id = self.model_manager.split_path(vpath)
        parent = self.model_manager.get_item(parent_path)
        if self.model_manager._get_reference_read_only(parent, item_id):
            return {}
        return properties

    def _read_properties(self, element, item_type):
        properties = {}
        for name, field in item_type.structure.items():
            if type(field) is Property:
                prop = self._get_child(element, name)
                if prop is not None:
                    properties[name] = prop.text
        return properties

    def _replace_properties(self, vpath, **properties):
        return self._checked(
            vpath, self.model_manager.replace_item(
                vpath, **properties))

    def _merge_properties(self, vpath, **properties):
        return self._checked(
            vpath, self.model_manager.merge_item(vpath, **properties))

    def _get_child(self, element, field_name):
        for child in _getchildren(element):
            if _polish(child.tag) == field_name:
                return child
        return None

    @et_logged(etlog)
    def _load_model(self, vpath, element):
        errs = []
        with self.model_manager.cached_model():
            etlog.begin("_load_descend")
            errs.extend(self._load_descend(vpath, element))
            etlog.done()
            etlog.begin("_load_inherits")
            errs.extend(self._load_inherits())
            etlog.done()
        return errs

    def _load_descend(self, vpath, element, errors=None):
        if errors is None:
            errors = []
        element_name = _polish(element.tag)
        if element_name == "root":
            for child in _getfilteredchildren(element):
                self._load_descend(vpath, child, errors)
        elif element_name in self.model_manager.item_types and \
                'id' in element.attrib:
            err = self._create_item_from_element(vpath, element)
            errors.extend(err)
            if not err:
                descend_vpath = os.path.join(vpath, element.attrib['id'])
                self._descend_children(descend_vpath, element, errors)
        elif self._is_collection(element):
            _, item_id = self._extract_collection_details(element)
            descend_vpath = os.path.join(vpath, item_id)
            self._descend_children(descend_vpath, element, errors)
        elif self._is_inherit_item_type(element):
            descend_vpath = os.path.join(vpath, element.attrib['id'])
            self._inherits[descend_vpath] = element
            self._descend_children(descend_vpath, element, errors)
        else:
            log.trace.debug("Ignoring: %s %s", vpath, element)
        return errors

    def _sorted_inherits(self):
        # quick fix for bad source_paths that get through XSD
        # this is caught and an exception is added to the list
        # however, as we need to pass-through and collect all
        # errors, we have to bail out here
        for vpath, element in self._inherits.items():
            if not element.attrib.get('source_path'):
                log.trace.warn("Inherit with no source path "
                               "ignoring: %s %s", vpath, element)
                return []

        graph = dict((vpath, set([element.attrib['source_path']]))
                     for vpath, element in self._inherits.items())
        sorted_inherits = []
        for vpath_list in topsort(graph):
            for vpath in vpath_list:
                if vpath in self._inherits:
                    sorted_inherits.append((vpath, self._inherits[vpath]))
        reordered_inherits = []
        for inherit in sorted_inherits:
            source_path = inherit[1].attrib['source_path']
            dependencies = []
            for i in sorted_inherits:
                destination_vpath = i[0]
                if source_path.startswith(destination_vpath):
                    dependencies.append(i)
            for d in dependencies:
                if d not in reordered_inherits:
                    reordered_inherits.append(d)
            if inherit not in reordered_inherits:
                reordered_inherits.append(inherit)
        return reordered_inherits

    def _load_inherits(self):
        errs = []
        for vpath, element in self._sorted_inherits():
            errs.extend(self._create_inherit_from_element(vpath, element))
        if errs:
            self._inherits = {}
        return errs

    def _descend_children(self, vpath, element, errors):
        for child in _getchildren(element):
            self._load_descend(vpath, child, errors)

    def _clean_properties(self, props_in):
        properties = {}
        for p, v in props_in.iteritems():
            if v is not None:
                properties.update({p: v})
        return properties

    def _cascade_delete_path(self, vpath):
        item = self.model_manager.get_item(vpath)
        if item:
            to_delete = [item]
            to_delete.extend(self.model_manager.query_descends(item))
            to_delete.sort(key=lambda item: item.parent_vpath, reverse=True)
            for item in to_delete:
                self.model_manager._delete_removed_item(
                    item, validate_inherit=False)

    def _create_item_from_element(self, vpath, element):
        item_type_id = _polish(element.tag)
        item_id = element.attrib['id']

        properties = self._clean_properties(self._read_properties(
            element, self.model_manager.item_types[item_type_id]))

        new_vpath = os.path.join(vpath, item_id)

        errors = set()

        existing_item = self.model_manager.get_item(new_vpath)
        if existing_item:
            log.trace.debug("Update item: %s", new_vpath)
            if existing_item.item_type_id == item_type_id:
                if self.replace:
                    errors.update(self._replace_properties(
                        new_vpath, **properties))
                else:
                    errors.update(self._merge_properties(
                        new_vpath, **properties))
            elif new_vpath not in NON_DELETABLE_PATHS:
                self._cascade_delete_path(new_vpath)
                errors.update(self._checked(
                    new_vpath, self.model_manager.create_item(
                        item_type_id, new_vpath, **properties)))
            return list(errors)
        else:
            log.trace.debug("Create item: %s", new_vpath)
            return self._checked(new_vpath, self.model_manager.create_item(
                item_type_id, new_vpath, **properties))

    def _create_inherit_from_element(self, vpath, element):
        source_path = element.attrib['source_path']
        if vpath == source_path:
            return [ValidationError(
                item_path=vpath,
                error_message=("The target item %s (id %s) "
                               "and its source path %s are the same item")
                % (_polish(element.tag), element.attrib['id'], source_path))]

        source = self.model_manager.get_item(source_path)
        _, element_type = self._extract_collection_details(element)
        if source and (source.item_type_id != element_type):
            return [ValidationError(
                item_path=vpath,
                error_message=('An inherited item is not allowed to reference'
                    ' a source item of type "%s" using item type "%s"')
                    % (source.item_type_id, element_type),
                    error_type=constants.INVALID_XML_ERROR)]

        properties = self._read_all_properties(element, vpath)
        if self.model_manager.has_item(vpath):
            log.trace.debug("Update inherit: %s", vpath)
            if self.merge:
                if self.replace:
                    return self._replace_properties(vpath, **properties)
                else:
                    return self._merge_properties(vpath, **properties)
            else:
                return self._checked(
                    vpath, self.model_manager.update_item(vpath, **properties))
        else:
            log.trace.debug("Create inherit: %s", vpath)
            return self._checked(vpath, self.model_manager.create_inherited(
                source_path, vpath, **properties))

    def _checked(self, new_vpath, response):
        if type(response) is list:
            log.trace.debug("Errors: %s", response)
            errors = _filter_errs(response)
            for err in errors:
                if hasattr(err, 'item_path') and err.item_path is None:
                    err.item_path = new_vpath
            return errors
        else:
            self.loaded.append(new_vpath)
            return []

    def _determine_removals(self, vpath):
        existing_branch = set(
            [epath for epath in
                self.existing_removable_vpaths if epath.startswith(vpath)])
        to_remove = existing_branch.difference(self.loaded)
        to_remove = sorted(to_remove)
        to_remove.reverse()
        return to_remove

    def _remove_missing(self, remove_vpath_list):
        errors = []
        for remove_vpath in remove_vpath_list:
            # Item may not exist if it was a reference to already removed item.
            item = self.model_manager.get_item(remove_vpath)
            if item and item.item_type_id not in ['upgrade']:
                errors.extend(self._checked(
                    remove_vpath,
                    self.model_manager.remove_item(item.get_vpath())))
        return errors
