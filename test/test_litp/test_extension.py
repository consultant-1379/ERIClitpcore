##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from unittest import TestCase
from litp.core.extension import ModelExtension


class ExtensionTest(TestCase):
    def setUp(self):
        self.extension = ModelExtension()

    def tearDown(self):
        pass

    def test_extension(self):
        self.assertEquals(
            [],
            self.extension.define_item_types()
        )
        self.assertEquals(
            [],
            self.extension.define_property_types()
        )
