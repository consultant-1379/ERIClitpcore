from lxml.etree import tostring, Element, SubElement, Comment

from litp.core.model_item import CollectionItem
from litp.core.model_item import RefCollectionItem
from litp.core.model_type import Collection, RefCollection
from litp.core.model_type import Property
from litp.core.litp_logging import LitpLogger
from litp.core.schemawriter import FieldSorter
from litp.enable_metrics import apply_metrics


LITP_NS_URL = "http://www.ericsson.com/litp"
NS = "{" + LITP_NS_URL + "}"
LITP_SCHEMA_LOC = "http://www.ericsson.com/litp litp-xml-schema/litp.xsd"
LITP_VERSION = "LITP2"
XSI_LOC = "http://www.w3.org/2001/XMLSchema-instance"

log = LitpLogger()

nsmap = {
    'litp': LITP_NS_URL,
    'xsi': XSI_LOC
}


def _polish(tagname):
    tagname = tagname.split("}")[-1]
    return tagname


class XmlExporter(object):

    def __init__(self, model_manager):
        self.model_manager = model_manager
        self._sorter = FieldSorter()
        apply_metrics(self)

    def _find_type(self, item):
        for item_type in self._walk_hierarchy(item.parent):
            if item.item_id in item_type.structure:
                return item_type.item_type_id
        raise Exception("Cannot find item type for %s" % (item,))

    def _build_collection_element(self, item, parent_element=None,
                                  source_item=None):
        if source_item:
            item_type = ("%s-%s-collection-inherit" % (self._find_type(item),
                                            item.item_id))
        else:
            item_type = ("%s-%s-collection" % (self._find_type(item),
                                            item.item_id))

        element = Element(NS + item_type, nsmap=nsmap)
        if parent_element is None:
            element.set("{" + XSI_LOC + "}" + "schemaLocation",
                        LITP_SCHEMA_LOC)

        if source_item:
            element.set("source_path", source_item.vpath)

        element.set("id", item.item_id)

        return element

    def _build_root_element(self, item):
        element_name = item.item_type_id
        if item.item_type_id == "root":
            element_name = item.item_type_id
        elif item.source_vpath:
            element_name += "-inherit"
        elif isinstance(item, (Collection, RefCollection)):
            element_name = "%s-%s-collection" % (
                self._find_type(item), item.item_id)
        element = Element(
            NS + element_name, nsmap=nsmap)
        element.set("{" + XSI_LOC + "}" + "schemaLocation",
                    LITP_SCHEMA_LOC)
        if item.item_type_id == 'root':
            element.set("id", "root")
        elif len(item.item_id) > 0:
            element.set("id", item.item_id)

        if item.source_vpath:
            element.set("source_path", item.source_vpath)

        return element

    def _build_element(self, item, parent_element):
        element = None
        _namespace = NS

        if item.source_vpath:
            element = SubElement(
                parent_element, _namespace + item.item_type_id + "-inherit")
            element.set("source_path", item.source_vpath)
        else:
            element = SubElement(parent_element,
                _namespace + item.item_type_id)

        if len(item.item_id) > 0:
            element.set("id", item.item_id)
        return element

    def _walk_hierarchy(self, item):
        supertypes = self.model_manager._all_supertypes(item.item_type)
        supertypes.insert(0, item.item_type)
        supertypes.reverse()
        return supertypes

    def _properties_for_type(self, item_type):
        props = item_type.get_properties()
        for parent in self.model_manager._all_supertypes(item_type):
            props = [p for p in props if p not in
                     parent.get_properties()]
        return props

    def _filter_properties(self, item, props):
        return [key for key in props if
            item.properties.get(key) and
            not callable(item.properties[key])]

    def _build_xml(self, item, parent_element=None):
        if isinstance(item, CollectionItem) or \
                isinstance(item, RefCollectionItem):
            source_item = self.model_manager.get_item(item.source_vpath) \
                    if item.source_vpath else None
            return self._build_collection_xml(
                item, parent_element,
                source_item)
        elif parent_element is not None:
            element = self._build_element(item, parent_element)
        else:
            element = self._build_root_element(item)

        processed_children = []
        for item_type in self._walk_hierarchy(item):
            immediate_props = self._properties_for_type(item_type)
            buildable_props = self._filter_properties(item, immediate_props)
            for details in self._sorter.get_fields_with_details(item_type):
                if isinstance(details.field, Property):
                    if details.name not in buildable_props:
                        continue
                    sub_element = SubElement(element, details.name)
                    type_structure = item.item_type.structure[details.name]
                    if not type_structure.updatable_rest:
                        sub_element.append(
                            Comment("note: this property is not updatable"))
                    sub_element.text = str(item.properties[details.name])
                else:
                    if details.name not in item.children:
                        continue
                    child = item.children[details.name]
                    if details.name not in processed_children and \
                        child.item_type_id not in ["snapshot-base",
                                                   "upgrade",
                                                   "litp-service-base"]:
                        element.append(self._build_xml(child,
                            parent_element=element))
                processed_children.append(details.name)
        return element

    def _build_collection_xml(self, item, parent_element, source_item=None):
        element = self._build_collection_element(
            item, parent_element, source_item)

        for item_id in sorted(item.children):
            child = item.children[item_id]
            element.append(self._build_xml(child,
                parent_element=element))
        return element

    def get_as_xml(self, vpath):
        item = self.model_manager.get_item(vpath)
        if not item:
            return None
        root = self._build_xml(item)
        return tostring(root, pretty_print=True,
                        xml_declaration=True, encoding="utf-8")
