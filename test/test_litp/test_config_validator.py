import unittest
import copy
import cherrypy
import contextlib


from litp.core.config_validator import ConfigValidator, _OptionValidator

@contextlib.contextmanager
def cleaned_config(option_name):
    try:
        yield
    finally:
        try:
            del cherrypy.config[option_name]
        except KeyError:
            pass


def option_a(value=None):
    if value is not None:
        option = value
    else:
        option = cherrypy.config.get('option_a')
    if option != 'test_value_a':
        return 'Expected value: "test_value_a"'
    return None


def option_b(value=None):
    if value is not None:
        option = value
    else:
        option = cherrypy.config.get('option_b')
    if option != 'test_value_b':
        return 'Expected value: "test_value_b"'
    return None


class TestConfigValidator(unittest.TestCase):
    def setUp(self):
        self._validator = ConfigValidator()
        del self._validator._options_to_validate[:]

    def tearDown(self):
        for option in ['option_a', 'option_b']:
            try:
                delattr(self._validator._option_validator, option)
            except AttributeError:
                pass

    def test_validate_option_valid_value_specified_no_validation_method(self):
        cherrypy.config.update({'option_a': 'test_value_a'})
        self.assertEqual(None,
                self._validator.validate_option('option_a',
                    'test_value_a'))

    def test_validate_option_invalid_value_specified_no_validation_method(self):
        cherrypy.config.update({'option_a': 'option_a'})
        self.assertEqual(None,
                self._validator.validate_option('option_a', 'unexpected_value'))

    def test_validate_option_valid_value_specified_validation_method(self):
        cherrypy.config.update({'option_a': 'test_value_a'})
        self._validator._option_validator.option_a = option_a
        self.assertEqual(None,
                self._validator.validate_option('option_a', 'test_value_a'))

    def test_validate_option_invalid_value_specified_validation_method(self):
        cherrypy.config.update({'option_a': 'test_value_a'})
        self._validator._option_validator.option_a = option_a
        self.assertEqual('Expected value: "test_value_a"',
                self._validator.validate_option('option_a', 'unexpected_value'))

    def test_validate_option_valid_value_in_config_no_validation_method(self):
        cherrypy.config.update({'option_a': 'test_value_a'})
        self.assertEqual(None,
                self._validator.validate_option('option_a'))

    def test_validate_option_invalid_value_in_config_no_validation_method(self):
        cherrypy.config.update({'option_a': 'unexpected_value'})
        self.assertEqual(None,
                self._validator.validate_option('option_a'))

    def test_validate_option_valid_value_in_config_validation_method(self):
        cherrypy.config.update({'option_a': 'test_value_a'})
        self._validator._option_validator.option_a = option_a
        self.assertEqual(None,
                self._validator.validate_option('option_a'))

    def test_validate_option_invalid_value_in_config_validation_method(self):
        cherrypy.config.update({'option_a': 'unexpected_value'})
        self._validator._option_validator.option_a = option_a
        self.assertEqual('Expected value: "test_value_a"',
                self._validator.validate_option('option_a'))

    def test_validate_no_options_to_validate(self):
        self.assertEqual([], self._validator.validate())

    def test_validate_one_options_to_validate(self):
        self._validator._options_to_validate.append('option_a')
        self.assertEqual([], self._validator.validate())

        # No method to validate yet in _OptionValidator
        cherrypy.config.update({'option_a': 'unexpected_value'})
        self.assertEqual([], self._validator.validate())

        # Validation method added to _OptionValidator
        cherrypy.config.update({'option_a': 'unexpected_value'})
        self._validator._option_validator.option_a = option_a
        self.assertEqual(['Expected value: "test_value_a"'],
                self._validator.validate())

    def test_validate_multiple_options_to_validate(self):
        self._validator._options_to_validate.append('option_a')
        self._validator._options_to_validate.append('option_b')
        self.assertEqual([], self._validator.validate())

        # No method to validate yet in _OptionValidator
        cherrypy.config.update({'option_a': 'unexpected_value'})
        cherrypy.config.update({'option_b': 'unexpected_value'})
        self.assertEqual([], self._validator.validate())

        # Only on validation method added to _OptionValidator
        cherrypy.config.update({'option_a': 'unexpected_value'})
        cherrypy.config.update({'option_b': 'unexpected_value'})
        self._validator._option_validator.option_a = option_a
        self.assertEqual(['Expected value: "test_value_a"'],
                self._validator.validate())

        # Two validation method added to _OptionValidator
        cherrypy.config.update({'option_a': 'unexpected_value'})
        cherrypy.config.update({'option_b': 'unexpected_value'})
        self._validator._option_validator.option_a = option_a
        self._validator._option_validator.option_b = option_b
        self.assertEqual(
                sorted(['Expected value: "test_value_a"',
                          'Expected value: "test_value_b"']),
                sorted(self._validator.validate()))


