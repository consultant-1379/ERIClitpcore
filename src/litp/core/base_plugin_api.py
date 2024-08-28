import ConfigParser
from litp.core.model_manager import QueryItem
from litp.core.exceptions import ModelManagerException
from litp.core.rpc_commands import run_rpc_command, run_rpc_application
from litp.encryption.encryption import EncryptionAES
import os
import base64
SECURITY_CONF_FILE_PATH = "/etc/litp_security.conf"
FILE_DEXIST_ERR = "{0} file does not exist".format(SECURITY_CONF_FILE_PATH)


class _SecurityApi(object):

    def __init__(self):
        self.aes = EncryptionAES()
        self.keyset = None
        self.password_file_path = None

    def _set_keyset_and_passwd(self):
        self.keyset, self.password_file_path = self._get_keyset_and_passwd()

    def _get_keyset_and_passwd(self):
        if not os.path.exists(SECURITY_CONF_FILE_PATH):
            raise os.error(FILE_DEXIST_ERR)
        parser = ConfigParser.SafeConfigParser()
        parser.read(SECURITY_CONF_FILE_PATH)
        return parser.get("keyset", "path"), parser.get("password", "path")

    def _create_keyset(self):
        if not self.keyset:
            self._set_keyset_and_passwd()
        if not self.aes.check_key(self.keyset):
            key = self.aes.generate_key()
            self.aes.write_key(self.keyset, key)

    def _decrypt(self, encrypted):
        key = self.aes.read_key(self.keyset)
        return self.aes.decrypt(key, encrypted)

    def get_password(self, service, user):
        """Return a password."""
        if not self.keyset:
            self._set_keyset_and_passwd()
        cp = ConfigParser.SafeConfigParser()
        cp.optionxform = str
        cp.read(self.password_file_path)

        b64_username = base64.standard_b64encode(user).replace('=', '')
        try:
            enc_password = cp.get(service, b64_username)
        except ConfigParser.NoOptionError:
            enc_password = cp.get(service, user)

        password = self._decrypt(enc_password)
        return password


class BasePluginApi(object):

    def __init__(self, model_manager):
        self._model_manager = model_manager
        self._security = _SecurityApi()

    def query_by_vpath(self, vpath):
        """
        Return a :class:`litp.core.model_manager.QueryItem` object that matches
        the specified vpath.

        If no :class:`litp.core.model_manager.QueryItem` is found, then None is
        returned.

        **Example Usage:**

            The following code will return a QueryItem if the vpath exists:

            .. code-block:: python

                item = self.api.query_by_vpath("/foo")

            Assuming the below vpath does not exist, None will be returned:

            .. code-block:: python

                no_item = self.api.query_by_vpath("is/not/there")

        :param vpath: :class:`litp.core.model_manager.ModelItem` vpath.
        :type  vpath: str

        :returns: :class:`litp.core.model_manager.QueryItem` found \
                based on the specified criteria.
        :rtype:   :class:`litp.core.model_manager.QueryItem` or None

        """
        try:
            model_item = self._model_manager.query_by_vpath(vpath)
            query_item = QueryItem(
                self._model_manager,
                model_item,
                updatable=True
            )
            return query_item
        except ModelManagerException:
            return None

    def query(self, item_type_id, **properties):
        """
        Return a list of :class:`litp.core.model_manager.QueryItem` objects
        that match specified criteria.

        Using a :class:`litp.core.model_manager.QueryItem` the plugin
        developer can update a :class:`litp.core.model_type.Property`
        of an item in the model if the property was defined with
        updatable_plugin=True argument.

        **Example Usage:**

            Given that the following item type is defined:

            .. code-block:: python

                ItemType("foobar",
                    name=Property("basic_string"),
                    time=Property("basic_string", updatable_plugin=True))

            The following code is valid:

            .. code-block:: python

                for item in api.query("foobar"):
                    item.time = "sometime"
                    # this would raise AttributeError:
                    # item.name = "some new name"

        :param item_type_id: Item type id of item to search for.
        :type  item_type_id: str
        :param   properties: Properties of the item to use as search criteria.
        :type    properties: dict

        :returns: list of :class:`litp.core.model_manager.QueryItem` found \
                based on the specified criteria.
        :rtype:   list
        """
        model_items = self._model_manager.query(item_type_id, **properties)
        query_items = []
        for model_item in model_items:
            query_item = QueryItem(
                self._model_manager,
                model_item,
                updatable=True
            )
            query_items.append(query_item)
        return query_items

    def get_password(self, service, user):
        """
        Return the password in clear for a particular service/user couple.

        :param service: identifier for the service instance, has to match \
            an item in LITP password storage
        :type service: string
        :param user: user associated with the password requested
        :type user: string
        :returns: Unencrypted password if credentials are valid else returns \
            None
        :rtype: string
        """
        try:
            return self._security.get_password(service, user)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return None

    def rpc_command(self, nodes, agent, action,
                    action_kwargs=None, timeout=None, retries=0):
        """
        Run an MCollective RPC command on the nodes.

        If the specified MCollective RPC agent is not installed on the
        management server, or if the specified action or any argument is not
        valid, no valid JSON output is generated by MCollective.
        Instead, the returned
        error message is logged and ValueError is raised.

        :param nodes: The hostnames of the nodes where the command will be run
        :type nodes: list of str
        :param agent: The MCollective agent to be used
        :type agent: str
        :param action: The MCollective agent action to be used
        :type action: str
        :param action_kwargs: Optional keyword arguments for the MCollective
                         agent action
        :type action_kwargs: dict
        :param timeout: Timeout in seconds (default is 60 seconds)
        :type timeout: int
        :param retries: Number of retries for nodes that do not return.
                        Only use this parameter if the RPC action is
                        idempotent.
        :type retries: int

        :returns: The results for all nodes as a dictionary.
        :rtype: dict

        **Example Output:**

            .. code-block:: python

                {
                    'node1': {
                        'errors': '',
                        'data': {
                            'status': 'running'
                        }
                    },
                    'node3': {
                        'errors': 'No answer from node',
                        'data': {},
                    },
                    'node2': {
                        'errors': '',
                        'data': {
                            'status': 'running'
                        }
                    }
                }
        """
        return run_rpc_command(
                  nodes, agent, action, action_kwargs, timeout, retries)

    def rpc_application(self, nodes, app_args):
        """
        Run an MCollective RPC application on the nodes.

        Most of the times these applications are used to control a service or
        Puppet.

        :param nodes: The hostnames of the nodes where the command will be run
        :type nodes: list of str
        :param app_args: List of arguments to call the MCollective application
        :type agent: list of str

        :returns: The exit code of the mco command.
        :rtype: int
        """
        return run_rpc_application(nodes, app_args)
