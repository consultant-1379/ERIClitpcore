##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.model_type import ItemType, Property, PropertyType, Collection
from litp.core.extension import ModelExtension
from litp.core.validators import IsNotDigitValidator
from litp.core.validators import PropertyValidator
from litp.core.validators import ValidationError

from litp.core.litp_logging import LitpLogger
log = LitpLogger()


class DNSClientExtension(ModelExtension):
    """
    DNSClient Model Extension.
    This model extension defines property and item types that let the user
    specify DNS client and search domain names for the
    resolv.conf file.
    """
    def define_property_types(self):
        return [
            PropertyType("position_value", regex=r"^[1-3]$"),
            PropertyType("comma_separated_domain_names",
                regex=r"^(([a-zA-Z0-9]|[a-zA-Z0-9]"
                r"[a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*"
                r"([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])"
                r"(,+(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*"
                r"([A-Za-z]|[A-Za-z][A-Za-z0-9\-]*[A-Za-z0-9]))*$",
                 validators=[IsNotDigitValidator(), MaxLengthValidator(256),
                              MaxCountValidator(1, 6, ',')])]

    def define_item_types(self):
        item_types = []
        item_types.append(
            ItemType("dns-client",
                     extend_item="node-config",
                     item_description="A node-level DNS client (resolv.conf)"
                     " configuration.",
                     search=Property("comma_separated_domain_names",
                     required=False,
                     site_specific=True,
                     prop_description="Comma separated list of domain names"),
                     nameservers=Collection(
                        "nameserver", min_count=1, max_count=3)))

        item_types.append(
            ItemType("nameserver",
                item_description=(
                    "A nameserver within the DNS (Domain Name System) client "
                    "configuration."
                ),
                ipaddress=Property("ipv4_or_ipv6_address",
                    required=True,
                    site_specific=True,
                    prop_description="IP address of nameserver"),
                position=Property("position_value", required=True,
                    prop_description="Position of the "
                        "nameserver in servers list")
            )
        )
        return item_types


class MaxLengthValidator(PropertyValidator):
    """
    Validates that a property with property_name is not greater than \
    the property with limit_property_name.
    """

    def __init__(self, max_length):
        """
        MaxValueValidator with property names.

        We assume that the property names correspond to Property objects that
        are required.

        :param  max_length: max length
        :type   max_length: int

        """
        super(MaxLengthValidator, self).__init__()
        self.max_length = max_length

    def validate(self, property_value, ):
        if len(property_value) > self.max_length:
            return ValidationError(
                error_message="Length of property cannot be "
                "more than %s characters" % (self.max_length)
                )


class MaxCountValidator(PropertyValidator):
    """
    Validates that a property with property_name has not less than \
    the min element count and not greater than the max element count \
    split by the delimiter.
    """

    def __init__(self, min_count, max_count, delimiter):
        """
        MaxCountValidator with property names.

        We assume that the property names correspond to Property objects that
        are required.

        :param  max_count: max count
        :type   max_count: int

        :param  min_count: min count
        :type   min_count: int

        :param  delimiter: element delimiter
        :type   delimiter: string

        """
        super(MaxCountValidator, self).__init__()
        self.max_count = max_count
        self.min_count = min_count
        self.delimiter = delimiter

    def validate(self, property_value, ):
        values = property_value.split(self.delimiter)
        if len(values) < self.min_count:
            return ValidationError(
                error_message=("A minium of %s domains per"
                " search may be specified" % (self.min_count))
                )
        elif len(values) > self.max_count:
            return ValidationError(
                error_message=("A maximum of %s domains per"
                " search may be specified" % (self.max_count))
                )
