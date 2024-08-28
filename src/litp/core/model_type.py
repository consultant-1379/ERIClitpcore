##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from litp.core.litp_logging import LitpLogger
from litp.core.validators import RegexValidator
from litp.core.exceptions import DuplicateChildTypeException


log = LitpLogger()

# Access modes
PROPERTY_READ = "read"
PROPERTY_WRITE = "PROPERTY_WRITE"


class PropertyType(object):
    """PropertyType class for instantiating new property types.

    **Example Usage:**

    .. code-block:: python

        PropertyType('very_basic_string', regex="^.*$")

    """
    def __init__(self, property_type_id, regex=None, validators=None,
                deprecated=False, regex_error_desc=None):
        """Defines a PropertyType.

        :param property_type_id: ID of this property type. \
                                 Convention is to use lowercase, numbers \
                                 and underscores.
        :type  property_type_id: str
        :param            regex: Regex for this property (Adds a \
                                 RegexValidator() to the list of validators).
        :type             regex: str
        :param       validators: List of \
                             :class:`litp.core.validators.PropertyValidator`\
                             objects for this property.
        :type        validators: list
        :param       deprecated: True if item is deprecated.
        :type        deprecated: bool
        :param       regex_error_desc: Optional validation error description \
                                        (if property regex validation fails).
        :type        regex_error_desc: str

        """
        super(PropertyType, self).__init__()
        if validators is None:
            validators = []

        self.property_type_id = property_type_id
        self.regex = regex or "^.*$"
        self.default_validators = [RegexValidator(self.regex,
                regex_error_desc=regex_error_desc)]
        self.validators = self.default_validators + validators
        self.deprecated = deprecated

    def __repr__(self):
        return "<PropertyType %s>" % (self.property_type_id)


class ItemType(object):
    """
    All items in the Deployment Model belong to an Item Type, which defines the
    properties and structure of these items. If defining multiple children
    (Child) of the same ItemType, they must be placed into a Collection.

    **Example Usage:**

    .. code-block:: python

        ItemType('example-item',
                 item_description="An example item type.",
                 name=Property('basic_string',
                               prop_description="Name of example-item.")
        )

    """
    def __init__(self, item_type_id, extend_item="", item_description="",
                 require=None, required=True, validators=None,
                 deprecated=False, **structure):
        r"""
        Constructs an Item Type to register with the Deployment Manager

        :param      item_type_id: ID of this item type. \
                                  Convention is to use lowercase, numbers \
                                  and hyphens.
        :type       item_type_id: str
        :param       extend_item: ID of item type which this extends.
        :type        extend_item: str
        :param  item_description: A description of the item type.
        :type   item_description: str
        :param           require: Sibling item on which this depends \
                                  (deprecated).
        :type            require: str
        :param          required: If item is required (deprecated).
        :type           required: bool
        :param        validators: List of validators for this item.
        :type         validators: list
        :param        deprecated: True if item is deprecated.
        :type         deprecated: bool
        :param      \**structure: The remaining kwargs are passed as the \
                                  structure of the item. The item types of \
                                  the fields must be unique if defining \
                                  Child elements.
        """

        if validators is None:
            validators = []
        self.item_type_id = item_type_id
        self.item_description = item_description
        self.extend_item = extend_item
        self.deprecated = deprecated
        self.validators = validators

        self._check_duplicate_child_types(structure)
        self.structure = structure
        self._validate_structure(structure)

    def __repr__(self):
        return "<ItemType %s>" % (self.item_type_id,)

    def _check_duplicate_child_types(self, structure):
        if structure:
            types = []
            for n, v in structure.items():
                if not v in types:
                    if isinstance(v, Child):
                        types.append(v)
                else:
                    raise DuplicateChildTypeException(
                        "%s duplicates the type %s "
                        "already defined in structure" % (n, v))

    def _validate_structure(self, structure):
        for field, value in structure.iteritems():
            if not (
                isinstance(value, Property) or
                isinstance(value, _BaseStructure)
            ):
                raise TypeError(
                    "invalid type {0} for field: {1}".format(
                        type(value), str(field)))

    def get_properties(self):
        """
        Returns all property names for this item type.

        :rtype: list
        :returns: a list of (string) property names for this item type
        """
        return [
            prop_name for prop_name, prop_type in self.structure.iteritems()
            if isinstance(prop_type, Property)
        ]

    def get_property_types(self):
        """
        Returns all property types for this item type.

        :rtype: list
        :returns: a list of property types for this item type
        """
        return [
            property_type for property_type in self.structure.itervalues()
            if isinstance(property_type, Property)
        ]


class _BaseStructure(object):
    """Base class for all structure elements"""
    def __init__(self, item_type_id, item_description="", require=None,
                 deprecated=False):
        self.item_type_id = item_type_id
        self.item_description = item_description
        self._require = require
        self.deprecated = deprecated

    def __repr__(self):
        return "<ItemType %s>" % (self.item_type_id,)

    def __eq__(self, other):
        if type(self) is type(other):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        if type(self) is type(other):
            return not self.__eq__(other)
        return NotImplemented


