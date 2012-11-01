import random
import unittest
import os
import tempfile
from robot.utils.asserts import assert_true, assert_false, assert_equals
from robot.parsing.model import TestCaseFile, TestDataDirectory, ResourceFile
from resources.mocks import FakeSettings
from robotide.controller.commands import DeleteResourceAndImports, DeleteFile, SaveFile

from robotide.controller.filecontrollers import (TestCaseFileController,
                                                 TestDataDirectoryController,
                                                 ResourceFileController)
from robotide.controller import ChiefController
from robotide.publish.messages import RideDataFileRemoved
from robotide.publish import PUBLISHER
import shutil
from robotide.namespace.namespace import Namespace
from robotide.spec.librarymanager import LibraryManager

def create_test_data(path, filepath, resourcepath, initpath):
    if not os.path.exists(path):
        os.mkdir(path)
    open(filepath, 'w').write('''\
*Settings*
Resource  resource.txt
*Test Cases*
Ride Unit Test  No Operation
''')
    open(resourcepath, 'w').write('*Keywords*\nUnit Test Keyword  No Operation\n')
    open(initpath, 'w').write('''\
*Settings*
Documentation  Ride unit testing file
''')

def remove_test_data(path):
    shutil.rmtree(path)

def create_chief():
    library_manager = LibraryManager(':memory:')
    library_manager.create_database()
    return ChiefController(Namespace(FakeSettings()), FakeSettings(), library_manager)


class _DataDependentTest(unittest.TestCase):

    def setUp(self):
        self._dirpath = os.path.join(tempfile.gettempdir(), 'ride_controller_utest_dir'+str(random.randint(0,100000000)))
        self._filepath = os.path.join(self._dirpath, 'tests.txt')
        self._resource_path = os.path.join(self._dirpath, 'resource.txt')
        self._init_path = os.path.join(self._dirpath, '__init__.txt')
        create_test_data(self._dirpath, self._filepath, self._resource_path, self._init_path)

    def tearDown(self):
        remove_test_data(self._dirpath)


class TestModifiedOnDiskWithFileSuite(_DataDependentTest):

    def test_mtime(self):
        ctrl = TestCaseFileController(TestCaseFile(source=self._filepath).populate())
        assert_false(ctrl.has_been_modified_on_disk())
        os.utime(self._filepath, (1,1))
        assert_true(ctrl.has_been_modified_on_disk())

    def test_size_change(self):
        os.utime(self._filepath, None)
        ctrl = TestCaseFileController(TestCaseFile(source=self._filepath).populate())
        open(self._filepath, 'a').write('#Ninja edit\n')
        assert_true(ctrl.has_been_modified_on_disk())

    def test_reload(self):
        controller_parent = object()
        model_parent = object()
        ctrl = TestCaseFileController(
            TestCaseFile(parent=model_parent, source=self._filepath).populate(),
            parent=controller_parent)
        assert_equals(len(ctrl.tests), 1)
        open(self._filepath, 'a').write('Second Test  Log  Hello World!\n')
        ctrl.reload()
        assert_equals(len(ctrl.tests), 2)
        assert_equals(ctrl.tests[-1].name, 'Second Test')
        assert_equals(ctrl.parent, controller_parent)
        assert_equals(ctrl.data.parent, model_parent)

    def test_overwrite(self):
        ctrl = TestCaseFileController(TestCaseFile(source=self._filepath).populate(),
                                      create_chief())
        os.utime(self._filepath, (1,1))
        assert_true(ctrl.has_been_modified_on_disk())
        ctrl.execute(SaveFile())
        assert_false(ctrl.has_been_modified_on_disk())


class TestModifiedOnDiskWithDirectorySuite(_DataDependentTest):

    def test_reload_with_directory_suite(self):
        ctrl = TestDataDirectoryController(TestDataDirectory(source=self._dirpath).populate())
        open(self._init_path, 'a').write('...  ninjaed more documentation')
        ctrl.reload()
        assert_equals(ctrl.settings[0].value,
                      'Ride unit testing file\\nninjaed more documentation')

    def test_mtime_with_directory_suite(self):
        ctrl = TestDataDirectoryController(TestDataDirectory(source=self._dirpath).populate())
        assert_false(ctrl.has_been_modified_on_disk())
        os.utime(self._init_path, (1,1))
        assert_true(ctrl.has_been_modified_on_disk())


class TestModifiedOnDiskWithresource(_DataDependentTest):

    def test_reload_with_resource(self):
        ctrl = ResourceFileController(ResourceFile(source=self._resource_path).populate())
        assert_equals(len(ctrl.keywords), 1)
        open(self._resource_path, 'a').write('Ninjaed Keyword  Log  I am taking over!\n')
        ctrl.reload()
        assert_equals(len(ctrl.keywords), 2)
        assert_equals(ctrl.keywords[-1].name, 'Ninjaed Keyword')


class TestDataFileRemoval(_DataDependentTest):

    def setUp(self):
        _DataDependentTest.setUp(self)
        PUBLISHER.subscribe(self._datafile_removed, RideDataFileRemoved)

    def tearDown(self):
        _DataDependentTest.tearDown(self)
        PUBLISHER.unsubscribe(self._datafile_removed, RideDataFileRemoved)

    def _datafile_removed(self, message):
        self._removed_datafile = message.datafile

    def test_deleting_source_should_remove_it_from_model(self):
        chief = create_chief()
        chief._controller = TestCaseFileController(TestCaseFile(source=self._filepath), chief)
        os.remove(self._filepath)
        ctrl = chief.data
        ctrl.remove()
        assert_true(chief.data is None)
        assert_true(self._removed_datafile is ctrl)

    def test_deleting_file_suite_under_dir_suite(self):
        chief = create_chief()
        chief._controller = TestDataDirectoryController(TestDataDirectory(source=self._dirpath).populate(), chief)
        original_children_length = len(chief.data.children)
        file_suite = chief.data.children[0]
        file_suite.remove()
        assert_true(len(chief.data.children) == original_children_length-1, 'Child suite was not removed')

    def test_deleting_resource_file(self):
        chief = create_chief()
        res = chief.new_resource(self._resource_path)
        res.remove()
        assert_true(len(chief.resources) == 0, 'Resource was not removed')

    def test_deleting_init_file(self):
        chief = create_chief()
        chief._controller = TestDataDirectoryController(TestDataDirectory(source=self._dirpath).populate(), chief)
        os.remove(self._init_path)
        chief.data.remove()
        open(self._init_path, 'w').write('*Settings*\nDocumentation  Ride unit testing file\n')
        assert_true(chief.data.has_format() is False, chief.data.data.initfile)


class DeleteCommandTest(_DataDependentTest):

    def setUp(self):
        _DataDependentTest.setUp(self)
        self.chief = create_chief()
        self.chief.load_data(self._dirpath)
        self.suite = self.chief.suite.children[0]
        self.resource = self.chief.resources[0]

    def test_delete_resource_and_imports(self):
        self.assert_resource_count(1)
        self.assert_import_count(1)
        self.resource.execute(DeleteResourceAndImports())
        self.assert_resource_count(0)
        self.assert_import_count(0)

    def test_delete_file(self):
        self.assert_resource_count(1)
        self.assert_import_count(1)
        self.resource.execute(DeleteFile())
        self.assert_resource_count(0)
        self.assert_import_count(1)

    def assert_resource_count(self, resource_count):
        assert_equals(len(self.chief.resources), resource_count)

    def assert_import_count(self, import_count):
        assert_equals(len(self.suite.setting_table.imports), import_count)


if __name__ == "__main__":
    unittest.main()
