##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import os
import ConfigParser
import StringIO

from collections import namedtuple

from lxml.etree import ElementTree, Element, SubElement, Comment

from litp.core.extension import ModelExtension
from litp.core.plugin import Plugin
from litp.core.model_type import PropertyType, ItemType, \
    Property, View, _BaseStructure, Collection, Child, Reference, \
    RefCollection
from litp.core.litp_logging import LitpLogger
from litp.core.exceptions import SchemaWriterException, FieldSorterException

NS_PREFIX = "xs"
NS_URL = "http://www.w3.org/2001/XMLSchema"
NS = "{" + NS_URL + "}"

LITP_NS_URL = "http://www.ericsson.com/litp"

BASEITEM_ID = "baseitem"
BASECOLLECTION_ID = "basecollection"
BASE_XSD = "litp-base.xsd"
MAIN_XSD = "litp.xsd"

SITE_SPECIFIC_REGEX = r"%%[a-zA-Z0-9\-\._]+%%"

log = LitpLogger()


class SchemaWriter(object):
    """
    SchemaWriter scans directories for Model Extension and Plugin
    configuration files and uses them to generate XSD Schema files
    """

    def __init__(self, xsd_basepath, plugins_basepaths):
        """
        :param xsd_basepath: Path where the xsd files will be written
        :type  item_path: str
        :param plugins_basepaths: A list of paths where plugin information \
                                  is stored
        :type  item_path: list of strings
        """
        self.debug = False

        self._xsd_basepath = xsd_basepath
        self._plugins_basepaths = plugins_basepaths

        self._baseitem_path = os.path.join(xsd_basepath, BASE_XSD)

        self._ext_names = set()
        self._ext_class_names = set()

        self._ext_instances = {}  # extension class -> extension object
        self._ext_paths = {}  # extension class -> XSD path
        self._ext_basepaths = {}  # extension class -> directory path
        self._ext_types = {}  # extension class -> [type objects]

        self._type_paths = {}  # type_id -> XSD path
        self._type_ext_classes = {}  # type_id -> extension class
        self._type_instances = {}  # type_id -> type object
        self._type_parents = {}  # type_id -> type_id

        self._types_extended = set()

        self._type_instances[BASEITEM_ID] = ItemType(BASEITEM_ID, None)

        self._sorter = FieldSorter(_type_instances=self._type_instances)

    def write(self):
        """
        Queries the model and writes the schema to xsd_basepath
        """
        self._discover_model_extensions(self._plugins_basepaths)
        self._generate_schemas()

    def _read_config_file(self, config, path):
        config.read(path)

    def _parse_config_file(self, path):
        log.trace.debug("parsing file: %s", path)
        config = ConfigParser.SafeConfigParser()
        self._read_config_file(config, path)

        try:
            if config.has_section("plugin"):
                name = config.get("plugin", "name")
                class_name = config.get("plugin", "class")

            elif config.has_section("extension"):
                name = config.get("extension", "name")
                class_name = config.get("extension", "class")

            else:
                name, class_name = (None, None)
        except ConfigParser.NoOptionError:
            name, class_name = (None, None)

        if name is None or class_name is None:
            raise SchemaWriterException("invalid configuration: " + path)

        return (name, class_name)

    def _get_extension_class(self, pkg, name):
        log.trace.debug("importing: %s", pkg)
        module = __import__(pkg, globals(), locals(), [name], -1)
        log.trace.debug("getting attribute: %s", name)
        return getattr(module, name)

    def _process_config_dir(self, path):
        """
        Looks inside a given path, and imports modules referenced in the
        config files, and queries them about their structure.

        :param path: a path to check for configuration files
        :type  path: str
        """
        ext_name, class_name = self._parse_config_file(path)

        if class_name in self._ext_class_names:
            raise SchemaWriterException(
                "class already imported: " + class_name)

        pkg, name = class_name.rsplit(".", 1)

        try:
            clazz = self._get_extension_class(pkg, name)
        except (ImportError, AttributeError):
            log.trace.warning(
                "ignoring plugin or extension: can't import %s.%s", pkg, name)
            return

        ext = clazz()

        self._ext_names.add(name)
        self._ext_class_names.add(class_name)

        self._ext_instances[clazz] = ext
        self._ext_paths[clazz] = os.path.join(
            self._xsd_basepath, ext_name + ".xsd")
        self._ext_basepaths[clazz] = os.path.join(self._xsd_basepath, ext_name)
        ext_types = self._get_types(ext)
        types = []

        # XXX Candidate for Phase 3 refactoring
        for t in ext_types:
            type_id = self._get_type_id(t)
            if type_id in self._type_ext_classes:
                log.trace.warning(
                    "ignoring type which has already been added: %s",
                    t)
                continue
            types.append(t)
            self._type_paths[type_id] = os.path.join(
                self._xsd_basepath, ext_name, type_id + ".xsd")
            self._type_ext_classes[type_id] = clazz
            self._type_instances[type_id] = t
            if isinstance(t, ItemType):
                parent_type_id = t.extend_item
                if parent_type_id:
                    if parent_type_id not in self._types_extended:
                        self._types_extended.add(parent_type_id)
                    self._type_parents[type_id] = parent_type_id
        self._ext_types[clazz] = types

    def _discover_model_extensions(self, basepaths):
        """
        Discovers model extensions from configurations in basepaths

        :param basepaths: A list of directories to search for configuration \
                          files
        :type  basepaths: list of strings
        """
        for basepath in basepaths:
            if not os.path.isdir(basepath):
                continue
            for file_name in os.listdir(basepath):
                if not file_name.endswith(".conf"):
                    continue
                file_path = os.path.join(basepath, file_name)
                self._process_config_dir(file_path)
        self._validate_discovered_items()

    def _validate_discovered_items(self):
        """
        Checks validity of ItemTypes and PropertyTypes referenced in the model
        """
        errors = False

        type_children = {}
        for type_id, t in self._type_instances.items():
            if type_id == BASEITEM_ID:
                continue
            if isinstance(t, ItemType):
                parent_type_id = t.extend_item
                if not parent_type_id:
                    parent_type_id = BASEITEM_ID
                if parent_type_id not in self._type_instances:
                    errors = True
                    log.trace.error(
                        "unknown parent type %s for %s", parent_type_id, t)
                if parent_type_id not in type_children:
                    type_children[parent_type_id] = set()
                type_children[parent_type_id].add(type_id)

                for field in t.structure.values():
                    if isinstance(field, View):
                        continue
                    field_type_id = self._sorter.get_field_type_id(field)
                    if field_type_id not in self._type_instances:
                        errors = True
                        log.trace.error("unknown field %s in %s", field, t)

        if errors:
            raise SchemaWriterException("error(s) during post processing, "
                                        "see log for details")

        # XXX Candidate for splitting in Phase 3
        for base_type_id, child_types in type_children.items():
            base_type = self._type_instances[base_type_id]
            for type_id in child_types:
                field_names = set(base_type.structure.keys())
                t = self._type_instances[type_id]
                for field_name in t.structure.keys():
                    if field_name in field_names:
                        errors = True
                        log.trace.error(
                            "%s in %s overwrites the field defined in %s",
                            field_name, t, base_type)
                    field_names.add(field_name)

        if errors:
            raise SchemaWriterException("error(s) during post processing, "
                                        "see log for details")

    def _generate_schemas(self):
        """
        Generates the xml schemas and writes them to the xsd_basepath
        """
        if not os.path.exists(self._xsd_basepath):
            os.mkdir(self._xsd_basepath)

        for clazz in self._ext_instances.keys():
            path = self._ext_basepaths[clazz]
            if not os.path.exists(path):
                os.mkdir(path)
            types = self._ext_types[clazz]
            for t in types:
                type_id = self._get_type_id(t)
                path = self._type_paths[type_id]
                with open(path, "w") as f:
                    self._write_type(f, t)
            path = self._ext_paths[clazz]
            with open(path, "w") as f:
                self._write_ext(f, self._ext_instances[clazz])

        with open(self._baseitem_path, "w") as f:
            self._write_base(f)

        path = os.path.join(self._xsd_basepath, MAIN_XSD)
        with open(path, "w") as f:
            self._write_main(f)

    def _get_schemas(self):
        """
        Generates the xml schemas and writes them to the xsd_basepath
        """
        schemas = {}
        for clazz in self._ext_instances.keys():
            path = self._ext_basepaths[clazz]
            types = self._ext_types[clazz]
            for t in types:
                type_id = self._get_type_id(t)
                path = self._type_paths[type_id]
                output = StringIO.StringIO()
                output.name = path
                self._write_type(output, t)
                schemas[path] = output.getvalue()
            path = self._ext_paths[clazz]
            output = StringIO.StringIO()
            output.name = path
            self._write_ext(output, self._ext_instances[clazz])
            schemas[path] = output.getvalue()

        output = StringIO.StringIO()
        output.name = self._baseitem_path
        self._write_base(output)
        schemas[self._baseitem_path] = output.getvalue()
        path = os.path.join(self._xsd_basepath, MAIN_XSD)
        output = StringIO.StringIO()
        output.name = path
        self._write_main(output)
        schemas[path] = output.getvalue()
        return schemas

    def _normalize_regex(self, _s):
        s = _s.lstrip("^")
        s = s.rstrip("$")
        log.trace.debug("regex normalized: \"%s\" >> \"%s\"", _s, s)
        return s

    def _get_types(self, ext):
        """
        :param ext: The extension to get the model types from
        :type  ext: ModelExtension or Plugin

        :returns: PropertyTypes and ItemTypes used by the Model ext
        :rtype: list of PropertyTypes and ItemTypes
        """
        if isinstance(ext, ModelExtension):
            property_types = ext.define_property_types()
            item_types = ext.define_item_types()
        elif isinstance(ext, Plugin):
            property_types = ext.register_property_types()
            item_types = ext.register_item_types()
        else:
            raise SchemaWriterException(
                "invalid parent class: " + str(ext.__class__))
        return property_types + item_types

    def _get_type_id(self, t):
        if isinstance(t, PropertyType):
            type_id = "_" + t.property_type_id
        elif isinstance(t, ItemType):
            type_id = t.item_type_id
        else:
            raise SchemaWriterException("invalid type: " + str(t.__class__))
        return type_id

    def _create_documentation_elements(self, model_type):
        if model_type.item_description:
            element = Element(NS + "annotation")
            doc_element = SubElement(element, NS + "documentation")
            doc_element.text = model_type.item_description
            if isinstance(model_type, RefCollection):
                doc_element.text = \
                    doc_element.text + \
                    (" **Deprecated: basecollection-inherit-type has been "
                     "deprecated. Please use basecollection-type instead.**")
            return [element]
        else:
            return []

    def _create_elements_property_type(self, t):
        elements = []
        element = Element(NS + "simpleType")
        elements.append(element)

        type_element_id = "-".join([self._get_type_id(t), "type"])
        element.set("name", type_element_id)

        element = SubElement(element, NS + "restriction")
        element.set("base", ":".join([NS_PREFIX, "string"]))

        element = SubElement(element, NS + "pattern")
        element.set("value", self._normalize_regex(t.regex))

        return elements

    def is_base_type(self, model_type):
        return self.base_type_id_for(model_type) == BASEITEM_ID

    def _create_elements_item_type(self, model_type):
        # XXX Candidate for Phase 3 refactoring
        elements = []

        elements.extend(self.create_include_elements(model_type))
        # type
        elements.append(self.create_model_type_element(model_type))
        # element
        elements.append(self.create_model_element(model_type))
        # inherit type
        elements.append(self.create_model_inherit_type_element(model_type))
        # inherit element
        elements.append(self.create_model_inherit_element(model_type))
        # Internal collection types
        elements.extend(self.create_internal_collection_types(model_type))

        return elements

    def create_inner_collection_type_element(self, model_type, element_name,
                                        field_type_id, field, inherit=False):
        model_type_element = Element(NS + "complexType")

        if inherit:
            collection_name = "%s-%s-collection-inherit-type" % \
                (model_type.item_type_id, element_name)
        else:
            collection_name = "%s-%s-collection-type" % \
                (model_type.item_type_id, element_name)

        model_type_element.set("name", collection_name)

        model_type_element.extend(self._create_documentation_elements(field))
        complexContentElement = SubElement(model_type_element,
                                           NS + "complexContent")

        extensionElement = SubElement(complexContentElement, NS + "extension")

        if isinstance(field, RefCollection):
            type_str = "-".join([BASECOLLECTION_ID, "inherit", "type"])
        else:
            type_str = "-".join([BASECOLLECTION_ID, "type"])

        extensionElement.set("base", type_str)
        sequenceElement = SubElement(extensionElement, NS + "sequence")
        if inherit or isinstance(field, RefCollection):
            field_type_id = "%s-inherit" % field_type_id
        else:
            field_type_id = "%s" % field_type_id

        innerElement = SubElement(sequenceElement, NS + "element")
        innerElement.set("ref", field_type_id)
        innerElement.set("minOccurs", str(field.min_count))

        if field.max_count is None or field.max_count < 0:
            max_occurs = "unbounded"
        else:
            max_occurs = str(field.max_count)
        innerElement.set("maxOccurs", max_occurs)

        self._add_attribute(extensionElement,
                            name="id",
                            required=True,
                            restriction_pattern=element_name)

        if inherit:
            self._add_attribute_source_path(extensionElement)

        return model_type_element

    def create_inner_collection_element(self, model_type, element_name,
                                        field_type_id, field, inherit=False):
        element = Element(NS + "element")

        if inherit:
            element.set("name", "%s-%s-collection-inherit" %
                        (model_type.item_type_id, element_name))
            element.set("type", "%s-%s-collection-inherit-type" %
                        (model_type.item_type_id, element_name))
        else:
            element.set("name", "%s-%s-collection" %
                        (model_type.item_type_id, element_name))
            element.set("type", "%s-%s-collection-type" %
                        (model_type.item_type_id, element_name))
        return element

    def create_internal_collection_types(self, model_type):
        collection_elements = []

        for details in self._sorter.get_fields_with_details(model_type):
            if isinstance(details.field, (Collection, RefCollection)):
                tasks = [(self.create_inner_collection_type_element, False),
                         (self.create_inner_collection_element, False),
                         (self.create_inner_collection_type_element, True),
                         (self.create_inner_collection_element, True)]
                args = (model_type, details.element_name,
                        details.type_id, details.field)
                for method, inherit in tasks:
                    collection_elements.append(method(*args, inherit=inherit))
        return collection_elements

    def create_model_inherit_element(self, model_type):
        element = Element(NS + "element")

        element.set("name", "-".join([model_type.item_type_id, "inherit"]))
        element.set("type", self.element_inherit_type_id(model_type))
        if self.base_type_id_for(model_type) != BASEITEM_ID:
            element.set("substitutionGroup", "-".join(
                [self.base_type_id_for(model_type), "inherit"]))
        return element

    def create_model_element(self, model_type):
        element = Element(NS + "element")

        element.set("name", model_type.item_type_id)
        element.set("type", self.element_type_id(model_type))
        if not self.is_base_type(model_type):
            element.set("substitutionGroup", self.base_type_id_for(model_type))
        return element

    def create_model_inherit_type_element(self, model_type):
        inherit_element = Element(NS + "complexType")

        inherit_element.set("name", self.element_inherit_type_id(model_type))
        inherit_element.extend(self._create_documentation_elements(model_type))

        sub_element = SubElement(inherit_element, NS + "complexContent")
        sub_element = SubElement(sub_element, NS + "extension")
        sub_element.set("base", "-".join(
            [self.base_type_id_for(model_type), "inherit", "type"]))
        sub_element = SubElement(sub_element, NS + "sequence")

        for details in self._sorter.get_fields_with_details(model_type):
            sub_element.extend(
                self._create_elements_field(
                    model_type, details.element_name,
                    details.type_id, details.field,
                    is_inherit_type=True))
        return inherit_element

    def element_inherit_type_id(self, model_type):
        return "-".join([model_type.item_type_id, "inherit", "type"])

    def create_model_type_element(self, model_type):
        model_type_element = Element(NS + "complexType")

        model_type_element.set("name", self.element_type_id(model_type))

        model_type_element.extend(self._create_documentation_elements(
            model_type))

        complex_element = SubElement(model_type_element, NS + "complexContent")

        extension_element = SubElement(complex_element, NS + "extension")
        extension_element.set("base", "-".join(
            [self.base_type_id_for(model_type), "type"]))

        seq_element = SubElement(extension_element, NS + "sequence")

        for details in self._sorter.get_fields_with_details(model_type):
            seq_element.extend(
                self._create_elements_field(
                    model_type, details.element_name,
                    details.type_id, details.field))

        return model_type_element

    def element_type_id(self, model_type):
        return "-".join([model_type.item_type_id, "type"])

    def base_type_id_for(self, model_type):
        base_type_id = self._type_parents.get(model_type.item_type_id)
        if not base_type_id:
            base_type_id = BASEITEM_ID
        return base_type_id

    def create_include_elements(self, model_type):
        base_type_id = self.base_type_id_for(model_type)
        included_types = self.all_types_for_model_item(model_type,
                                                       base_type_id)
        included_xsds_list = self.all_included_paths_for_model_item(
            included_types, model_type)
        include_elements = []
        for included_path in included_xsds_list:
            element = Element(NS + "include")
            include_elements.append(element)
            element.set("schemaLocation", os.path.relpath(
                included_path,
                os.path.dirname(self._type_paths[model_type.item_type_id])))
        return include_elements

    def all_included_paths_for_model_item(self, included_types, t):
        included_xsds_list = set()
        base_ids = set([BASEITEM_ID, BASECOLLECTION_ID])
        for included_type_id in included_types:
            if included_type_id in base_ids:
                included_type_path = self._baseitem_path
            else:
                if included_type_id == t.item_type_id:
                    continue
                included_type_path = self._type_paths[included_type_id]
            included_xsds_list.add(included_type_path)

        included_xsds_list = list(included_xsds_list)
        included_xsds_list.sort()
        return included_xsds_list

    def all_types_for_model_item(self, t, base_type_id):
        included_types = set([base_type_id])
        for details in self._sorter.get_fields_with_details(t):
            if isinstance(details.field, (Collection, RefCollection)):
                included_types.add(BASECOLLECTION_ID)
            included_types.add(details.type_id)
        return included_types

    def _create_elements_field(self, model_type, element_name,
                               field_type_id, field, is_inherit_type=False):

        # XXX Candidate for Phase 3 refactoring
        log.trace.debug(
            "creating element: %s from %s; inherit: %s",
            element_name, field, is_inherit_type)

        field_class = field.__class__

        if field_type_id not in self._type_ext_classes:
            raise SchemaWriterException(
                "unknown type for field: " + field_type_id)

        element = Element(NS + "element")
        if isinstance(field, Property):
            element.extend(self._create_documentation_elements(field))
        elif not isinstance(field, (Collection, RefCollection)) \
                and isinstance(field, _BaseStructure):
            element.extend(self._create_documentation_elements(field))

        if issubclass(field_class, Property):
            element.set("name", element_name)
            if field.site_specific:
                self._create_site_specific_field(field_type_id, field, element)
            else:
                element.set("type", "-".join([field_type_id, "type"]))
        elif field_class in set([Child]) and is_inherit_type:
            element.set("ref", "%s-inherit" % element_name)
        elif field_class in set([Child, Reference]):
            element.set("ref", element_name)
        elif self._is_collection_type(field) and is_inherit_type:
            element.set("ref", "%s-%s-collection-inherit" %
                        (model_type.item_type_id, element_name))
            if not field.min_count:
                element.set("minOccurs", "0")
        elif self._is_collection_type(field):
            element.set("ref", "%s-%s-collection" % (model_type.item_type_id,
                                                   element_name))
            if not field.min_count:
                element.set("minOccurs", "0")
        else:
            raise SchemaWriterException(
                "invalid class for field: " + str(field))

        if is_inherit_type:
            element.set("minOccurs", "0")
        if not self._is_collection_type(field) and not field.required:
            element.set("minOccurs", "0")
        if self._is_required_property(field):
            element.set("minOccurs", "0")
        if isinstance(field, Reference):
            element.set("minOccurs", "0")
        if isinstance(field, Property) and field.default:
            element.set("default", field.default)

        return [element]

    def _create_site_specific_field(self, field_type_id, field, element):
        simple_element = SubElement(element, NS + "simpleType")
        restriction_element = SubElement(simple_element, NS + "restriction")
        restriction_element.set("base", ":".join([NS_PREFIX, "string"]))
        property_type = self._type_instances[field_type_id]
        pattern_element = SubElement(restriction_element, NS + "pattern")
        pattern_element.set("value", self._normalize_regex(
            property_type.regex) + r"|(" + SITE_SPECIFIC_REGEX + ")")

    def _is_required_property(self, field):
        return isinstance(field, Property) and \
            field.required and \
            field.default

    def _is_collection_type(self, field):
        return isinstance(field, (Collection, RefCollection))

    def _write_base(self, f):
        # XXX Candidate for Phase 3 refactoring
        log.trace.debug("generating: %s", f.name)

        ElementTree(Comment(" " + BASEITEM_ID + " ")).write(
            f, encoding="utf-8", xml_declaration=True)
        f.write("\n")

        root = Element(NS + "schema", nsmap={NS_PREFIX: NS_URL})
        model_type = self._type_instances[BASEITEM_ID]

        # baseitem-type
        element = SubElement(root, NS + "complexType")
        element.set("name", "-".join([BASEITEM_ID, "type"]))

        subelement = SubElement(element, NS + "sequence")
        fields_with_details = self._sorter.get_fields_with_details(model_type)
        for details in fields_with_details:
            subelement.extend(
                self._create_elements_field(
                    model_type, details.element_name,
                    details.type_id, details.field))

        self._add_attribute(element,
                            name="id",
                            required=True,
                            restriction_pattern=r"[a-zA-Z0-9_\-]+")

        subelement = SubElement(element, NS + "attribute")
        subelement.set("name", "version")
        subelement.set("type", ":".join([NS_PREFIX, "string"]))
        subelement.set("use", "optional")

        # baseitem-inherit-type
        element = SubElement(root, NS + "complexType")
        element.set("name", "-".join([BASEITEM_ID, "inherit", "type"]))

        subelement = SubElement(element, NS + "sequence")
        for details in fields_with_details:
            if not isinstance(details.field, Property):
                continue
            subelement.extend(
                self._create_elements_field(
                    model_type, details.element_name,
                    details.type_id, details.field,
                    is_inherit_type=True))

        self._add_attribute(element,
                            name="id",
                            required=True,
                            restriction_pattern=r"[a-zA-Z0-9_\-]+")

        self._add_attribute_source_path(element)

        # basecollection-type
        element = SubElement(root, NS + "complexType")
        element.set("name", "-".join([BASECOLLECTION_ID, "type"]))

        # basecollection-inherit-type
        element = SubElement(root, NS + "complexType")
        element.set("name", "-".join([BASECOLLECTION_ID, "inherit", "type"]))

        ElementTree(root).write(f, pretty_print=True)

    def _add_attribute(self, element, name, required, restriction_pattern):
        subelement = SubElement(element, NS + "attribute")
        subelement.set("name", name)
        if required:
            subelement.set("use", "required")
        attr_subelement = SubElement(subelement, NS + "simpleType")
        attr_subelement = SubElement(attr_subelement, NS + "restriction")
        attr_subelement.set("base", ":".join([NS_PREFIX, "string"]))
        attr_subelement = SubElement(attr_subelement, NS + "pattern")
        attr_subelement.set("value", restriction_pattern)

    def _add_attribute_source_path(self, element):
        self._add_attribute(element,
                            name="source_path",
                            required=True,
                            restriction_pattern=r"[a-zA-Z0-9_\-/]+")

    def _write_type(self, f, t):
        #log.trace.debug("generating: %s", f.name)
        type_id = self._get_type_id(t)
        clazz = self._type_ext_classes[type_id]
        type_fullname = ".".join([clazz.__module__, clazz.__name__, type_id])

        ElementTree(Comment(" " + type_fullname + " ")).write(
            f, encoding="utf-8", xml_declaration=True)
        f.write("\n")

        root = Element(NS + "schema", nsmap={NS_PREFIX: NS_URL})

        elements = []

        if isinstance(t, PropertyType):
            elements.extend(self._create_elements_property_type(t))
        elif isinstance(t, ItemType):
            elements.extend(
                self._create_elements_item_type(t))
        else:
            raise SchemaWriterException(
                "invalid base class for " + str(t) + ": " + str(t.__class__))

        root.extend(elements)

        ElementTree(root).write(f, pretty_print=True)

    def _write_ext(self, f, ext):
        #log.trace.debug("generating: %s", f.name)

        clazz = ext.__class__
        class_fullname = ".".join([clazz.__module__, clazz.__name__])

        ElementTree(Comment(" " + class_fullname + " ")).write(
            f, encoding="utf-8", xml_declaration=True)
        f.write("\n")

        root = Element(NS + "schema", nsmap={NS_PREFIX: NS_URL})

        types = self._ext_types[clazz]

        for t in types:
            type_id = self._get_type_id(t)
            path = self._type_paths[type_id]
            element = SubElement(root, NS + "include")
            element.set("schemaLocation", os.path.relpath(
                path, os.path.dirname(f.name)))

        ElementTree(root).write(f, pretty_print=True)

    def _write_main(self, f):
        log.trace.debug("generating: %s", f.name)

        ElementTree(Comment("LITP")).write(
            f, encoding="utf-8", xml_declaration=True)
        f.write("\n")

        root = Element(NS + "schema", nsmap={NS_PREFIX: NS_URL})
        root.set("targetNamespace", LITP_NS_URL)

        element = SubElement(root, NS + "include")
        element.set("schemaLocation", os.path.relpath(
            self._baseitem_path, os.path.dirname(f.name)))

        for clazz in self._ext_instances.keys():
            ext_path = self._ext_paths[clazz]
            element = SubElement(root, NS + "include")
            element.set("schemaLocation", os.path.relpath(
                ext_path, os.path.dirname(f.name)))

        ElementTree(root).write(f, pretty_print=True)


