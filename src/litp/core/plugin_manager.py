##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


import imp
import os
import sys

from ConfigParser import ConfigParser, Error
from litp.core.base_manager import BaseManager
from litp.core.plugin import Plugin
from litp.core.extension import ModelExtension
from litp.core.topsort import topsort

from litp.core.event_emitter import EventEmitter
from litp.core.litp_logging import LitpLogger
from litp.core.exceptions import DuplicatedItemTypeException
from litp.core.exceptions import DuplicatedPropertyTypeException
from litp.core.exceptions import RegistryException
from litp.enable_metrics import apply_metrics

log = LitpLogger()


class _DaemonAwareLogger(object):

    def __init__(self, *args, **kwargs):
        self._is_daemon = False
        if 'daemon' in kwargs:
            self._is_daemon = kwargs['daemon']

    def _log(self, *args):
        if self._is_daemon:
            log.trace.info(*args)
        else:
            log.trace.debug(*args)


class _Registry(_DaemonAwareLogger):
    """
    Register and store plugins and extensions
    """
    def __init__(self, descriptive_name, daemon=False):
        super(_Registry, self).__init__(daemon=daemon)
        self.descriptive_name = descriptive_name
        self._by_name = {}
        self._by_class = {}  # actually by qualname of class, not class object.

    def check(self, name, klass):
        """
        Determine whether class has already been registered as a \
        plugin or extension.
        :param str name: Name of the plugin or extension registering \
            the class specified by klass (actually qualified name)
        :param str klass: The qualified name of class to be instantiated by \
            the specfied plugin name
        """
        if name in self._by_name:
            raise RegistryException(
                "{0} called {1} is already defined".format(
                    self.descriptive_name, name))
        if klass in self._by_class:
            raise RegistryException(
                ("{0} called {1} already uses class {2} "
                 "which clashes with {0} {3}").format(
                    self.descriptive_name,
                    self._by_class[klass]['name'],
                    klass,
                    name))

    def _add(self, name, klass, version, cls):
        # for historical reasons, the qualified class name is designated
        # 'class'/klass here. cls is the corresponding actual class object.
        val = {
            'name': name,
            'class': klass,
            'version': version,
            'cls': cls
        }

        self._by_name[name] = val
        self._by_class[klass] = val

        # This should be debug except on startup (I think...)
        self._log('Added %s: "%s" using class "%s"' %
            (self.descriptive_name, name, klass))

    def check_then_add(self, name, klass, version, cls):
        self.check(name, klass)
        self._add(name, klass, version, cls)

    def iter_items(self):
        for item in self._by_name.values():
            yield item['name'], item['cls']

    def get_items(self, keys=None):
        """
        Return a list of registered items

        :param keys: List of keys to include when building item list
        :type keys: list
        """
        if keys is None:
            keys = ['name', 'class', 'version', 'cls']
        items = []
        for entry in self._by_name.values():
            item = {}
            for key in keys:
                item[key] = entry[key]
            items.append(item)
        return items


