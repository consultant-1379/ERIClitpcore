import unittest
import mock

from litp.core.validators import ValidationError
from litp.core.validators import PropertyLengthValidator
from litp.core.validators import IPAddressValidator
from litp.core.validators import IntValidator
from litp.core.validators import IntRangeValidator
from litp.core.validators import IsNotDigitValidator
from litp.core.validators import DirectoryExistValidator
from litp.core.validators import IPv6AddressAndMaskValidator
from litp.core.validators import NetworkValidator
from litp.core.validators import NetworkValidatorV6
from litp.core.validators import NotEmptyStringValidator
from litp.core.validators import MaxValueValidator

class TestValidatorError(unittest.TestCase):

    def test_validators_equals(self):
        v1 = ValidationError()
        v2 = ValidationError()
        self.assertEqual(v1, v2)

    def test_validators_equals_2(self):
        v1 = ValidationError(item_path='one/path',
                             error_message="error")
        v2 = ValidationError(item_path='one/path',
                             error_message='error')
        self.assertEqual(v1, v2)
        d = dict()
        d[v1] = 'foo'
        self.assertTrue(v2 in d)
        self.assertEqual(hash(v1), hash(v2))

    def test_validators_equals_not(self):
        v1 = ValidationError(item_path='one/path')
        v2 = ValidationError(item_path='scond/path')
        self.assertNotEquals(v1, v2)

        v3 = ValidationError(item_path='one',
                             error_message='e1')
        v4 = ValidationError(item_path='one',
                             error_message='e2')
        self.assertNotEquals(v3, v4)

    def test_validators_set(self):
        v1set = set([ValidationError(item_path='one'),
                 ValidationError(item_path='two')])

        v2set = set([ValidationError(item_path='one'),
                 ValidationError(item_path='two')])

        self.assertEqual(v1set, v2set)

    def test_ipvalidator(self):
        validate = IPAddressValidator().validate
        address = ' 10.10.10.101'
        self.assertEquals(ValidationError, type(validate(address)))

        address = '10.10.10.101 '
        self.assertEquals(ValidationError, type(validate(address)))

        address = '0 10.10.10.100'
        self.assertEqual(ValidationError, type(validate(address)))

        address = '08.01.01.01'
        self.assertEquals(ValidationError, type(validate(address)))

        address = '0x80.192.168.1'
        self.assertEquals(ValidationError, type(validate(address)))

        address = '1.2.3.4'
        self.assertEquals(None, validate(address))

        address = "10.10"
        self.assertEquals(ValidationError, type(validate(address)))

        address = "10.10"
        validator = IPAddressValidator("both")
        self.assertEquals(ValidationError, type(validator.validate(address)))

    def test_property_length_validator(self):
        validator = PropertyLengthValidator(10)
        self.assertEquals(None, validator.validate("1234567890"))
        self.assertEquals(ValidationError(
            error_message="Property cannot be longer than 10"),
            validator.validate("1234567890_A"))

    def test_not_None_validator(self):
        validator = IsNotDigitValidator()
        self.assertEquals(ValidationError(
                        error_message="Invalid value: 'None'",
                          error_type="ValidationError"),
                        validator.validate(None))

    def test_directory_exist_validator(self):
        validator = DirectoryExistValidator()
        none_directory = {'version': '&&', 'name': 'None', 'path': 'None'}
        null_directory = {'version': '&&', 'name': 'None'}
        bad_directory = {'version': 'rhel6', 'name': 'x', 'path': 'badpath'}
        exist_path = {u'version': u'rhel6', u'name': u'home', 'path': '/home'}
        error_message1 = "Invalid value: 'badpath' directory does not exist "
        self.assertEquals(None, validator.validate(exist_path))
        self.assertEquals(ValidationError(
             error_message=error_message1,
                 error_type="ValidationError"),
                 validator.validate(bad_directory))
        error_message2 = "Invalid value: 'None' directory does not exist "
        self.assertEquals(ValidationError(
            error_message=error_message2,
            error_type="ValidationError"),
                          validator.validate(none_directory))
        self.assertEquals(ValidationError(
            error_message=error_message2,
            error_type="ValidationError"),
                          validator.validate(null_directory))


