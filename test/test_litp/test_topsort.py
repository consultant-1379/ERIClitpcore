import unittest
from litp.core.topsort import topsort


class TopsortTest(unittest.TestCase):
    def test_topsort(self):
        # TODO - replace splits with []...?
        des_system_lib = 'std synopsys std_cell_lib des_system_lib dw02 dw01' + \
                ' ramlib ieee'
        dw03 = 'std synopsys dware dw03 dw02 dw01 ieee gtech'
        graph = {
            'des_system_lib':   set(des_system_lib.split()),
            'dw01':             set('ieee dw01 dware gtech'.split()),
            'dw02':             set('ieee dw02 dware'.split()),
            'dw03':             set(dw03.split()),
            'dw04':             set('dw04 ieee dw01 dware gtech'.split()),
            'dw05':             set('dw05 ieee dware'.split()),
            'dw06':             set('dw06 ieee dware'.split()),
            'dw07':             set('ieee dware'.split()),
            'dware':            set('ieee dware'.split()),
            'gtech':            set('ieee gtech'.split()),
            'ramlib':           set('std ieee'.split()),
            'std_cell_lib':     set('ieee std_cell_lib'.split()),
            'synopsys':         set(),
        }

        sorted_deps = list(topsort(graph))
        self.assertEquals(
            [
                ['ieee', 'std', 'synopsys'],
                ['dware', 'gtech', 'ramlib', 'std_cell_lib'],
                ['dw01', 'dw02', 'dw05', 'dw06', 'dw07'],
                ['des_system_lib', 'dw03', 'dw04']
            ], sorted_deps)

    def test_blank(self):
        self.assertEquals([], list(topsort({})))

    def test_missing_entries(self):
        graph = {
            'a': set(['b', 'c']),
            'b': set(),
        }

        sorted_deps = list(topsort(graph))
        self.assertEquals([['b', 'c'], ['a']], sorted_deps)

    def test_circular_refs(self):
        graph = {
            'a': set(['b']),
            'b': set(['a']),
        }
        try:
            sorted_deps = list(topsort(graph))
            self.fail("Should have thrown")
        except AssertionError, ae:
            raise
        except Exception, e:
            err_msg = str(e)
            self.assertTrue(
                err_msg.startswith("A cyclic dependency exists in graph")
            )