class PluginManagerNextGen(EventEmitter, BaseManager, _DaemonAwareLogger):
    """
    Manage the loading and registering of plugin and extension items
    """
    def __init__(self, model_manager, daemon=False):
        super(PluginManagerNextGen, self).__init__()
        self.model_manager = model_manager
        self._plugins = _Registry('Plugin', daemon=daemon)
        self._extensions = _Registry('ModelExtension', daemon=daemon)
        self._is_daemon = daemon
        apply_metrics(self)

    def get_plugin(self, plugin_class):
        if plugin_class not in self._plugins._by_class:
            return None
        plugin = self._plugins._by_class[plugin_class]['cls']()
        self.emit(
            'plugin_added',
            self._plugins._by_class[plugin_class]['name'],
            plugin)
        return plugin

    def iter_plugins(self):
        for name, cls in self._plugins.iter_items():
            plugin = cls()
            self.emit('plugin_added', name, plugin)
            yield (name, plugin)

    def get_plugin_info(self):
        keys = ['name', 'class', 'version']
        return self._plugins.get_items(keys)

    def get_plugins(self):
        return self._plugins.get_items(None)

    def get_extension_info(self):
        keys = ['name', 'class', 'version']
        return self._extensions.get_items(keys)

    def add_plugin(self, name, klass, version, plugin):
        # API used to be to take an _instance_ of plugin to be reused
        # while this is notionally internal/undocumented, a bunch of unit
        # tests across litp plugins use it. For legacy compat, accept it
        # for now.
        cls = plugin.__class__
        self.add_plugin_class(name, klass, version, cls)

    def add_plugin_class(self, name, klass, version, cls):
        self._plugins.check_then_add(name, klass, version, cls)
        # Continue to support an ancient and maybe unused API variant where
        # plugins (not extensions) can register item and property types.
        plugin = cls()
        self.model_manager.register_property_types(
            plugin.register_property_types())
        self.model_manager.register_item_types(plugin.register_item_types())

    def _reload(self, module_name):
        # reload, in separate method to facilitate atrunner mocking
        reload(module_name)

    def _find_class(self, classpath, check_subclass=None):
        """ Try to find a class specified in classpath

        :param classpath: Class to be found, ie. 'path.to.module.ClassName'
        :type classpath: str.

        :returns: class object for the class specified in classpath.
        :raises: ImportError, AttributeError
        """
        path_list = classpath.split('.')
        classname = path_list[-1]
        modulename = ".".join(path_list[:-1])

        if modulename:
            try:
                if modulename in sys.modules:
                    # We want to cover the case where modulename is already
                    # loaded, but from a different file than the one we want
                    loaded_module = os.path.splitext(
                        sys.modules[modulename].__file__
                    )[0]
                    reload_info = None
                    try:
                        reload_info = imp.find_module(modulename)
                    except ImportError:
                        pass
                    else:
                        module_on_reload = os.path.splitext(reload_info[1])[0]
                        if loaded_module != module_on_reload:
                            self._reload(sys.modules[modulename])
                    finally:
                        if reload_info is not None:
                            reload_info[0].close()
                else:
                    module = __import__(modulename, fromlist=[classname])
            except ImportError:
                log.trace.error(
                    'Exception while importing module %s' % modulename)
                raise

            try:
                module = sys.modules[modulename]
                klass = getattr(module, classname)
            except AttributeError:
                log.trace.error('Exception while importing class %s' %
                                classname)
                raise

            if issubclass(klass, check_subclass):
                return klass
        return None

    def _find_plugin_class(self, classpath):
        return self._find_class(classpath, check_subclass=Plugin)

    def _find_extension_class(self, classpath):
        return self._find_class(classpath, check_subclass=ModelExtension)

    def add_plugins(self, plugin_conf_dir):
        r""" Get list of plugins from \*.conf files and import them.

        :param plugin_conf_dir: Where \*.conf files are located.
        :type plugin_conf_dir: str

        :returns: None
        :raises: NoSectionError
        """
        for plugin_name, plugin_classpath, plugin_version in \
                            set(self.read_plugin_config(plugin_conf_dir)):
            plugin_class = self._find_plugin_class(plugin_classpath)
            if plugin_class is not None:
                self.add_plugin_class(plugin_name, plugin_classpath,
                                plugin_version, plugin_class)
                self._log('Added plugin: "%s"' % (plugin_name))
            else:
                log.trace.warning('Plugin not added: "%s"' % (plugin_name))

    def add_default_model(self):
        """
        Create the core root items in the model
        """
        self.model_manager.create_core_root_items()

    def add_item_types(self, item_types):
        """
        Add item types to the model
        :param item_types: List of ItemType objects to be added
        :type item_types: litp.core.model_type.ItemType
        """
        self._log("Adding item types.")
        self.model_manager.register_item_types(item_types)

    def add_property_types(self, property_types):
        """
        Add property types to the model
        :param item_types: List of PropertyType objects to be added
        :type item_types: litp.core.model_type.PropertyType
        """
        self._log("Adding property types.")
        self.model_manager.register_property_types(property_types)

    def read_ext_config(self, config_dir):
        """
        Read extensions config files located at the specified directory
        :param str config_dir: Directory to read configuration files from
        """
        return self.read_config_files(config_dir, config_type="extension")

    def read_plugin_config(self, config_dir):
        """
        Read plugin config files located at the specified directory
        :param str config_dir: Directory to read configuration files from
        """
        return self.read_config_files(config_dir, config_type="plugin")

    def read_config_files(self, config_dir, config_type):
        """Generator, yields a name and a classpath

        param config_dir: str, where config files are located
        param config_type: str, is 'extension' or 'plugin' config
        raises: config parser error
        """
        for config_file in os.listdir(config_dir):
            if config_file.endswith(".conf"):
                config = ConfigParser()
                config.read(os.path.join(config_dir, config_file))
                try:
                    name = config.get(config_type, "name")
                    classpath = config.get(config_type, "class")
                    version = config.get(config_type, "version")
                    yield (name, classpath, version)
                except Error as e:
                    log.trace.error("Error while parsing "
                                    "config file {0}".format(e))
                    raise

    def ensure_unique_properties(self, ext_name, property_types_by_id,
                                 extension_property_types):
        """
        :param ext_name: The name of the extension registering property \
            types
        :type node: basicstring

        :param property_types_by_id: The list of already registered property \
            types
        :type property_types_by_id: list

        :param extension_property_types: The list of property types \
            registered by this extension
        :type extension_property_types: list
        """
        for ept in extension_property_types:
            if ept.property_type_id in property_types_by_id:
                msg = ('PropertyType "{0}" defined by extension "{1}" '
                       'clashes with that defined by "{2}"'.format(
                           ept.property_type_id,
                           property_types_by_id[ept.property_type_id][1],
                           ext_name))
                log.trace.error(msg)
                raise DuplicatedPropertyTypeException(msg)
            else:
                property_types_by_id[ept.property_type_id] = (ept, ext_name)
                log.trace.debug("Property type {0} added.".format(
                    ept.property_type_id))

    def ensure_unique_item_types(self, ext_name, item_types_by_id,
                                 extension_item_types):
        """
        Check for uniqueness for this extension name among registered \
            item types
        :param ext_name: The name of the extension registering types
        :type node: basicstring

        :param item_types_by_id: The list of already registered item types
        :type item_types_by_id: list

        :param extension_item_types: The list of item_types registered \
            by this extension
        :type extension_item_types: list
        """
        for eit in extension_item_types:
            if eit.item_type_id in item_types_by_id:
                msg = ('ItemType "{0}" defined by extension "{1}" '
                       'clashes with that defined by "{2}"'.format(
                       eit.item_type_id, item_types_by_id[eit.item_type_id][1],
                       ext_name))
                log.trace.error(msg)
                raise DuplicatedItemTypeException(msg)
            else:
                item_types_by_id[eit.item_type_id] = (eit, ext_name)
                log.trace.debug("Item type {0} added.".format(
                    eit.item_type_id))

    def get_sorted_item_types(self, item_types_by_id):
        """
        Returns a list of topologically sorted item types.

        :param item_types_by_id: The list of item types to topologically sort
        :type item_types_by_id: list
        """
        item_types = {}
        item_types_mapping = {}
        for entry in item_types_by_id.values():
            item_type, _ = entry
            item_types_mapping[item_type.item_type_id] = item_type
            if not item_type.extend_item:
                item_types[item_type.item_type_id] = set([])
            else:
                item_types[item_type.item_type_id] = \
                        set([item_type.extend_item])

        sorted_item_types = []
        for item_list in topsort(item_types):
            for item in item_list:
                sorted_item_types.append(item)
        return [item_types_mapping[it] for it in sorted_item_types if \
            it in item_types_mapping]

    def add_extensions(self, ext_conf_dir):
        """Get a list of extensions and import them.

        param ext_conf_dir: str, where are extensions files located
        returns None

        """
        item_types_by_id = {}
        property_types_by_id = {}

        for ext_name, ext_classpath, ext_version in \
                                    self.read_ext_config(ext_conf_dir):
            extension_class = self._find_extension_class(ext_classpath)
            extension = extension_class()
            if extension is not None:
                self._extensions.check_then_add(ext_name, ext_classpath,
                                                ext_version, extension_class)
                ei_types = extension.define_item_types()
                self.ensure_unique_item_types(ext_name, item_types_by_id,
                                              ei_types)

                ep_types = extension.define_property_types()
                self.ensure_unique_properties(ext_name, property_types_by_id,
                                              ep_types)
            else:
                log.trace.warning('Extension not added: "{0}"'.format(
                    ext_name))

        item_types = self.get_sorted_item_types(item_types_by_id)
        self.add_property_types(
            ept[0] for ept in property_types_by_id.values())
        self.add_item_types(item_types)


class PluginManager(PluginManagerNextGen):
    def __init__(self, model_manager, *args, **kwargs):
        super(PluginManager, self).__init__(model_manager, *args, **kwargs)
        self.data_manager = model_manager.data_manager