class TestIntRangeValidator(unittest.TestCase):
    @mock.patch('litp.core.validators.ValidationError')
    def test_non_numeric_unicode_value_in_message(self, validation_error):
        validator = IntRangeValidator()
        result = validator.validate(u'str')
        self.assertFalse(result is None)
        msg = "Invalid value 'str', numeric value expected"
        validation_error.assert_called_once_with(error_message=msg)

    @mock.patch('litp.core.validators.ValidationError')
    def test_zero_min_range_value(self, validation_error):
        # TORF-110536
        validator = IntRangeValidator(0, 5)
        result = validator.validate('-2')
        self.assertFalse(result is None)
        msg = "Value outside range 0 - 5"
        validation_error.assert_called_once_with(error_message=msg)

        result = validator.validate('2')
        self.assertTrue(result is None)

    @mock.patch('litp.core.validators.ValidationError')
    def test_zero_max_range_value(self, validation_error):
        validator = IntRangeValidator(-2, 0)
        result = validator.validate('2')
        self.assertFalse(result is None)
        msg = "Value outside range -2 - 0"
        validation_error.assert_called_once_with(error_message=msg)

        result = validator.validate('-1')
        self.assertTrue(result is None)

    @mock.patch('litp.core.validators.ValidationError')
    def test_zero_property_value(self, validation_error):
        validator = IntRangeValidator(2, 5)
        result = validator.validate('0')
        self.assertFalse(result is None)
        msg = "Value outside range 2 - 5"
        validation_error.assert_called_once_with(error_message=msg)

        validator = IntRangeValidator(-2, 2)
        result = validator.validate('0')
        self.assertTrue(result is None)

    @mock.patch('litp.core.validators.ValidationError')
    def test_none_range_value(self, validation_error):
        validator = IntRangeValidator(None, 5)
        result = validator.validate('7')
        self.assertFalse(result is None)
        msg = "Value outside range None - 5"
        validation_error.assert_called_once_with(error_message=msg)


class TestIntValidator(unittest.TestCase):
    @mock.patch('litp.core.validators.ValidationError')
    def test_non_numeric_unicode_value_in_message(self, validation_error):
        validator = IntValidator()
        result = validator.validate(u'str')
        self.assertFalse(result is None)
        msg = "Invalid value 'str', numeric value expected"
        validation_error.assert_called_once_with(error_message=msg)

    @mock.patch('litp.core.validators.ValidationError')
    def test_integer_value(self, validation_error):
        validator = IntValidator()
        result = validator.validate(u'234323')
        self.assertTrue(result is None)

    @mock.patch('litp.core.validators.ValidationError')
    def test_float_value(self, validation_error):
        validator = IntValidator()
        result = validator.validate(u'3.14159')
        self.assertFalse(result is None)
        msg = "Invalid value '3.14159', numeric value expected"
        validation_error.assert_called_once_with(error_message=msg)


