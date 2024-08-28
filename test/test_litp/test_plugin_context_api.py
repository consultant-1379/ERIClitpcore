import unittest
from time import time
from mock import MagicMock, patch

from litp.core.model_manager import ModelManager, QueryItem
from litp.core.model_item import ModelItem
from litp.core.constants import UPGRADE_SNAPSHOT_NAME
from litp.core.plugin_context_api import PluginApiContext
from litp.core.model_type import Child, ItemType, Property, PropertyType, \
    Reference, Collection, RefCollection
from litp.core.exceptions import NoMatchingActionError, NoSnapshotItemError
from litp.core.snapshot_model_api import SnapshotModelApi


class PluginApiContextTest(unittest.TestCase):
    def setUp(self):
        self.model_manager = ModelManager()
        self.plugin_api_context = PluginApiContext(self.model_manager)
        self.model_manager.register_property_type(PropertyType("basic_string"))
        self.model_manager.register_property_type(PropertyType("basic_boolean", regex=r"^(true|false)$"))
        self.model_manager.register_item_type(
            ItemType("root",
                     my_child=Child("child"),
                     my_dependant=Child("dependant"),
                     snapshots=Collection("snapshot-base", max_count=1),
                     name=Property("basic_string")
                     ))
        self.model_manager.register_item_type(
            ItemType("child",
                     dependant_ref=Reference("dependant"),
                     name=Property("basic_string", required=True)
                     )
        )
        self.model_manager.register_item_type(
            ItemType("dependant",
                     name=Property("basic_string", required=True)
                     )
        )
        self.model_manager.register_item_type(ItemType("snapshot-base",
                timestamp=Property('basic_string'),
                active=Property('basic_boolean',
                            required=False,
                            updatable_rest=False,
                            default='true'),
                force=Property('basic_boolean',
                            required=False,
                            updatable_rest=False,
                            default='false')))

        self.model_manager.create_root_item("root")
        self.model_manager.create_item("child", "/my_child",
                                       name="test")

    def _set_all_applied(self, model):
        """Copy this here, as it will be one day removed!"""
        for item in model.query_model():
            if not item.is_applied():
                item.set_applied()

    def _assertRaisesCustom(self, exception, message, callable, *args, **kwargs):
        try:
            callable(*args, **kwargs)
        except exception as e:
            if (str(e) != message):
                raise AssertionError("{0} != {1}".format(message, str(e)))
        else:
            raise AssertionError('No exception was raised')

    def _simple_model(self, applied=True):
        model = ModelManager()
        plugin_api = PluginApiContext(model)
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            source=Child("item"),
        ))
        model.register_item_type(ItemType(
            "container",
            refs=RefCollection("item"),
            refs2=RefCollection("item"),
        ))
        model.register_item_type(ItemType(
            "item",
            name=Property("basic_string",
                updatable_plugin=True),
            not_overwritten=Property("basic_string",
                updatable_plugin=True),
            overwritten=Property("basic_string",
                updatable_plugin=True,
                default='default_bar'),
        ))
        model.create_root_item("root")
        model.create_item("container", "/container")
        model.create_item("item", "/source", name="original_name",
                not_overwritten="original_foo", overwritten='original_bar')
        model.create_inherited("/source", "/container/refs/ref1")
        if applied:
            self._set_all_applied(model)
        return model, plugin_api

    def test_get_password(self):
        password = "testing123"
        self.plugin_api_context._security.get_password = \
            lambda service, user: password
        self.assertEqual(password,
                         self.plugin_api_context.get_password("test", "test"))

    def test_query(self):
        result = self.plugin_api_context.query("child", name="test")
        self.assertTrue(isinstance(result[0], QueryItem))
        self.assertEqual(1, len(result))
        self.assertEqual("my_child", result[0]._model_item.item_id)
        self.assertEqual("", result[0]._model_item.parent.item_id)

    def test_query_by_vpath(self):
        item = self.plugin_api_context.query_by_vpath("/my_child")
        same_item = self.plugin_api_context.query("child")[0]
        self.assertTrue(isinstance(item, QueryItem))
        self.assertEqual(item, same_item)
        self.assertEqual('/my_child', item.get_vpath())
        no_item = self.plugin_api_context.query_by_vpath("is/not/there")
        self.assertTrue(no_item == None)

    def test_queryitem_query(self):
        del self.model_manager
        del self.plugin_api_context

        self.model_manager = ModelManager()
        self.plugin_api_context = PluginApiContext(self.model_manager)

        self.model_manager.register_property_type(PropertyType("basic_string"))
        self.model_manager.register_item_type(
            ItemType("root",
                     my_item=Child("base-type"),
                     node=Child("node"),
                     ))

        self.model_manager.register_item_type(ItemType(
                'node',
                child=Child('base-type')
                ))

        self.model_manager.register_item_type(ItemType(
                'base-type',
                name=Property("basic_string")
                ))

        self.model_manager.register_item_type(ItemType(
                'extended-type',
                extend_item='base-type',
                nickname=Property("basic_string")
                ))

        self.model_manager.create_root_item("root")
        self.model_manager.create_item("node", "/node")
        self.model_manager.create_item("base-type", "/node/child", name="alpha")

        # Get a QueryItem for the node
        node_qi = self.plugin_api_context.query('node')[0]
        self.assertEquals('node', node_qi.item_id)
        self.assertEquals('/node', node_qi.get_vpath())

        # Test the context API's query behaviour with regard to extension
        base_items_API = self.plugin_api_context.query('base-type')
        self.assertEquals(1, len(base_items_API))
        self.assertEquals("/node/child", base_items_API[0].get_vpath())

        base_items_QI = node_qi.query('base-type')
        self.assertEquals(1, len(base_items_QI))
        self.assertEquals("/node/child", base_items_QI[0].get_vpath())
        self.assertEquals(base_items_QI, base_items_API)
        self.assertEquals('base-type', base_items_QI[0].item_type_id)

        # Now use the extended type instead!
        self.model_manager.remove_item("/node/child")
        self.model_manager.create_item("extended-type", "/node/child",
                name="alpha", nickname="bravo")

        base_items_API = self.plugin_api_context.query('base-type')
        self.assertEquals(1, len(base_items_API))
        self.assertEquals("/node/child", base_items_API[0].get_vpath())

        node_qi = self.plugin_api_context.query('node')[0]
        base_items_QI = node_qi.query('base-type')
        self.assertEquals(1, len(base_items_QI))
        self.assertEquals("/node/child", base_items_QI[0].get_vpath())
        self.assertEquals(base_items_QI, base_items_API)

        self.assertEquals('extended-type', base_items_QI[0].item_type_id)

    def test_snapshot_object(self):
        # no snapshot
        self.assertEqual(None, self.plugin_api_context._snapshot_object())
        # Initial
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/olakease', timestamp=None
                                       )
        self.assertEqual(ModelItem.Initial,
                         self.plugin_api_context._snapshot_object().get_state())
        # 2 in initial but one failed
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/failed', timestamp='', active=None
                                       )
        self.assertEqual('olakease',
                         self.plugin_api_context._snapshot_object().item_id)
        # For removal
        self.model_manager.get_item('/snapshots/olakease').set_for_removal()
        self.assertEqual(ModelItem.ForRemoval,
                         self.plugin_api_context._snapshot_object().get_state())
        # Applied works only for upgrade snapshot
        self.model_manager.get_item('/snapshots/olakease').set_applied()
        self.assertEqual(ModelItem.Applied,
                         self.plugin_api_context._snapshot_object().get_state())

    def test_snapshot_object_errors(self):
        # Initial + For removal
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/olakease', timestamp=None
                                       )
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/puena', timestamp=None
                                       )
        self.model_manager.get_item('/snapshots/puena').set_for_removal()
        self.assertRaises(Exception, self.plugin_api_context._snapshot_object)
        # +1 initial
        self.model_manager.get_item('/snapshots/puena').set_initial()
        self.assertRaises(Exception, self.plugin_api_context._snapshot_object)
        # +1 For removal
        self.model_manager.get_item('/snapshots/puena').set_for_removal()
        self.model_manager.get_item('/snapshots/olakease').set_for_removal()
        self.assertRaises(Exception, self.plugin_api_context._snapshot_object)
        # make it work
        self.model_manager.get_item('/snapshots/puena').set_applied()
        self.model_manager.get_item('/snapshots/puena').delete_property('active')
        self.assertEqual('olakease',
                         self.plugin_api_context.snapshot_name())

    def test_snapshot_name(self):
        self.assertEqual('', self.plugin_api_context.snapshot_name())
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/olakease', timestamp=None
                                       )
        self.assertEqual('olakease',
                         self.plugin_api_context.snapshot_name())
        self.model_manager.get_item('/snapshots/olakease').set_applied()
        self.assertEqual('olakease', self.plugin_api_context.snapshot_name())
        # try with upgrade snapshot
        self.model_manager.create_item('snapshot-base',
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME),
                                       timestamp=None)
        self.model_manager.get_item(
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME)
                                    ).set_applied()
        self.model_manager.get_item('/snapshots/olakease').delete_property('active')
        self.assertEqual('snapshot', self.plugin_api_context.snapshot_name())

    def test_snapshot_action(self):
        # no snapshot -> error
        self.assertRaises(NoSnapshotItemError, self.plugin_api_context.snapshot_action)
        # base cases
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/olakease', timestamp=None
                                       )
        snapshot = MagicMock()
        snapshot.is_for_removal = MagicMock(return_value = False)
        snapshot.is_initial = MagicMock(return_value = False)
        snapshot.is_applied = MagicMock(return_value = False)
        with patch.object(self.plugin_api_context, '_snapshot_object',
                          MagicMock(return_value = snapshot)):
            self.assertRaises(NoMatchingActionError, self.plugin_api_context.snapshot_action)
        self.assertEqual('create', self.plugin_api_context.snapshot_action())
        self.model_manager.get_item('/snapshots/olakease').set_for_removal()
        self.assertEqual('remove', self.plugin_api_context.snapshot_action())
        # two active snapshots -> error
        self.model_manager.create_item('snapshot-base',
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME),
                                       timestamp=None)
        self.assertRaises(Exception, self.plugin_api_context.snapshot_action)
        # one active snapshot with a valid timestamp
        self.model_manager.get_item(
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME)
                                    ).set_applied()
        self.model_manager.get_item('/snapshots/olakease').delete_property('active')
        self.model_manager.get_item(
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME)
                                    ).set_property('timestamp', str(time()))

        self.assertEqual('restore', self.plugin_api_context.snapshot_action())
        # applied + no timestamp = oops
        self.model_manager.get_item(
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME)
                                    ).delete_property('timestamp')
        self.assertRaises(NoMatchingActionError, self.plugin_api_context.snapshot_action)
        # should never happen!
        self.model_manager.get_item(
                                "/snapshots/{0}".format(UPGRADE_SNAPSHOT_NAME)
                                    ).set_updated()
        self.assertRaises(NoMatchingActionError, self.plugin_api_context.snapshot_action)
        # only upgrade snapshots can be restored
        self.model_manager.get_item('/snapshots/snapshot').delete_property('active')
        self.model_manager.get_item("/snapshots/olakease").set_applied()
        self.model_manager.get_item('/snapshots/olakease').set_property('active', 'true')
        self.model_manager.get_item('/snapshots/olakease').set_property('timestamp', str(time()))
        self.assertRaises(NoMatchingActionError, self.plugin_api_context.snapshot_action)

    def test_snapshot_model_snapshot_state(self):
        # Only expose SnapshotModelApi at restore and remove snapshot
        self.assertRaises(NoSnapshotItemError,
                self.plugin_api_context.snapshot_model)
        self.model_manager.create_item(
                 'snapshot-base', '/snapshots/snapshot', timestamp='123')
        snap = self.plugin_api_context.query_by_vpath('/snapshots/snapshot')
        self.assertEqual(None, self.plugin_api_context.snapshot_model())
        snap._model_item.set_updated()
        self.assertRaises(NoMatchingActionError, self.plugin_api_context.snapshot_model)
        snap._model_item.set_removed()
        self.assertRaises(NoMatchingActionError, self.plugin_api_context.snapshot_model)
        snap._model_item.set_for_removal()
        self.assertTrue(isinstance(self.plugin_api_context.snapshot_model(), SnapshotModelApi))
        snap._model_item.set_applied()
        self.assertTrue(isinstance(self.plugin_api_context.snapshot_model(), SnapshotModelApi))

    def _setup_model_for_clear_property(self):
        model = ModelManager()
        plugin_api = PluginApiContext(model)

        model.register_property_types([
            PropertyType("basic_boolean", regex=r"^(true|false)$"),
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
            PropertyType("any_string", regex=r"^.*$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            source=Child("item"),
            other_source=Child("item-two"),
            another_source=Child("item-three"),
            source_11606=Child("item-four"),
        ))
        model.register_item_type(ItemType(
            "container",
            collection=Collection("root"),
            prop_required=Property("basic_string",
                updatable_plugin=True,
                required=True,
                default='default_value'),
            prop_required_no_def=Property("basic_string",
                updatable_plugin=True,
                required=True),
            prop_standard=Property("basic_boolean",
                updatable_plugin=True,
                default='false'),
            prop_non_up=Property("basic_string",
                updatable_plugin=False),
            prop_optional_apd=Property('basic_string',
                updatable_plugin=True),
            ref=Reference("item-two"),
            another_ref=Reference("item-three"),
            ref_11606=Reference("item-four"),
            ref_read_only=Reference("item",
                read_only=True),
        ))
        model.register_item_type(ItemType("item",
            name=Property("basic_string"),
            item_prop=Property("basic_string",
                updatable_plugin=True),
        ))
        model.register_item_type(ItemType("item-two",
            name=Property("basic_string"),
            item_prop=Property("basic_string",
                updatable_plugin=True),
            any_prop=Property("any_string",
                updatable_plugin=True),
        ))
        model.register_item_type(ItemType("item-three",
            name=Property("basic_string"),
            item_prop=Property("basic_string",
                updatable_plugin=True,
                required=True,
                default='default_from_source',
                )
        ))
        model.register_item_type(ItemType("item-four",
            name=Property("basic_string"),
            item_prop=Property("basic_string",
                updatable_plugin=True,
                required=True,
                )
        ))

        model.create_root_item("root")
        model.create_item("container", "/container", prop_required='original',
                prop_required_no_def='original_no_def', prop_non_up='origin_non_up')
        model.create_item("item", "/source", item_prop="original_source")
        model.create_item("item-two", "/other_source", item_prop="original_other_source")
        model.create_item("item-three", "/another_source", item_prop="new_from_source")
        model.create_item("item-four", "/source_11606", item_prop="11606_source_value")
        model.create_inherited("/other_source", "/container/ref")
        model.create_inherited("/source", "/container/ref_read_only")
        model.create_inherited("/another_source", "/container/another_ref")
        model.create_inherited("/source_11606", "/container/ref_11606")
        self._set_all_applied(model)
        return model, plugin_api

    def test_unset_property(self):
        # LITPCDS-11331 - Mimic CLI litp update -d
        model, plugin_api = self._setup_model_for_clear_property()
        container = plugin_api.query_by_vpath('/container')

        # Test unset required property without default - raises
        self.assertEqual(container.prop_required_no_def, 'original_no_def')
        expected = """ValidationErrors occurred during update of property "prop_required_no_def" on /container:\n<prop_required_no_def - MissingRequiredPropertyError - ItemType "container" is required to have a property with name "prop_required_no_def">"""
        self._assertRaisesCustom(AttributeError, expected,
                container.clear_property, 'prop_required_no_def')
        self.assertEqual(container.prop_required_no_def, 'original_no_def')
        self.assertEqual(ModelItem.Applied, container.get_state())

        # Test happy trail - clears property
        self.assertTrue('prop_standard' in container.properties)
        container.clear_property('prop_standard')
        self.assertFalse('prop_standard' in container.properties)
        self.assertEqual(ModelItem.Updated, container.get_state())

        # Test property required validation with default - revert to default
        self.assertEqual(container.prop_required, 'original')
        container.clear_property('prop_required')
        self.assertEqual(container.prop_required, 'default_value')

        # Test clear updatable_plugin=False property -> raises
        expected = 'Field "prop_non_up" in <ModelItem /container ' \
                'type=container state=Updated> is not updatable by plugins'
        self._assertRaisesCustom(AttributeError, expected,
                container.clear_property, 'prop_non_up')
        self.assertEqual(container.prop_non_up, 'origin_non_up')

        # Test clear property that doesn't exist -> raises
        expected = 'No such field "prop_NON_EXIST" in ' \
                '<ModelItem /container type=container state=Updated>'
        self._assertRaisesCustom(AttributeError, expected,
                container.clear_property, 'prop_NON_EXIST')

        # Test clear something that isn't a property -> raises
        expected = 'Field "collection" in <ModelItem /container type=container' \
                ' state=Updated> is not a Property'
        self._assertRaisesCustom(AttributeError, expected,
                container.clear_property, 'collection')

    def test_clear_property_apd(self):
        # Updated property with APD=False, clear_property() to revert to
        # properties to applied state, item stays in Updated state
        model, plugin_api = self._setup_model_for_clear_property()
        container = plugin_api.query_by_vpath('/container')

        model.update_item(container.vpath, prop_optional_apd='something')
        container._model_item.applied_properties_determinable = False

        self.assertFalse(container.applied_properties_determinable)
        self.assertEqual(container.get_state(), ModelItem.Updated)

        # clear_property to return properties to that of the Applied state
        container.clear_property('prop_optional_apd')
        # Stays in updated due to apd=False
        self.assertEqual(container.get_state(), ModelItem.Updated)
        self.assertFalse(container.applied_properties_determinable)
        self.assertFalse('prop_optional_apd' in container.properties)

    def test_clear_property_inherited(self):
        model, plugin_api = self._setup_model_for_clear_property()
        # Test clear required reference property with default - matches source
        ref = plugin_api.query_by_vpath('/container/another_ref')
        self.assertEqual('new_from_source', ref.item_prop)
        ref.clear_property('item_prop') # Inherit item doesn't have this property
        self.assertEqual('new_from_source', ref.item_prop)

        # Test clear updated required reference property with default - reverts to source
        model.update_item(ref.vpath, item_prop='updated_inherit')
        self.assertEqual('updated_inherit', ref.item_prop)
        ref.clear_property('item_prop') # Inherit item now has this property
        self.assertEqual('new_from_source', ref.item_prop)

        # LITPCDS-11606: Test clear required reference property with no default - matches source
        ref_11606 = plugin_api.query_by_vpath('/container/ref_11606')
        self.assertEqual('11606_source_value', ref_11606.item_prop)
        ref_11606.clear_property('item_prop')
        self.assertEqual('11606_source_value', ref_11606.item_prop)

        # Test clear updated optional reference property no default - reverts to source
        optional_ref = plugin_api.query_by_vpath('/container/ref')
        optional_ref.item_prop = 'updated_other_source'
        self.assertEqual('updated_other_source', optional_ref.item_prop)
        optional_ref.clear_property('item_prop')
        self.assertEqual('original_other_source', optional_ref.item_prop)

        # Test clear reference read only item property
        ref_read_only = plugin_api.query_by_vpath('/container/ref_read_only')
        expected = 'Read-only reference cannot be updated'
        self._assertRaisesCustom(AttributeError, expected,
                ref_read_only.clear_property, 'item_prop')
        self.assertEqual(ref_read_only.item_prop, 'original_source')

    def test_plugin_update_source_property_empty_string(self):
        # LITPCDS-11647
        model, plugin_api = self._setup_model_for_clear_property()
        # Test update option source property with empty string
        source = plugin_api.query_by_vpath('/other_source')
        ref = plugin_api.query_by_vpath('/container/ref')
        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Applied, ref.get_state())
        source.any_prop = ''
        self.assertTrue('any_prop' in source.properties)
        self.assertEqual(source.any_prop, "")
        self.assertEqual(ModelItem.Updated, source.get_state())
        # Check that the reference item also got the value of ''
        self.assertTrue('any_prop' in ref.properties)
        self.assertEqual(ref.any_prop, "")
        self.assertEqual(ModelItem.Updated, ref.get_state())
        # Delete the property from the source (goes from ref too)
        source.clear_property('any_prop')
        self.assertFalse('any_prop' in source.properties)
        self.assertEqual(source.any_prop, None)
        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertFalse('any_prop' in ref.properties)
        self.assertEqual(ref.any_prop, None)
        self.assertEqual(ModelItem.Applied, ref.get_state())

    def test_plugin_update_reference_property_empty_string(self):
        # LITPCDS-11647
        model, plugin_api = self._setup_model_for_clear_property()
        # Test update optional reference property with empty string
        ref = plugin_api.query_by_vpath('/container/ref')
        self.assertEqual(ModelItem.Applied, ref.get_state())
        ref.any_prop = ""
        self.assertTrue('any_prop' in ref.properties)
        self.assertEqual(ref.any_prop, "")
        self.assertEqual(ModelItem.Updated, ref.get_state())
        # Remove the empty string update and check goes to Applied
        ref.clear_property("any_prop")
        self.assertFalse('any_prop' in ref.properties)
        self.assertEqual(ref.any_prop, None)
        self.assertEqual(ModelItem.Applied, ref.get_state())

    def test_update_source_reference_states(self):
        # LITPCDS-11594: Update source, ref item state also Updated
        model, plugin_api = self._setup_model_for_clear_property()
        source = plugin_api.query_by_vpath('/other_source')
        ref = plugin_api.query_by_vpath('/container/ref')

        # Check Applied starting states -> update, states go to Updated
        source.item_prop = 'new_value' # was => 'original_other_source'
        self.assertEqual(ModelItem.Updated, source.get_state())
        self.assertEqual(ModelItem.Updated, ref.get_state())
        # Update source back to Applied state
        source.item_prop = 'original_other_source'
        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Applied, ref.get_state())

        # Check ForRemoval starting state changes:
        # (a) ForRemoval -> update with original value-> states go to Applied
        source.item_prop = "newer_value2"
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.get_state(), ModelItem.Updated)
        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        # Update source back to originally applied state
        source.item_prop = 'original_other_source'
        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Applied, ref.get_state())

        # (b) ForRemoval -> update with new value -> states go to Updated
        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        # Update source with new value, goes to updated state
        source.item_prop = "newer_value"
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.get_state(), ModelItem.Updated)

        # Check Initial starting states -> update source, states stay Initial
        model.set_items_to_initial_from('/') # Set all to Initial
        self.assertEqual(source.get_state(), ModelItem.Initial)
        self.assertEqual(ref.get_state(), ModelItem.Initial)
        source.item_prop = "another_new_item_prop"
        self.assertEqual(source.get_state(), ModelItem.Initial)
        self.assertEqual(source.item_prop, "another_new_item_prop")
        self.assertEqual(ref.get_state(), ModelItem.Initial)
        self.assertEqual(ref.item_prop, "another_new_item_prop")

    def test_for_removal_inherit_validation_errors(self):
        # LITPCDS-11945
        model, plugin_api = self._setup_model_for_clear_property()
        source = plugin_api.query_by_vpath('/other_source')
        ref = plugin_api.query_by_vpath('/container/ref')
        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        # Update reference, source in ForRemoval state -> Raises
        expected = 'ValidationErrors occurred during update of property ' \
            '"item_prop" on /container/ref:\n</container/ref - ' \
            'MethodNotAllowedError - Item\'s source item is marked for removal>'
        self._assertRaisesCustom(AttributeError, expected,
                ref.__setattr__, 'item_prop', 'update_value')
        self.assertEqual('original_other_source', source.item_prop)
        self.assertEqual('original_other_source', ref.item_prop)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)

    def test_update_source_reference_apd_false(self):
        # Update source item back to Applied state, reference is APD=False,
        # reference stays in Updated state (7855 AC6)
        model, plugin_api = self._setup_model_for_clear_property()
        source = plugin_api.query_by_vpath('/other_source')
        ref = plugin_api.query_by_vpath('/container/ref')
        source.item_prop = 'new_value' # was => 'original_other_source'
        self.assertEqual(ModelItem.Updated, source.get_state())
        self.assertEqual(ModelItem.Updated, ref.get_state())
        ref._model_item._set_applied_properties_determinable(False)
        # Update source back to Applied state
        source.item_prop = 'original_other_source'
        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Updated, ref.get_state())

    def test_update_source_reference_overwrites_properties(self):
        # Update source but reference has overwritten properties
        model, plugin_api = self._setup_model_for_clear_property()
        source = plugin_api.query_by_vpath('/other_source')
        ref = plugin_api.query_by_vpath('/container/ref')

        # Update source property with same value, no updates to states
        source.item_prop = 'original_other_source' # was => 'original_other_source'

        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Applied, ref.get_state())

        # Update source, reference also updates
        source.item_prop = 'new_value' # was => 'original_other_source'

        self.assertEqual(ModelItem.Updated, source.get_state())
        self.assertEqual(ModelItem.Updated, ref.get_state())

        # Reference overwrites properties, source stays updated
        ref.item_prop = 'reference_overwrites'

        # Update source back to Applied state, reference stasy updated
        source.item_prop = 'original_other_source'

        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Updated, ref.get_state())

    def test_clear_property_source_updates_reference_state(self):
        # clear_property() on source to bring it back to Applied
        # state, source should follow
        model, plugin_api = self._setup_model_for_clear_property()
        source = plugin_api.query_by_vpath('/other_source')
        ref = plugin_api.query_by_vpath('/container/ref')

        source.any_prop = 'give_value' # originally not there
        self.assertEqual(ModelItem.Updated, source.get_state())
        self.assertEqual(ModelItem.Updated, ref.get_state())
        # clear_property() source back to Applied state
        source.clear_property('any_prop')
        self.assertEqual(source.any_prop, None)
        self.assertEqual(ref.any_prop, None)
        self.assertEqual(ModelItem.Applied, source.get_state())
        self.assertEqual(ModelItem.Applied, ref.get_state())

    def test_update_source_check_ref_collection_states(self):
        model = ModelManager()
        plugin_api = PluginApiContext(model)
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            source=Child("item"),
        ))
        model.register_item_type(ItemType(
            "container",
            refs=RefCollection("item"),
        ))
        model.register_item_type(ItemType(
            "item",
            name=Property("basic_string",
                updatable_plugin=True),
            foo=Property("basic_string",
                updatable_plugin=True),
            bar=Property("basic_string",
                updatable_plugin=True,
                default='default_bar'),
        ))
        model.create_root_item("root")
        model.create_item("container", "/container")
        model.create_item("item", "/source", name="original_name", foo="original_foo")
        model.create_inherited("/source", "/container/refs/ref1")
        model.create_inherited("/source", "/container/refs/ref2")
        model.create_inherited("/source", "/container/refs/ref3")

        source = plugin_api.query_by_vpath("/source")
        self._set_all_applied(model) # Apply source and reference items
        # Inherited items only
        refs = plugin_api.query("container")[0].query("item")
        # Update source
        source.name = "new_name"
        self.assertEqual(source.get_state(), ModelItem.Updated)
        # Check all refs in refCollection were updated
        for ref in refs:
            self.assertEqual(ref.get_state(), ModelItem.Updated)
            self.assertEqual(ref.name, "new_name")
        # Update source back to applied
        source.name = "original_name"
        self.assertEqual(source.get_state(), ModelItem.Applied)
        # Check all refs in refCollection were updated
        for ref in refs:
            self.assertEqual(ref.get_state(), ModelItem.Applied)
            self.assertEqual(ref.name, "original_name")

    def test_update_source_nested_reference_states(self):
        # Update source which has a ref which is also a source
        model = ModelManager()
        plugin_api = PluginApiContext(model)
        model.register_property_types([
            PropertyType("basic_string", regex=r"^[a-zA-Z0-9\-\._]+$"),
        ])
        model.register_item_type(ItemType(
            "root",
            container=Child("container"),
            source=Child("item"),
        ))
        model.register_item_type(ItemType(
            "container",
            refs=RefCollection("item"),
            refs2=RefCollection("item"),
        ))
        model.register_item_type(ItemType(
            "item",
            name=Property("basic_string",
                updatable_plugin=True),
            foo=Property("basic_string",
                updatable_plugin=True),
            bar=Property("basic_string",
                updatable_plugin=True,
                default='default_bar'),
        ))
        model.create_root_item("root")
        model.create_item("container", "/container")
        model.create_item("item", "/source", name="original_name", foo="original_foo")
        model.create_inherited("/source", "/container/refs/ref1")
        model.create_inherited("/container/refs/ref1", "/container/refs/ref2")
        model.create_inherited("/container/refs/ref2", "/container/refs2/ref3")
        self._set_all_applied(model) # Apply source and reference items

        source = plugin_api.query_by_vpath("/source")
        ref1 = plugin_api.query_by_vpath("/container/refs/ref1")
        ref2 = plugin_api.query_by_vpath("/container/refs/ref2")
        # Reference 'ref1' is also source for reference 'ref2'
        self.assertTrue(ref2._model_item.source is ref1._model_item)

        # Update source
        source.bar = 'new_bar'
        self.assertEqual(source.get_state(), ModelItem.Updated)

        self.assertEqual(ref1.get_state(), ModelItem.Updated)
        self.assertEqual(ref1.bar, "new_bar")
        self.assertEqual(ref2.get_state(), ModelItem.Updated)
        self.assertEqual(ref2.bar, "new_bar")

        # Check reference which is in diff ref collection
        ref3 = plugin_api.query_by_vpath("/container/refs2/ref3")
        # Reference 'ref2' is source for reference 'ref3'
        self.assertTrue(ref3._model_item.source is ref2._model_item)
        self.assertEqual(ref3.get_state(), ModelItem.Updated)
        self.assertEqual(ref3.bar, "new_bar")

        # Update source back to applied
        source.bar = 'default_bar'
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(source.bar, 'default_bar')

        self.assertEqual(ref1.get_state(), ModelItem.Applied)
        self.assertEqual(ref1.bar, 'default_bar')
        self.assertEqual(ref2.get_state(), ModelItem.Applied)
        self.assertEqual(ref2.bar, 'default_bar')

        # Check reference which is in diff ref collection
        # Reference 'ref2' is source for reference 'ref3'
        self.assertEqual(ref3.get_state(), ModelItem.Applied)
        self.assertEqual(ref3.bar, "default_bar")

    def test_update_applied_source_for_removal_reference_not_overwritten(self):
        # LITPCDS-12008: Test Plugin API
        # Update applied source with ForRemoval reference
        model, plugin_api = self._simple_model(applied=True)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        # TC1: Update source item with applied properties - updates
        model.remove_item(ref.vpath)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.Applied)

        source.not_overwritten = 'original_foo' # applied property value
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Applied)
        self.assertEqual(source.not_overwritten, 'original_foo')
        self.assertEqual(ref.not_overwritten, 'original_foo')

        # TC2: Update source with new properties -> updates ref
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        source.not_overwritten = 'new_foo' # new property value
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'new_foo')
        self.assertEqual(ref.not_overwritten, 'new_foo')

        # Reset
        source.not_overwritten = 'original_foo'
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Applied)

        # TC5: Update with applied properties ref APD=False -> Updated not Applied
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        ref._model_item._set_applied_properties_determinable(False)
        source.not_overwritten = 'original_foo' # applied property value
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'original_foo')
        self.assertEqual(ref.not_overwritten, 'original_foo')

    def test_update_applied_src_for_removal_ref_overwritten(self):
        model, plugin_api = self._simple_model(applied=True)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        ref.overwritten = 'overwritten_by_ref' # Overwrite ref prop
        self.assertEqual(ref.get_state(), ModelItem.Updated)

        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        # TC3: Update source with applied properties -> no updates
        source.overwritten = 'original_bar'
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'original_bar')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

        # TC4: Update sourcw with new properties -> no ref update
        source.overwritten = 'source_update'
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'source_update')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

        # Extra: Update non overwritten property -> updates ref
        self.assertEqual(ref.not_overwritten, 'original_foo')
        source.not_overwritten = 'source_update'
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'source_update')
        self.assertEqual(ref.not_overwritten, 'source_update')

    def test_update_for_removal_source_for_removal_reference_not_overwritten(self):
        # LITPCDS-12008: Test Plugin API
        # Update ForRemoval source with ForRemoval reference
        model, plugin_api = self._simple_model(applied=True)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        # TC6: Update source item with applied properties - updates
        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)

        source.not_overwritten = 'original_foo' # applied property value
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Applied)
        self.assertEqual(source.not_overwritten, 'original_foo')
        self.assertEqual(ref.not_overwritten, 'original_foo')

        # TC7: Update source with new properties -> updates ref
        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        source.not_overwritten = 'new_foo' # new property value
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'new_foo')
        self.assertEqual(ref.not_overwritten, 'new_foo')

        # Reset for APD=False test
        source.not_overwritten = 'original_foo'
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Applied)

        # TC10: Update with applied properties, ref APD=False -> Updated not Applied
        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        ref._model_item._set_applied_properties_determinable(False)
        source.not_overwritten = 'original_foo' # applied property value
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'original_foo')
        self.assertEqual(ref.not_overwritten, 'original_foo')

    def test_update_for_removal_src_for_removal_ref_overwritten(self):
        model, plugin_api = self._simple_model(applied=True)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        ref.overwritten = 'overwritten_by_ref' # Overwrite ref prop
        self.assertEqual(ref.get_state(), ModelItem.Updated)

        model.remove_item(ref.vpath)
        model.remove_item(source.vpath)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        # TC8: Update source with applied properties -> no ref updates
        source.overwritten = 'original_bar'
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'original_bar')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

        # TC9: Update source with new properties -> no ref update
        model.remove_item(source.vpath)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        source.overwritten = 'source_update'
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'source_update')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

        # Extra: Update src, ref with overwritten props and APD=False -> no ref update
        model.remove_item(source.vpath)
        self.assertEqual(source.get_state(), ModelItem.ForRemoval)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        ref._model_item._set_applied_properties_determinable(False)
        source.overwritten = 'original_bar' # src applied prop
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'original_bar')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

    def test_update_updated_src_for_removal_ref_not_overwritten(self):
        # LITPCDS-12008: Test Plugin API
        # Update Updated source with ForRemoval reference
        model, plugin_api = self._simple_model(applied=True)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        # TC11: Update source item with applied properties - updates
        source.not_overwritten = 'update_source_state' # Updated source
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        source.not_overwritten = 'original_foo' # applied property value
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Applied)
        self.assertEqual(source.not_overwritten, 'original_foo')
        self.assertEqual(ref.not_overwritten, 'original_foo')

        # TC12: Update source with new properties -> updates ref
        source.not_overwritten = 'update_source_state' # Updated source
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        source.not_overwritten = 'new_foo' # new property value
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'new_foo')
        self.assertEqual(ref.not_overwritten, 'new_foo')

        # Reset for APD=False test
        source.not_overwritten = 'original_foo'
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Applied)

        # TC15: Update with applied properties, ref APD=False -> Updated not Applied
        source.not_overwritten = 'update_source_state' # Updated source
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        ref._model_item._set_applied_properties_determinable(False)
        source.not_overwritten = 'original_foo' # applied property value
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'original_foo')
        self.assertEqual(ref.not_overwritten, 'original_foo')

    def test_update_updated_src_for_removal_ref_overwritten(self):
        model, plugin_api = self._simple_model(applied=True)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        ref.overwritten = 'overwritten_by_ref' # Overwrite ref prop
        self.assertEqual(ref.get_state(), ModelItem.Updated)

        source.overwritten = 'update_source_state' # Updated source
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)

        # TC13: Update source with applied properties -> no ref updates
        source.overwritten = 'original_bar' # applied src prop
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'original_bar')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

        # TC14: Update source with new properties -> no ref update
        source.overwritten = 'update_source_state' # Updated source
        self.assertEqual(source.get_state(), ModelItem.Updated)
        source.overwritten = 'source_update'
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'source_update')
        self.assertEqual(ref.overwritten, 'overwritten_by_ref')

        # Extra: Update non overwritten property -> updates ref
        self.assertEqual(ref.not_overwritten, 'original_foo')
        source.not_overwritten = 'source_update_again'
        self.assertEqual(source.get_state(), ModelItem.Updated)
        self.assertEqual(ref.get_state(), ModelItem.Updated)
        self.assertEqual(source.not_overwritten, 'source_update_again')
        self.assertEqual(ref.not_overwritten, 'source_update_again')


    def test_update_initial_src_for_removal_ref_not_overwritten(self):
        # LITPCDS-12008: Test Plugin API
        # Update Initial source with ForRemoval reference
        model, plugin_api = self._simple_model(applied=False)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        # TC16: Update src properties, ref APD=False -> ref updates
        ref._model_item._set_applied_properties_determinable(False)
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Initial)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        source.not_overwritten = 'doesnt_matter'
        self.assertEqual(source.get_state(), ModelItem.Initial)
        self.assertEqual(ref.get_state(), ModelItem.Initial)
        self.assertEqual(source.not_overwritten, 'doesnt_matter')
        self.assertEqual(ref.not_overwritten, 'doesnt_matter')

    def test_update_initial_src_for_removal_ref_overwritten(self):
        model, plugin_api = self._simple_model(applied=False)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        # TC17: Update src properties, ref APD=False -> ref stays ForRemoval
        ref.overwritten = 'ref_overwrites'

        ref._model_item._set_applied_properties_determinable(False)
        model.remove_item(ref.vpath)
        self.assertEqual(source.get_state(), ModelItem.Initial)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        source.overwritten = 'doesnt_matter'
        self.assertEqual(source.get_state(), ModelItem.Initial)
        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.overwritten, 'doesnt_matter')
        self.assertEqual(ref.overwritten, 'ref_overwrites')

    def test_update_applied_source_for_removal_ref_applied_props(self):
        # Update Applied source with an applied property, ForRemoval ref
        # with overwritten version of that property which is applied.
        # No state changes as ref property was overwritten
        model, plugin_api = self._simple_model(applied=False)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        ref.overwritten = 'ref_overwrites'
        self._set_all_applied(model)
        model.remove_item(ref.vpath)

        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.Applied)

        source.overwritten = 'original_bar' # Original value

        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(source.overwritten, 'original_bar')
        self.assertEqual(ref.overwritten, 'ref_overwrites')

    def test_if_all_ref_properties_are_not_overwritten_update_state(self):
        # Update a source item, if any of the updating properties are not
        # overwritten on the reference, then update ref state
        model, plugin_api = self._simple_model(applied=False)
        source = plugin_api.query_by_vpath("/source")
        ref = plugin_api.query_by_vpath("/container/refs/ref1")

        ref.overwritten = 'ref_overwrites'
        self._set_all_applied(model)
        model.remove_item(ref.vpath)

        self.assertEqual(ref.get_state(), ModelItem.ForRemoval)
        self.assertEqual(source.get_state(), ModelItem.Applied)

        # Update both overwritten and non overwritten properties on source
        model.update_item(source.vpath, overwritten='original_bar',
                not_overwritten='original_foo')

        self.assertEqual(ref.get_state(), ModelItem.Applied)
        self.assertEqual(source.get_state(), ModelItem.Applied)
        self.assertEqual(source.overwritten, 'original_bar')
        self.assertEqual(ref.overwritten, 'ref_overwrites')

    def test_remove_item_initial(self):
        model, plugin_api = self._simple_model(applied=False)
        container = plugin_api.query_by_vpath("/container")
        self.assertEqual(container.get_state(), ModelItem.Initial)
        refs = plugin_api.query_by_vpath("/container/refs")
        self.assertEqual(refs.get_state(), ModelItem.Initial)
        ref1 = plugin_api.query_by_vpath("/container/refs/ref1")
        self.assertEqual(ref1.get_state(), ModelItem.Initial)

        plugin_api.remove_item("/container")

        container = plugin_api.query_by_vpath("/container")
        self.assertEqual(container, None)
        refs = plugin_api.query_by_vpath("/container/refs")
        self.assertEqual(refs, None)
        ref1 = plugin_api.query_by_vpath("/container/refs/ref1")
        self.assertEqual(ref1, None)

    def test_remove_item_applied(self):
        model, plugin_api = self._simple_model(applied=True)

        container = plugin_api.query_by_vpath("/container")
        self.assertEqual(container.get_state(), ModelItem.Applied)
        refs = plugin_api.query_by_vpath("/container/refs")
        self.assertEqual(refs.get_state(), ModelItem.Applied)
        ref1 = plugin_api.query_by_vpath("/container/refs/ref1")
        self.assertEqual(ref1.get_state(), ModelItem.Applied)

        plugin_api.remove_item("/container")

        container = plugin_api.query_by_vpath("/container")
        self.assertEqual(container.get_state(), ModelItem.ForRemoval)
        refs = plugin_api.query_by_vpath("/container/refs")
        self.assertEqual(refs.get_state(), ModelItem.ForRemoval)
        ref1 = plugin_api.query_by_vpath("/container/refs/ref1")
        self.assertEqual(ref1.get_state(), ModelItem.ForRemoval)

    def test_is_snapshot_action_forced(self):
        self.assertEqual(None, self.plugin_api_context._snapshot_object())
        self.assertFalse(self.plugin_api_context.is_snapshot_action_forced())
        snap = self.model_manager.create_item('snapshot-base',
                                              '/snapshots/snapshot',
                                              timestamp=None)
        self.assertFalse(self.plugin_api_context.is_snapshot_action_forced())
        snap.set_property('force', 'false')
        self.assertFalse(self.plugin_api_context.is_snapshot_action_forced())
        snap.set_property('force', 'true')
        self.assertTrue(self.plugin_api_context.is_snapshot_action_forced())
