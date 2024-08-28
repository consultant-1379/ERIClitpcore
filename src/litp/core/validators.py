##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


import re
import netaddr
from os.path import isdir

import litp.core.constants as constants
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class ValidationError(object):
    """
    Class to represent validation errors.
    """
    def __init__(self, item_path=None, property_name=None, error_message="",
                 error_type=constants.VALIDATION_ERROR):
        """
        :param item_path: Path to item with error.
        :type  item_path: str
        :param property_name: Name of property with error.
        :type  property_name: str
        :param error_message: Error message.
        :type  error_message: str
        :param error_type: Error type.
        :type  error_type: str default 'ValidationError'

        """
        self.item_path = item_path
        self.error_message = error_message
        self.error_type = error_type
        self.property_name = property_name

    def __repr__(self):
        return "<%s - %s - %s>" % (self.item_path or self.property_name,
                                   self.error_type, self.error_message)

    def __eq__(self, rhs):
        return rhs and type(rhs) is ValidationError and \
            self.item_path == rhs.item_path and \
            self.error_message == rhs.error_message and \
            self.error_type == rhs.error_type and \
            self.property_name == rhs.property_name

    def __hash__(self):
        return hash((self.item_path, self.error_message,
                     self.error_type, self.property_name))

    def to_dict(self):
        ret = {
            'error': self.error_type,
            'message': self.error_message
        }
        if self.item_path is not None:
            ret['uri'] = self.item_path
        if self.property_name is not None:
            ret['property_name'] = self.property_name
        return ret


class PropertyValidator(object):
    """
    Base class for all PropertyValidator.
    """
    def __init__(self):
        """
        The constructor can be used to pass validation options.
        """
        pass

    def validate(self, _property_value):
        """
        The validate method performs validation and can \
        return None or a ValidationError.

        :param properties: The properties of the item to validate.
        :type  properties: dict

        :returns: Either a ValidationError object or None
        :type: :class:`litp.core.validators.ValidationError` or None

        """
        return None


class RegexValidator(PropertyValidator):
    """
    Validates the value of the property using the regex provided:
    """
    def __init__(self, regex, regex_error_desc=None):
        super(RegexValidator, self).__init__()
        self.regex = regex
        self.regex_error_desc = regex_error_desc

    def __repr__(self):
        return "<RegexValidator - '%s'>" % self.regex

    def validate(self, property_value):
        re_compiled = re.compile(self.regex)
        if not re_compiled.search(unicode(property_value)):
            log.trace.info("RegexError: '%s' does not match %s" % (
                property_value, self.regex)
            )
            if self.regex_error_desc:
                return ValidationError(error_message=(
                    "Invalid value '%s'. %s" %
                        (property_value, self.regex_error_desc)
                ))
            else:
                return ValidationError(error_message=(
                    "Invalid value '%s'." % property_value)
                )


class IsNotDigitValidator(PropertyValidator):
    """
    Validates that the value of the property is not a digit.
    """
    def __init__(self):
        super(IsNotDigitValidator, self).__init__()

    def validate(self, property_value):
        if str(property_value) == 'None':
            return ValidationError(
                error_message=("Invalid value: '%s'" % property_value)
            )
        if property_value.isdigit():
            return ValidationError(
                error_message=(
                    "Invalid value: '%s' is digit " % property_value
                )
            )


class NetworkValidator(PropertyValidator):
    """
    Validates that the value of the property is a valid IPv4 network.
    """
    def validate(self, property_value):
        if not property_value:
            return None
        try:
            net = netaddr.IPNetwork(property_value, version=4)
        except netaddr.AddrFormatError as e:
            if e.args[0] == 'invalid prefix for IPv4 address!':
                error_message = ('Invalid prefix for destination IPv4 network '
                                 'at \'{0}\''.format(property_value))
            else:
                error_message = "Invalid IPv4 subnet value '%s'" % (
                        str(property_value))
            return ValidationError(error_message=error_message)
        except ValueError as e:
            error_message = "Invalid IPv4 subnet value '%s'" % (
                    str(property_value))
            return ValidationError(error_message=error_message)
        except Exception as e:
            return ValidationError(
                error_message="Invalid value: %s" % str(e))

        if not '/' in property_value:
            return ValidationError(
                error_message="Subnet must include prefix length"
            )


class NetworkValidatorV6(PropertyValidator):
    """
    Validates the property's value is a valid IPv6 Network
    """
    def validate(self, property_value):
        if not property_value:
            return None

        try:

            net = netaddr.IPNetwork(property_value, version=6)
            if net.is_multicast():
                return ValidationError(
                        error_message="Subnet cannot be a multicast address",
                    )
            if net.is_reserved():
                return ValidationError(
                        error_message="Subnet cannot be a reserved network",
                    )

        except netaddr.AddrFormatError as e:
            if e.args[0] == 'invalid prefix for IPv6 address!':
                error_message = ('Invalid prefix for destination IPv6 network '
                                 'at \'{0}\''.format(property_value))
            else:
                error_message = "Invalid IPv6 subnet value '%s'" % (
                    str(property_value))
            return ValidationError(error_message=error_message)
        except Exception as e:
            return ValidationError(
                error_message="Invalid value: %s" % str(e))

        if not '/' in property_value:
            return ValidationError(
                error_message="Subnet must include prefix length"
            )