class Property(_BaseStructure):
    """
    An Item Type's :class:`Property` is a single named piece of information
    that pertains to that Item Type. All properties for a given Item Type exist
    side-by-side in a flat relationship. Properties must be given the ID of a
    :class:`PropertyType` when they are defined in an Item Type's structure.


        **Example Usage:**

        .. code-block:: python

            ItemType('example-item', "An example item type."
                      prop=Property('basic_string',
                                    prop_description="example property"),
                      req_prop=Property('basic_string',
                                    prop_description="required property",
                                    required=True)
            )

    """

    def __init__(self, prop_type_id, prop_description="", default=None,
                 required=False, deprecated=False, updatable_plugin=False,
                 updatable_rest=True, configuration=True, site_specific=False):
        """Defines a Property structural element

        :param      prop_type_id: ID of this property type.
        :type       prop_type_id: str
        :param  prop_description: A description of this property.
        :type   prop_description: str
        :param           default: A default value for this property.
        :type            default: str
        :param          required: If the property is required.
        :type           required: bool
        :param        deprecated: True if item is deprecated.
        :type         deprecated: bool
        :param  updatable_plugin: If True, the property value can be updated
                          from plugins using the
                          :class:`litp.core.task.CallbackTask` callback
                          function to set the attribute on the
                          :class:`litp.core.model_manager.QueryItem`
                          returned as a result of a
                          :func:`litp.core.callback_api.CallbackApi.query`.
        :type   updatable_plugin: bool
        :param    updatable_rest: If True, the property can be updated using
                                  the REST interface.
        :type     updatable_rest: bool
        :param    configuration: If True, the property affects system
                                 configuration and generate tasks when updated.
        :type     configuration: bool
        :param     site_specific: If True, the property restriction element is
                                  configured in XSD as the regex property_type
                                  regex or %%[a-zA-Z0-9-._]+%%.
        :type      site_specific: bool

        .. note::
            Property updates driven by :class:`litp.core.task.CallbackTask`
            tasks trigger property and item validation on the item being
            updated.
        """
        super(Property, self).__init__(
                item_type_id=prop_type_id,
                item_description=prop_description,
                deprecated=deprecated
                )
        self.prop_type_id = prop_type_id
        self.prop_type = None
        self.prop_description = prop_description
        self.required = required
        if default is not None and type(default) is not str:
            raise ValueError(
                "default value must be string (%s)" % repr(default))
        self.default = default
        self.updatable_plugin = updatable_plugin
        self.updatable_rest = updatable_rest
        self.configuration = configuration
        self.site_specific = site_specific

    def __repr__(self):
        return "<Property %s>" % (self.prop_type_id,)


class View(_BaseStructure):
    """
    An Item Type's :class:`View` is a single named piece of information that is
    derived dynamically from the Deployment Model using logic implemented in a
    Model Extension. Views are read-only and are not exposed through the REST
    interface - they are available to plugins in the same way Properties are
    and allow Deployment Model access logic to be factored out in Model
    Extensions.

    Views must be given the ID of a :class:`PropertyType` when they are
    defined in an Item Type's structure.


        **Example Usage:**

        .. code-block:: python

           class MyExtension(ModelExtension):

               @staticmethod
               def view_method(plugin_api_context, query_item):
                   return 'value'

               def define_property_types(self):

                   ItemType('example-item', "An example item type."
                       view_alpha=View(
                           'basic_string',
                           view_description='My View',
                           callable_method=MyExtension.view_method))

    """

    def __init__(self, prop_type_id, callable_method, view_description="",
                 deprecated=False):
        """Defines a View structural element

        :param      prop_type_id: ID of this view's property type.
        :type       prop_type_id: str
        :param  view_description: A description of this View.
        :type   view_description: str
        :param   callable_method: A static method of the extension that
                                  implements the View
        :type         deprecated: function
        :param        deprecated: True if item is deprecated.
        :type         deprecated: bool

        """
        super(View, self).__init__(
                item_type_id=prop_type_id,
                item_description=view_description,
                deprecated=deprecated
                )
        self.prop_type_id = prop_type_id
        self.prop_type = None
        self.callable_method = callable_method
        self.required = False
        self.default = callable_method

    def __repr__(self):
        return "<View %s: %s>" % (self.prop_type_id, self.callable_method)


class Child(_BaseStructure):
    """
    An :class:`ItemType`'s :class:`Child` is a named structural element that
    establishes a direct hierarchical relationship between instances of that
    :class:`ItemType` and instances of a target :class:`ItemType`.

        **Example Usage:**

        .. code-block:: python

            ItemType('example-item', "An example item type."
                     child=Child('another-example-item'), )
            )
    """
    def __init__(self, item_type_id, required=False, require=None,
                 deprecated=False):
        """Defines a child structural element.

        :param      item_type_id: ID of the type of this child item.
        :type       item_type_id: str
        :param           require: Sibling item with on which this depends.
        :type            require: str
        :param          required: If the child item is required.
        :type           required: bool
        :param        deprecated: True if item is deprecated.
        :type         deprecated: bool

        """
        super(Child, self).__init__(
            item_type_id=item_type_id,
            require=require,
            deprecated=deprecated,
            item_description="Child of %s" % item_type_id
        )
        self.required = required

    def __repr__(self):
        return "<Child %s>" % (self.item_type_id,)


