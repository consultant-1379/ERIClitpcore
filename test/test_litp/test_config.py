import unittest
import copy
import cherrypy

from litp.core.config import config
from litp.core.config_validator import _OptionValidator
from litp.core.exceptions import ConfigValueError


def option_a(value=None):
    if value is not None:
        option = value
    else:
        option = cherrypy.config.get('option_a')
    if option != 'test_value':
        return 'Expected value: "test_value"'
    return None


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._old_values = copy.copy(config)
        config.update({'option_a': 'test_value'})

    def tearDown(self):
        config.clear()
        config.update(self._old_values)

        try:
            delattr(config._validator._option_validator, 'option_a')
        except AttributeError:
            pass

    def test_update_if_no_value_in_config(self):
        self.assertFalse('tmp_option' in config)
        config.update({'tmp_option': 'tmp_value'})
        self.assertTrue('tmp_option' in config)

    def test_update_if_value_in_config(self):
        self.assertEquals('test_value', config['option_a'])
        config.update({'option_a': 'tmp_value'})
        self.assertEquals('tmp_value', config['option_a'])

    def test_config_is_the_same_as_cherrypy_config(self):
        self.assertEquals(dict(eval(repr(config))),
                          dict(eval(repr(cherrypy.config))))
        for option in cherrypy.config:
            self.assertEquals(cherrypy.config[option], config[option])

    def test_setitem(self):
        config['option_a'] = 'value'
        self.assertEquals('value', config['option_a'])

    def test_getitem(self):
        self.assertEquals('test_value', config['option_a'])
        self.assertRaises(KeyError, lambda: config['nonexistent_option'])

    def test_get(self):
        self.assertEquals('test_value', config['option_a'])
        self.assertEquals(None, config.get('nonexistent'))
        self.assertEquals([1, 2, 3], config.get('nonexistent', [1, 2, 3]))

    def test_validate_on_setitem_valid_value(self):
        config._validator._option_validator.option_a = option_a
        self.assertEquals('test_value', config['option_a'])
        config['option_a'] = 'test_value'
        self.assertEquals('test_value', config['option_a'])

    def test_validate_on_setitem_invalid_value(self):
        def _setitem(key, value):
            config[key] = value
        config._validator._option_validator.option_a = option_a
        self.assertEquals('test_value', config['option_a'])
        self.assertRaises(ConfigValueError, _setitem, 'option_a', 'different_than_test_value')

    def test_validate_on_update(self):
        config._validator._option_validator.option_a = option_a
        self.assertEquals('test_value', config['option_a'])
        self.assertRaises(ConfigValueError,
            config.update, {'option_a': 'different_than_test_value'})

    def test_validate_on_getitem(self):
        config._validator._option_validator.option_a = option_a
        self.assertEquals('test_value', config['option_a'])
        cherrypy.config.update({'option_a': 'different_than_test_value'})
        self.assertRaises(ConfigValueError, lambda: config['option_a'])

    def test_validate_on_get(self):
        config._validator._option_validator.option_a = option_a
        self.assertEquals('test_value', config.get('option_a'))
        cherrypy.config.update({'option_a': 'different_than_test_value'})
        self.assertRaises(ConfigValueError, lambda: config.get('option_a'))

        # Make sure that ConfigValueError is raised on invalid default value
        cherrypy.config.update({'option_a': 'test_value'})
        self.assertRaises(ConfigValueError,
                lambda: config.get('option_a', 'different_than_test_value'))

    def test_get_puppet_phase_timeout(self):
        week = 604800
        def update_puppet_phase_timeout(value):
            config._config.update({"puppet_phase_timeout": value})

        for value in [0, week, week / 2, 10.2]:
            update_puppet_phase_timeout(value)
            self.assertEquals(value, config['puppet_phase_timeout'])

        for value in [None, week + 1, -1, 'not_a_number', '10.2']:
            update_puppet_phase_timeout(value)
            self.assertRaises(ConfigValueError,
                    lambda: config['puppet_phase_timeout'])

    def test_items(self):
        for key, value in config.items():
            self.assertEquals(value, config[key])
            self.assertEquals(value, cherrypy.config[key])

    def test_iteritems(self):
        for key, value in config.iteritems():
            self.assertEquals(value, config[key])
            self.assertEquals(value, cherrypy.config[key])