class NotEmptyStringValidator(PropertyValidator):
    '''
    Validates that the value of the property is not an empty string.
    '''
    def validate(self, property_value):
        if property_value is not None \
            and not property_value:
            return ValidationError(
                error_message="Property cannot be empty"
                )


class ZeroAddressValidator(PropertyValidator):
    """
    Validates that the value of the property is not a zero address network
    (that is, 0.0.0.0/0).
    """
    def validate(self, property_value):
        ZEROADDRESS = '0.0.0.0/0'
        if property_value == ZEROADDRESS:
            return ValidationError(
                error_message="Invalid subnet value '%s'"
                    % str(property_value))


class IPAddressValidator(PropertyValidator):
    """
    Validates the value of the property in the following 3 scenarios:

    If validating a property of type ipv4_address (version set to 4) then \
    the value must be a valid IPv4 address.

    If validating a property of type ipv6_address (version set to 6) then \
    the value must be a valid IPv6 address.

    If validating a property of type ipv4_or_ipv6_address (version set to \
    both) then the value must be either a valid IPv4 or a valid IPv6 address.
    """

    def __init__(self, version="4"):
        """Check property is a valid IP Address

        :param version: IP version to check for ("4", "6" or "both"). \
                        Default is 4
        :type  version: str

        """
        super(IPAddressValidator, self).__init__()
        self.version = version

    def validate(self, property_value):
        try:
            if (str(self.version) == '4' \
                    and not netaddr.valid_ipv4(property_value,
                        netaddr.INET_PTON)) or \
                (str(self.version) == '6' and \
                    not netaddr.valid_ipv6(property_value)):
                raise netaddr.AddrFormatError
            if self.version == 'both' and not (\
                netaddr.valid_ipv4(property_value,
                        netaddr.INET_PTON) or
                netaddr.valid_ipv6(property_value)):
                raise netaddr.AddrFormatError
            address = netaddr.IPAddress(property_value)
        except (netaddr.AddrFormatError, ValueError):
            version_text = "IPv6Address" if str(self.version) == '6' \
                    else "IPAddress"
            return ValidationError(
                error_message="Invalid %s value '%s'"
                    % (version_text, str(property_value)))
        if str(address.version) != self.version and self.version != "both":
            return ValidationError(
                error_message=("Invalid IPAddress value '%s' for IPv%s"
                    % (property_value, self.version)))


class DirectoryExistValidator(PropertyValidator):
    """
    Checks whether the directory exists.
    """
    def __init__(self):
        super(DirectoryExistValidator, self).__init__()

    def validate(self, properties):
        property_value = properties.get("path")
        if str(property_value) == 'None':
            return ValidationError(error_message=(
                "Invalid value: '%s' directory does not exist "
                % str(property_value)
            ),
            error_type=constants.VALIDATION_ERROR
        )
        if not isdir(property_value):
            return ValidationError(
                error_message=(
                    "Invalid value: '%s' directory does not exist "
                    % property_value
                ),
                error_type=constants.VALIDATION_ERROR
            )


class ItemValidator(object):
    """
    Base class for all ItemValidator.
    """
    def __init__(self):
        """
        The constructor can be used to pass validation options.
        """
        pass

    def validate(self, _properties):
        """
        The validate method performs validation and can return \
        a ValidationError object.

        :param _properties: The properties of the item to validate.
        :type  _properties: dict

        :returns: Either a ValidationError object or None
        :type: :class:`litp.core.validators.ValidationError` or None
        """
        return None


class MaxValueValidator(ItemValidator):
    """
    Validates that a property with property_name is not greater than \
    the property with limit_property_name.
    """

    def __init__(self, limit_property_name, property_name):
        """
        MaxValueValidator with property names.

        We assume that the property names correspond to Property objects that
        are required.

        :param  limit_property_name: Limit property name
        :type   limit_property_name: str
        :param        property_name: Name of property to ensure it's value \
                                     is not greater than the limit_property
        :type         property_name: str

        """
        super(MaxValueValidator, self).__init__()
        self.limit_property_name = limit_property_name
        self.property_name = property_name

    def validate(self, properties):
        """Compares the values of the property name.

        :param    properties (dict): Item properties
        :returns: None or ValidationError

        """
        limit_value = properties.get(self.limit_property_name, None)
        value = properties.get(self.property_name, None)

        if all((limit_value, value)) and value > limit_value:
            return ValidationError(
                property_name=self.property_name,
                error_message=("%s value is greater than %s value" %
                               (self.property_name, self.limit_property_name)),
            )


