import unittest

from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Collection


class ModelDependencyHelperTest(unittest.TestCase):
    def setUp(self):
        self.manager = ModelManager()
        self.dh = self.manager.model_dependency_helper
        self.manager.register_property_type(PropertyType("basic_string"))
        self.manager.register_property_type(PropertyType("special_string",
                                                         regex="^[a-z]+$"))

    def test_dependencies(self):
        self.manager.register_item_types([
            ItemType(
                "foobar_t",
                name=Property("basic_string"),
                foo=Child("items_t", required=True),
                bar=Child("items1_t", required=True, require="foo"),
                baz=Child("items2_t", required=True, require="bar"),
            ),
            ItemType(
                "items_t",
                name=Property("basic_string"),
                fooitems=Collection("foobar_t"),
                baritems=Collection("foobar_t", require="fooitems"),
                bazitems=Collection("foobar_t", require="baritems"),
            ),
            ItemType(
                "items1_t",
                name=Property("basic_string"),
                fooitems=Collection("foobar_t"),
                baritems=Collection("foobar_t", require="fooitems"),
                bazitems=Collection("foobar_t", require="baritems"),
            ),
            ItemType(
                "items2_t",
                name=Property("basic_string"),
                fooitems=Collection("foobar_t"),
                baritems=Collection("foobar_t", require="fooitems"),
                bazitems=Collection("foobar_t", require="baritems"),
            ),
        ])

        self.manager.create_root_item("foobar_t")
        self.manager.create_item("foobar_t", "/bar/baritems/item1")
        self.manager.create_item("foobar_t", "/bar/baritems/item1/bar/baritems/item2")
        self.manager.create_item("foobar_t", "/bar/baritems/item1/bar/fooitems/item2")
        self.manager.create_item("foobar_t", "/bar/baritems/item1/foo/baritems/item2")
        self.manager.create_item("foobar_t", "/foo/fooitems/item1")
        self.manager.create_item("foobar_t", "/foo/fooitems/item1/bar/fooitems/item2")
        self.manager.create_item("foobar_t", "/foo/fooitems/item1/foo/baritems/item2")
        self.manager.create_item("foobar_t", "/foo/fooitems/item1/foo/fooitems/foo")
        self.manager.create_item("foobar_t", "/foo/fooitems/item1/foo/fooitems/item2")

        self.manager.create_item("foobar_t", "/baz/bazitems/item1")

        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/")
        )

        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo")
        )
        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo/fooitems")
        )
        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo/fooitems/item1")
        )
        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo/fooitems/item1/foo")
        )
        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo/fooitems/item1/foo/fooitems")
        )
        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo/fooitems/item1/foo/fooitems/item2")
        )
        self.assertEquals(
            set([]),
            self.dh._get_all_required_items("/foo/fooitems/item1/foo/fooitems/item2/foo")
        )

        self.assertEquals(
            set(["/foo"]),
            self.dh._get_all_required_items("/bar")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems"]),
            self.dh._get_all_required_items("/bar/baritems")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems"]),
            self.dh._get_all_required_items("/bar/baritems/item1")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems", "/bar/baritems/item1/foo"]),
            self.dh._get_all_required_items("/bar/baritems/item1/bar")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems", "/bar/baritems/item1/foo", "/bar/baritems/item1/bar/fooitems"]),
            self.dh._get_all_required_items("/bar/baritems/item1/bar/baritems")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems", "/bar/baritems/item1/foo", "/bar/baritems/item1/bar/fooitems"]),
            self.dh._get_all_required_items("/bar/baritems/item1/bar/baritems/item2")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems", "/bar/baritems/item1/foo", "/bar/baritems/item1/bar/fooitems", "/bar/baritems/item1/bar/baritems/item2/foo"]),
            self.dh._get_all_required_items("/bar/baritems/item1/bar/baritems/item2/bar")
        )

        self.assertEquals(
            set(["/foo", "/bar/fooitems", "/bar/baritems/item1/foo/fooitems", "/bar/baritems/item1/foo/baritems/item2/foo"]),
            self.dh._get_all_required_items("/bar/baritems/item1/foo/baritems/item2/bar")
        )
        self.assertEquals(
            set(["/foo", "/bar/fooitems", "/bar/baritems/item1/foo", "/bar/baritems/item1/bar/fooitems/item2/foo"]),
            self.dh._get_all_required_items("/bar/baritems/item1/bar/fooitems/item2/bar")
        )
        self.assertEquals(
            set(["/foo/fooitems/item1/foo"]),
            self.dh._get_all_required_items("/foo/fooitems/item1/bar/fooitems/item2/foo")
        )
        self.assertEquals(
            set(["/foo/fooitems/item1/foo/fooitems"]),
            self.dh._get_all_required_items("/foo/fooitems/item1/foo/baritems/item2/foo")
        )

        self.assertEquals(
            set(["/foo", "/bar", "/baz/fooitems", "/baz/baritems"]),
            self.dh._get_all_required_items("/baz/bazitems/item1")
        )

        # get_filtered_deps

        vpaths = [
            "/foo/fooitems/item1/foo/fooitems/foo",
            "/bar/baritems/item1/foo/baritems/item2/bar",
            "/baz/bazitems/item1"
        ]

        self.assertEquals(
            set(),
            self.dh.get_filtered_deps(
                "/foo/fooitems/item1/foo/fooitems/foo", vpaths)
        )

        self.assertEquals(
            set(
                [
                    "/foo/fooitems/item1/foo/fooitems/foo"
                ]
            ),
            self.dh.get_filtered_deps(
                "/bar/baritems/item1/foo/baritems/item2/bar", vpaths)
        )

        self.assertEquals(
            set(
                [
                    "/foo/fooitems/item1/foo/fooitems/foo",
                    "/bar/baritems/item1/foo/baritems/item2/bar"
                ]
            ),
            self.dh.get_filtered_deps(
                "/baz/bazitems/item1", vpaths)
        )

    def test_dependencies_extended_types(self):
        self.manager.register_item_types([
            ItemType(
                "root_t",
                foo=Child("foofoo_t", required=True),
                bar=Child("barbar_t", required=True),
            ),

            ItemType(
                "foo_t",
                a=Child("gee_t", required=True),
                b=Child("gee_t", required=True, require="a"),
                foo_name=Property("basic_string"),
            ),
            ItemType(
                "bar_t",
                c=Child("gee_t", required=True),
                d=Child("gee_t", required=True, require="c"),
                bar_name=Property("basic_string"),
            ),

            ItemType(
                # The item type used for all children of items of type foo and
                # bar
                "gee_t",
                name=Property("basic_string")
            ),

            ItemType(
                "barbar_t",
                extend_item="bar_t",
                other_prop=Property("basic_string")
            ),
            ItemType(
                "foofoo_t",
                extend_item="foo_t",
                another_prop=Property("basic_string")
            )
        ])

        self.manager.create_root_item("root_t")

        self.assertEquals(
            set(["/foo/a"]),
            self.dh._get_all_required_items("/foo/b")
        )

        self.assertEquals(
            set(["/bar/c"]),
            self.dh._get_all_required_items("/bar/d")
        )

    def test_extending_types(self):
        a = ItemType(
            "urtype_t",
            name=Property("basic_string"),
            foo=Child("items_t"),
            bar=Child("items1_t", require="foo"),
            baz=Child("items2_t", require="bar"),
        )
        b = ItemType(
            "generic_t",
            extend_item="urtype_t",
            fooitems=Collection("foobar_t"),
            baritems=Collection("foobar_t", require="fooitems"),
            bazitems=Collection("foobar_t", require="baritems"),
        )
        c = ItemType(
            "specialised_t",
            extend_item="generic_t",
            prop=Property("basic_string")
        )
        d = ItemType(
            "very_specialised_t",
            extend_item="specialised_t",
            other_prop=Property("basic_string")
        )

        self.manager.register_item_types([a,b,c,d])

        self.assertEquals(
            ['generic_t', 'specialised_t', 'very_specialised_t'],
            self.dh.get_extending_types(a)
        )
        self.assertEquals(
            ['specialised_t', 'very_specialised_t'],
            self.dh.get_extending_types(b)
        )
        self.assertEquals(
            ['very_specialised_t'],
            self.dh.get_extending_types(c)
        )
        self.assertEquals(
            [],
            self.dh.get_extending_types(d)
        )

    def test_extended_types(self):
        a = ItemType(
            "urtype_t",
            name=Property("basic_string"),
            foo=Child("items_t"),
            bar=Child("items1_t", require="foo"),
            baz=Child("items2_t", require="bar"),
        )
        b = ItemType(
            "generic_t",
            extend_item="urtype_t",
            fooitems=Collection("foobar_t"),
            baritems=Collection("foobar_t", require="fooitems"),
            bazitems=Collection("foobar_t", require="baritems"),
        )
        c = ItemType(
            "specialised_t",
            extend_item="generic_t",
            prop=Property("basic_string")
        )
        d = ItemType(
            "very_specialised_t",
            extend_item="specialised_t",
            other_prop=Property("basic_string")
        )

        self.manager.register_item_types([a,b,c,d])

        self.assertEquals(
            [],
            self.dh._get_extended_types(a)
        )
        self.assertEquals(
            ['urtype_t'],
            self.dh._get_extended_types(b)
        )
        self.assertEquals(
            ['generic_t', 'urtype_t'],
            self.dh._get_extended_types(c)
        )
        self.assertEquals(
            ['specialised_t', 'generic_t', 'urtype_t'],
            self.dh._get_extended_types(d)
        )
