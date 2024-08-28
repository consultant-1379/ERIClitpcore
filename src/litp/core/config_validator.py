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
import os.path


class ConfigValidator(object):
    """ Validator for options specified in /etc/litpd.conf file. """

    def __init__(self):
        """
        All options that are going to be validated on `self.validate()` call
        have to be listed in `self._options_to_validate`.
        Concrete validation functions are the methods of
        `self._option_validator`

        """
        self._option_validator = _OptionValidator()
        self._options_to_validate = ["puppet_phase_timeout",
                                    "puppet_poll_frequency",
                                    "puppet_poll_count",
                                    "puppet_mco_timeout",
                                    "task_graph_save_location"]

    def validate_option(self, option, value=None):
        """
        Validate a specified option of a config file.
        Return an error string as returned from a validation function or None
        if no error. If value is specified, the validation function should
        validate it, rather than the one from config file.

        :param option: Name of an option to validate.
        :type option: str
        :param value: Value of an option to validate.
        :type value: any valid type for a specified option

        :rtype str or None

        """
        if hasattr(self._option_validator, option):
            validation_function = getattr(self._option_validator, option)
            return validation_function(value)
        return None

    def validate(self):
        """
        Validate all options specified in `self._options_to_validate`.
        Return a list of errors as returned from a validation functions.

        :rtype list

        """
        errors = []
        for option in self._options_to_validate:
            error = self.validate_option(option)
            if error:
                errors.append(error)
        return errors


class _OptionValidator(object):
    """
    This class contains actual validation methods for options from
    /etc/litpd.conf config file.

    Each method in this class has to be named _exactly_ the same as the option
    it validates. For instance if the option to validate is
    "puppet_phase_timeout", the method has to be declared as follows:

    def puppet_phase_timeout(self, value=None):
        ...

    Each validation method MUST return either an error string or None if no
    error is found.

    Each validation method takes an optional `value` argument. If `value`
    argument is specified, the validation method should validate the option
    against that value rather than a value taken from `cherrypy.config`.

    Use cherrypy.config to access the options at this stage, to avoid
    validation calls in `litp.core.config`.

    """
    def puppet_phase_timeout(self, value=None):
        option_name = 'puppet_phase_timeout'
        minimum = 0         # no timeout
        maximum = 604800    # week
        return self._validate_min_max(option_name, minimum, maximum, value)

    def puppet_poll_frequency(self, value=None):
        option = 'puppet_poll_frequency'
        minute = 60
        hour = 3600
        msg = ("Incorrect \"{0}\" value specified in /etc/litpd.conf. "
                "Valid \"{0}\" value is an integer: 0 or [{1}, {2}]".format(
                    option,  minute, hour))
        try:
            if value is not None:
                timeout = int(value)
            else:
                timeout = int(cherrypy.config.get(option))
            if (not minute <= timeout <= hour) and (timeout != 0):
                raise ValueError
        except (ValueError, TypeError):
            return msg
        return None

    def puppet_poll_count(self, value=None):
        option_name = 'puppet_poll_count'
        minimum = 1
        maximum = 1000
        return self._validate_min_max(option_name, minimum, maximum, value)

    def puppet_mco_timeout(self, value=None):
        option_name = "puppet_mco_timeout"
        minimum = 300
        maximum = 900
        return self._validate_min_max(option_name, minimum, maximum, value)

    def task_graph_save_location(self, value=None):
        option_name = "task_graph_save_location"
        save_location = cherrypy.config.get(option_name)
        if not save_location:
            return None
        if not save_location.startswith('/'):
            msg = ("Incorrect \"{0}\" value specified"
                   " in /etc/litpd.conf. Value should be"
                   " an absolute path.".format(option_name))
            return msg

        if (not os.path.isdir(save_location) and
               os.access(save_location.os.W_OK)):
            msg = ("Incorrect \"{0}\" value specified"
                   " in /etc/litpd.conf. Value should be"
                   " an existing and writeable path.".format(option_name))
            return msg
        return None

    def _validate_min_max(self, option_name, minimum, maximum, value):
        try:
            if value is not None:
                timeout = int(value)
            else:
                timeout = int(cherrypy.config.get(option_name))
            if not minimum <= timeout <= maximum:
                raise ValueError
        except (ValueError, TypeError):
            msg = ("Incorrect \"{0}\" value specified in /etc/litpd.conf. "
                    "Valid \"{0}\" value is an integer within a range "
                    "[{1}, {2}]".format(option_name, minimum, maximum))
            return msg
        return None