class PropertyLengthValidator(PropertyValidator):
    """
    Validates the length the property against the provided max_length.
    """

    def __init__(self, max_length):
        """
        PropertyLengthValidator.

        Validates the length of the given property

        :param  int max_length: Length of string

        """
        super(PropertyLengthValidator, self).__init__()
        self.max_length = max_length

    def validate(self, property_value):
        """
        Validates the property length

        :param    str property_value: The string value of the property to \
                        validate
        :returns: Either a ValidationError object or None
        :type: litp.core.validators.ValidationError or None

        """
        if len(property_value) > self.max_length:
            return ValidationError(
                error_message=("Property cannot be longer than %s" %
                               (self.max_length,)),
            )


class IntValidator(PropertyValidator):
    """
    Validates that the value of a property is a valid integer.
    """
    def __init__(self):
        super(IntValidator, self).__init__()

    def validate(self, property_value):
        try:
            int(property_value)
        except ValueError:
            msg = "Invalid value '%s', numeric value expected" % \
                str(property_value)
            err = ValidationError(error_message=msg)
            return err
        else:
            return None


class IntRangeValidator(PropertyValidator):
    """
    Validates that the value of the property is within a range.
    """

    def __init__(self, min_value=None, max_value=None):
        """
        IntRangeValidator.

        Validates the value of the property is within the given
        range of ``min_value`` and ``max_value``.

        :param min_value: Min value to validate against.
        :type  min_value: int or None
        :param max_value: Max value to validate against.
        :type  max_value: int or None

        :returns: Either a ValidationError object or None
        :type: litp.core.validators.ValidationError or None
        """
        super(IntRangeValidator, self).__init__()
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, property_value):
        try:
            prop_val_int = int(property_value)
        except ValueError:
            msg = "Invalid value '%s', numeric value expected" % \
                str(property_value)
            err = ValidationError(error_message=msg)
            return err

        if (self.min_value is not None and prop_val_int < self.min_value) or \
                (self.max_value is not None and prop_val_int > self.max_value):
            msg = "Value outside range {0} - {1}".format(
                    self.min_value, self.max_value)
            err = ValidationError(error_message=msg)
            return err


class OnePropertyValidator(ItemValidator):
    """
    Validates that exactly one of the properties is defined.
    """

    def __init__(self, prop_names):
        """
        OnePropertyValidator.

        Validates that exactly one of the required properties is defined.

        :param prop_names: Names of the mutually exclusive properties.
        :type  prop_names: list

        :returns: None or ValidatonError

        """
        super(OnePropertyValidator, self).__init__()
        self.prop_names = prop_names

    def validate(self, properties):
        count = 0
        for prop_name in self.prop_names:
            if prop_name in properties:
                count += 1
        if count == 0 or count > 1:
            msg = "One of %s property must be set." % \
                  ' or '.join(self.prop_names)
            err = ValidationError(error_message=msg)
            return err


class RestrictedPropertiesValidator(PropertyValidator):
    """
    Validates that restricted property values are not supplied.
    """

    default_message = "%s is not allowed as value for this property."

    def __init__(self, restricted_prop_values, custom_message=None):
        """
        Restricts the allowed property values.

        :param restricted_prop_values: Restricted property values.
        :type  restricted_prop_values: list

        :param custom_message: Custom message, must have 1 str argument.
        :type  custom_message: str

        :returns: None or ValidationError

        """
        super(RestrictedPropertiesValidator, self).__init__()
        self.prop_values = restricted_prop_values
        self.message_template = custom_message or self.default_message

    def validate(self, property_value):
        if property_value in self.prop_values:
            msg = self.message_template % property_value
            err = ValidationError(error_message=msg)
            return err


class IPv6AddressAndMaskValidator(PropertyValidator):
    '''
    Validates that the value of the property is a valid IPv6
    address which may or may not have a network prefix mask.
    '''
    def __init__(self):
        super(IPv6AddressAndMaskValidator, self).__init__()

    def _create_error(self, ip_address, error_subtype):
        return ValidationError(
            error_message="IPv6 address '{ip}' {whinge}".format(
                ip=ip_address,
                whinge=error_subtype
                )
            )

    def validate(self, property_value):
        try:
            netaddr.IPNetwork(property_value, version=6)
        except netaddr.AddrFormatError:
            return self._create_error(property_value, 'is not valid')
        try:
            address, suffix = property_value.split('/', 1)
            try:
                suffix_value = int(suffix)
                if suffix_value == 0:
                    # Pythonic: Assuming exceptions are cheap.. :)
                    raise ValueError()
            except ValueError:
                return self._create_error(property_value, 'is not valid')
        except ValueError:
            address = property_value
            suffix = None

        # There is a difference of opinion whether stuff like 0::1 should be
        # 'not valid' or 'not permitted' ...
        parsed_address = netaddr.IPAddress(address)
        if parsed_address == netaddr.IPAddress('::') or \
            parsed_address == netaddr.IPAddress('::1'):
            return self._create_error(property_value, 'is not permitted')