class Test_OptionValidator(unittest.TestCase):
    """ Test all your validation methods here.  """

    def setUp(self):
        self._saved_config = copy.copy(cherrypy.config)
        self._validator = _OptionValidator()

    def tearDown(self):
        cherrypy.config.clear()
        cherrypy.config.update(self._saved_config)

    def _check_values(self, option_name, values, with_arg=False,
                        test_invalid=False, err_msg=None):
        for value in values:
            with cleaned_config(option_name):
                if test_invalid and with_arg:
                    self.assertEquals(err_msg,
                            getattr(self._validator, option_name)(value))
                elif test_invalid and not with_arg:
                    cherrypy.config.update({option_name: value})
                    self.assertEquals(err_msg,
                            getattr(self._validator, option_name)())
                elif not test_invalid and with_arg:
                    self.assertEquals(None,
                            getattr(self._validator, option_name)(value))
                elif not test_invalid and not with_arg:
                    cherrypy.config.update({option_name: value})
                    self.assertEquals(None,
                            getattr(self._validator, option_name)())
                else:
                    raise Exception('Not a valid test!')

    def _check_valid_values_with_arg(self, option_name, values):
        self._check_values(option_name, values, with_arg=True,
                            test_invalid=False, err_msg=None)

    def _check_invalid_values_with_arg(self, option_name, values, err_msg):
        self._check_values(option_name, values, with_arg=True,
                            test_invalid=True, err_msg=err_msg)

    def _check_valid_values_from_config(self, option_name, values):
        self._check_values(option_name, values, with_arg=False,
                            test_invalid=False, err_msg=None)

    def _check_invalid_values_from_config(self, option_name, values, err_msg):
        self._check_values(option_name, values, with_arg=False,
                            test_invalid=True, err_msg=err_msg)

    def _check_option(self, option, valid_values, invalid_values, err_msg):
        self._check_valid_values_with_arg(option, valid_values)
        self._check_valid_values_from_config(option, valid_values)
        self._check_invalid_values_with_arg(option, invalid_values, err_msg)
        self._check_invalid_values_from_config(option, invalid_values, err_msg)

    def test_puppet_phase_timeout(self):
        option = "puppet_phase_timeout"
        week = 604800
        minimum = 0
        maximum = week
        valid_values = [-0.9, 0, 43200, week, week / 2, 10.2]
        invalid_values = [None, week + 1, -1, 'not_a_number', '10.2']
        err_msg = ('Incorrect "{0}" value specified in '
                    '/etc/litpd.conf. Valid "puppet_phase_timeout" value is '
                    'an integer within a range [{1}, {2}]'.format(
                        option, minimum, maximum))

        self._check_option(option, valid_values, invalid_values, err_msg)

    def test_puppet_poll_frequency(self):
        option = "puppet_poll_frequency"
        minute = 60
        hour = 3600
        valid_values = [-0.9, 0, 0.9, minute, hour, hour / 2]
        invalid_values = [None, -1, 1, hour + 1, minute - 1,  'not_a_number',
                            '60.2']

        err_msg = ("Incorrect \"{0}\" value specified in /etc/litpd.conf. "
                "Valid \"{0}\" value is an integer: 0 or [{1}, {2}]".format(
                    option,  minute, hour))

        self._check_option(option, valid_values, invalid_values, err_msg)

    def test_puppet_poll_count(self):
        option = "puppet_poll_count"
        minimum = 1
        maximum = 1000
        valid_values = [minimum, 60, maximum, 10.2]
        invalid_values = [None, -1, minimum - 1, maximum + 1, 'not_a_number',
                            '10.2']
        err_msg = ("Incorrect \"{0}\" value specified in /etc/litpd.conf. "
                    "Valid \"{0}\" value is an integer within a range "
                    "[{1}, {2}]".format(option, minimum, maximum))

        self._check_option(option, valid_values, invalid_values, err_msg)