class TestIPv6AddressAndMaskValidator(unittest.TestCase):
    def test_netmask_missing(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127')
        self.assertTrue(result is None)

    def test_netmask_malformed(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127/')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '::127/' is not valid"),
            result
            )

    def test_netmask_bad(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127/xxx')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '::127/xxx' is not valid"),
            result
            )

    def test_netmask_of_one(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127/1')
        self.assertTrue(result is None)

    def test_netmask_of_128(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127/128')
        self.assertTrue(result is None)

    def test_netmask_of_zero(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127/0')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '::127/0' is not valid"),
            result
            )

    def test_netmask_too_large(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::127/129')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '::127/129' is not valid"),
            result
            )

    def test_address_empty(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'::')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '::' is not permitted"),
            result
            )

    def test_address_zeros(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'0:0:0:0:0:0:0:0/12')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '0:0:0:0:0:0:0:0/12' is not permitted"),
            result
            )

    def test_address_not_loopback(self):
        validator = IPv6AddressAndMaskValidator()
        result = validator.validate(u'0:0:0:0:0:0:0:1')
        self.assertEqual(
            ValidationError(error_message="IPv6 address '0:0:0:0:0:0:0:1' is not permitted"),
            result
            )

class TestNetworkValidator(unittest.TestCase):
    def setUp(self):
        self.validator = NetworkValidator()

    def test_subnet_ipv6(self):
        result = self.validator.validate("fdde:4d7e:d471::834:0:0/64")
        self.assertEqual(
            ValidationError(error_message="Invalid IPv4 subnet value "
                            "'fdde:4d7e:d471::834:0:0/64'"),
            result
            )

    def test_subnet_ipv6_exception(self):
        result = self.validator.validate(object())
        self.assertEqual(
            ValidationError(error_message="Invalid value: "
                            "unexpected type <type 'object'> for addr arg"),
            result
            )

    def test_subnet_no_prefix(self):
        expected = ValidationError(
                error_message='Subnet must include prefix length',
                )
        result = self.validator.validate("10.11.12.0")
        self.assertEqual(
                expected,
                result
            )

    def test_subnet_bad_prefix(self):
        expected = ValidationError(
                error_message = "Invalid prefix for destination IPv4 network at '10.11.12.0/33'"
                )
        result = self.validator.validate("10.11.12.0/33")
        self.assertEqual(
                expected,
                result
            )

        result = self.validator.validate("192.168./24")
        self.assertEqual(
            ValidationError(error_message="Invalid IPv4 subnet value "
                            "'192.168./24'"),
            result
            )

    def test_subnet_mcast(self):
        expected = None
        result = self.validator.validate("224.11.12.13/32")
        self.assertEqual(
                expected,
                result
            )

class TestNetworkValidatorV6(unittest.TestCase):
    def setUp(self):
        self.validator = NetworkValidatorV6()

    # IPv4 subnet disallowed..
    def test_subnet_ipv4(self):
        result = self.validator.validate("192.168.0.1/16")
        self.assertEqual(
            ValidationError(error_message="Invalid IPv6 subnet value "
                            "'192.168.0.1/16'"),
            result
            )

    def test_subnet_ipv6_exception(self):
        result = self.validator.validate(object())
        self.assertEqual(
            ValidationError(error_message="Invalid value: "
                            "unexpected type <type 'object'> for addr arg"),
            result
            )

    def test_subnet_no_prefix(self):
        expected = ValidationError(
                error_message='Subnet must include prefix length',
                )
        result = self.validator.validate("fdd3:2:3:4::")
        self.assertEqual(
                expected,
                result
            )

    def test_not_subnet_at_all(self):
        address = 'invalid_subnet'
        expected = ValidationError(
                error_message="Invalid IPv6 subnet value 'invalid_subnet'",
                )
        result = self.validator.validate(address)
        self.assertEqual(
                expected,
                result
            )

    def test_subnet_bad_prefix(self):
        address = 'fdde:2:3:4::0/129'
        expected = ValidationError(
                error_message="Invalid prefix for destination "
                "IPv6 network at 'fdde:2:3:4::0/129'",
                )
        result = self.validator.validate(address)
        self.assertEqual(
                expected,
                result
            )

    def test_subnet_mcast(self):
        expected = ValidationError(
                error_message="Subnet cannot be a multicast address",
                )
        result = self.validator.validate("ff00::1/128")
        self.assertEqual(
                expected,
                result
            )

    def test_subnet_reserved(self):
        result = self.validator.validate('::/128')
        self.assertEqual(
            ValidationError(error_message="Subnet cannot be a reserved network"),
            result
            )


class TestNotEmptyStringValidator(unittest.TestCase):
    def test_empty_string(self):
        validator = NotEmptyStringValidator()
        result = validator.validate("")
        self.assertEqual(
            ValidationError(
                error_message="Property cannot be empty"
                ),
            result
            )

    def test_nonempty_string(self):
        validator = NotEmptyStringValidator()
        result = validator.validate("foo")
        self.assertEqual(None,result)

    def test_nonetype(self):
        validator = NotEmptyStringValidator()
        result = validator.validate(None)
        self.assertEqual(None,result)


class TestMaxValueValidator(unittest.TestCase):
    def test_validate(self):
        validator = MaxValueValidator('limit_property_name', 'property_name')
        result = validator.validate({'property_name':51, 'limit_property_name':50})
        self.assertEqual(
            str(ValidationError(
                item_path='property_name',
                error_message="property_name value is greater"
                " than limit_property_name value"
                )),
            str(result)
            )