FieldWithDetails = namedtuple('FieldWithDetails',
                              'element_name, type_id, field, name')


class FieldSorter(object):
    """
    Encapsulate the field sorting logic.

    At the moment used by both schemawriter and xml_exporter. Both consumers
    apply specific constraints on fields returned.
    """
    def __init__(self, _type_instances=None):
        """
        :param _type_instances: field of unknown type raises an exception
        """
        self._type_instances = _type_instances

    def _should_raise(self, field_type_id):
        if self._type_instances is None:
            return field_type_id is None
        else:
            return field_type_id not in self._type_instances

    def get_element_name(self, field_name, field_type_id, field):
        if isinstance(field, (Property, Collection, RefCollection)):
            element_name = field_name
        elif isinstance(field, Child):
            element_name = field_type_id
        elif isinstance(field, Reference):
            element_name = field_type_id + "-inherit"
        else:
            template = "invalid class for field: {0}"
            raise FieldSorterException(template.format(str(field)))
        return element_name

    def get_field_type_id(self, field):
        if isinstance(field, Property):
            field_type_id = "_" + field.prop_type_id
        elif isinstance(field, _BaseStructure):
            field_type_id = field.item_type_id
        else:
            template = "invalid class for field: {0}"
            raise FieldSorterException(template.format(str(field)))
        return field_type_id

    def get_fields_with_details(self, model_type):
        fields_with_details = []
        for field_name, field in model_type.structure.items():
            if isinstance(field, View):
                continue
            field_type_id = self.get_field_type_id(field)
            if self._should_raise(field_type_id):
                template = "unknown type: {0}"
                raise FieldSorterException(template.format(str(field)))

            element_name = self.get_element_name(
                field_name, field_type_id, field)

            fields_with_details.append(
                FieldWithDetails(
                    element_name, field_type_id, field, field_name))
        return sorted(
            fields_with_details,
            key=lambda t: (not isinstance(t[2], Property), t[0]))
