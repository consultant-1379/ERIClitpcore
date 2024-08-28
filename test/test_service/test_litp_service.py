import os
import sys
import unittest

class TestLitpService(unittest.TestCase):

    def _get_repo_root(self):
        test_module_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = test_module_dir
        while repo_root != os.sep:
            head, tail = os.path.split(repo_root)
            repo_root = head
            if tail == 'test':
                break
        return repo_root

    def test_bin_module_imports(self):
        repo_root = self._get_repo_root()
        module_dir = os.path.join(repo_root, 'bin')
        sys.path.insert(0, module_dir)
        for module in os.listdir(module_dir):
            if not module.endswith(".py"):
                continue
            try:
                __import__(os.path.splitext(module)[0])
            except ImportError:
                self.fail('Error importing module %s' % module)

    def test_src_module_imports(self):
        module_dir = os.path.join(self._get_repo_root(), 'src')
        sys.path.insert(0, module_dir)
        for (dirpath, _, filenames) in os.walk(module_dir):
            for module_filename in filenames:
                if not module_filename.endswith('.py'):
                    continue
                relative_path = dirpath.split(module_dir)[1]
                package_path = relative_path[1:].replace(os.sep, '.')
                if '.alembic' in package_path:
                    continue
                if module_filename == '__init__.py':
                    module_dotted_path = package_path
                else:
                    module_dotted_path = package_path + '.' + module_filename.split('.py')[0]
                if not module_dotted_path:
                    continue

                try:
                    __import__(module_dotted_path)
                except ImportError:
                    self.fail('Error importing module %s' % module_dotted_path)
