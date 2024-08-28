##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.base_plugin_api import BasePluginApi


class CallbackApi(BasePluginApi):

    """Represents Callback API."""

    def __init__(self, execution_manager):
        self.execution_manager = execution_manager
        super(CallbackApi, self).__init__(
                model_manager=execution_manager.model_manager)

    def initialize(self):
        """Initialize callback api."""
        self._security._create_keyset()

    #to be used when the password is used in a shell.
    def get_escaped_password(self, service, user):
        """
        Return the password in clear for a particular service/user couple,
        with all special character escaped. This method is needed when the
        password is used in a shell (e.g. in a command executed with a
        subprocess.Popen)

        :param service: identifier for the service instance, has to match \
            an item in LITP password storage
        :type service: string
        :param user: user associated with the password requested
        :type user: string
        :returns: Unencrypted password if credentials are valid else returns \
            None
        :rtype: string
        """
        password = self.get_password(service, user)
        if password:
            return '{pwd}'.format(pwd=self.sanitize(password))

    def sanitize(self, raw_string):
        """
        Sanitizes a string by inserting escape characters to make it
        shell-safe.

        :param raw_string: The string to sanitise
        :type raw_string: string

        :returns: The escaped string
        :rtype: string
        """
        spec_chars = '''"`$'(\\)!~#<>&*;| '''
        escaped = ''.join([c if c not in spec_chars else '\\' + c
                           for c in raw_string])
        return escaped

    def is_running(self):
        """
        Determine if a plan is currently running.

        The plugin developer must check regularly (every 1-2 seconds) if the
        plan has been stopped so that the callback function can finish its
        job. This is very important for long running callback functions.

        :returns: Whether the plan is currently running
        :rtype: bool
        """

        self.execution_manager.forget_cached_plan()
        return self.execution_manager.is_plan_running()
