##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import cherrypy
import copy
from litp.core.config_validator import ConfigValidator
from litp.core.exceptions import ConfigValueError


class Config(object):
    """ Proxy `cherrypy.config` so that it's more intuitive to the user.
    Every data put or retrieval goes along with an on-the-fly validation.
    Validation methods are specified in
    `litp.core.config_validator._OptionValidator`.

    Usage:
        Importing:
            from litp.core.config import config

        Getting an option's value:
            value = config['option_name']
            value = config.get('option_name')

        Updating the value of an option:
            config.update({'option_name': 'new_value'})
            config['option_name'] = 'new_value'

    """
    def __init__(self):
        self._config = cherrypy.config
        self._validator = ConfigValidator()

    def update(self, *args, **kwargs):
        options = {}
        options.update(args[0])
        options.update(kwargs)
        for option_name, value in options.iteritems():
            self._validate_option(option_name, value)
        self._config.update(*args, **kwargs)

    def clear(self):
        self._config.clear()

    def items(self):
        return self._config.items()

    def iteritems(self):
        for key, value in self._config.iteritems():
            yield key, value

    def __copy__(self):
        return copy.copy(self._config)

    def __deepcopy__(self, memo):
        return copy.deepcopy(self._config, memo)

    def _validate_option(self, option_name, value=None):
        error = self._validator.validate_option(option_name, value)
        if error:
            raise ConfigValueError(error)

    def _getitem(self, key):
        option_name = key
        value = self._config.__getitem__(key)
        self._validate_option(option_name, value)
        return value

    def get(self, key, default=None):
        option_name = key
        self._validate_option(option_name, default)
        return self._config.get(option_name, default)

    def __setitem__(self, key, value):
        self._validate_option(key, value)
        self._config.__setitem__(key, value)

    def __getitem__(self, key):
        return self._getitem(key)

    def __repr__(self):
        return self._config.__repr__()

    def __contains__(self, item):
        return self._config.__contains__(item)


config = Config()