class Collection(_BaseStructure):
    """
    An Item Type's :class:`Collection` is a named structural element under
    which a set of instances of the target Item Type may be created.

        **Example Usage:**

        .. code-block:: python

            ItemType('example-item', "An example item type."
                      other_items=Collection('other-item'), )
            )

    """
    def __init__(self, item_type_id, min_count=0, max_count=9999,
                 require=None, deprecated=False):
        """Defines a collection structural element.

        :param      item_type_id: ID of item types which this collection \
                                  collection can contain.
        :type       item_type_id: str
        :param         min_count: Minimum number of items in this collection.
        :type          min_count: int
        :param         max_count: Max number of items in this collection.
        :type          max_count: int
        :param           require: Sibling item with on which this depends.
        :type            require: str
        :param        deprecated: True if item is deprecated.
        :type         deprecated: bool

        """
        super(Collection, self).__init__(
            item_type_id=item_type_id,
            require=require,
            deprecated=deprecated,
            item_description="Collection of %s" % item_type_id
        )
        self.min_count = min_count
        self.max_count = max_count

    def __repr__(self):
        return "<Collection %s>" % (self.item_type_id,)


class RefCollection(Collection):
    """
    A :class:`RefCollection` in an Item Type's structure is a named element
    under which several instances of the target Item Type may be inherited
    from specified source paths. Unlike a :class:`Collection`, no Item
    instance can be created under a :class:`RefCollection` of its parent
    Item. Instead, the :class:`RefCollection`'s targets are created
    elsewhere in the Deployment Model and is inherited to the
    :class:`RefCollection`.

        **Example Usage:**

        .. code-block:: python

            ItemType('example-item', "An example item type."
                      other_items=RefCollection('other-item'), )
           )

    """
    def __init__(self, item_type_id, min_count=0, max_count=9999,
                 require=None, exclusive=False, deprecated=False,
                 read_only=False):
        """Defines a reference collection structural element.

        :param      item_type_id: ID of inherited item types which this \
                                  collection can contain.
        :type       item_type_id: str
        :param         min_count: Minimum number of items in this collection.
        :type          min_count: int
        :param         max_count: Max number of items in this collection.
        :type          max_count: int
        :param           require: Sibling item with on which this depends.
        :type            require: str
        :param        deprecated: True if item is deprecated.
        :type         deprecated: bool
        :param         read_only: True if this item or descendants of this \
                                  item cannot be updated.
        :type          read_only: bool

        """
        super(RefCollection, self).__init__(
            item_type_id=item_type_id,
            min_count=min_count,
            max_count=max_count,
            require=require,
            deprecated=deprecated
        )
        self.item_description = "Ref-collection of %s" % self.item_type_id
        self.is_multi_ref_allowed = not exclusive
        self.read_only = read_only

    def __repr__(self):
        return "<RefCollection %s>" % (self.item_type_id,)


class Reference(_BaseStructure):
    """
    A :class:`Reference` in an Item Type's structure is a named element that
    may be inherited from an instance of the target Item Type from a
    specified source path. Unlike a :class:`Child`, no Item instance can be
    created as a :class:`Reference` of its parent Item.  Instead, the
    :class:`Reference`'s target is created elsewhere in the Deployment Model
    and is inherited to the
    :class:`Reference`.

        **Example Usage:**

        .. code-block:: python

            ItemType('example-item', "An example item type."
                      inherit=Reference('other-item'), )
            )

    """
    def __init__(self, item_type_id, required=False, default=False,
                 require=None, exclusive=False, deprecated=False,
                 read_only=False, **properties):
        """Defines a reference structural element.

        :param         item_type_id: ID of item types which this reference \
                                     can refer to.
        :type          item_type_id: str
        :param             required: True if item is required.
        :type              required: bool
        :param              require: Sibling item with on which this depends.
        :type               require: str
        :param            exclusive: Whether reference is exclusive to a \
                                     single item.
        :type             exclusive: bool
        :param           deprecated: True if item is deprecated.
        :type            deprecated: bool
        :param            read_only: True if this item or descendants of this \
                                     item cannot be updated.
        :type             read_only: bool

        """
        super(Reference, self).__init__(
            item_type_id=item_type_id,
            require=require,
            deprecated=deprecated,
            item_description="Reference to %s" % item_type_id
        )
        self.default = default
        self.required = required
        self.properties = properties
        self.is_multi_ref_allowed = not exclusive
        self.read_only = read_only

    def __repr__(self):
        return "<Reference %s>" % (self.item_type_id,)
