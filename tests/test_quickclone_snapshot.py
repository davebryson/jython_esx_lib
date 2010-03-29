import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *
from time import sleep

class QuickCloneSnapShotTest(unittest.TestCase):
    """

    """
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')
        self.session = login(self.url,self.un,self.pw)

    def tearDown(self):
        logout(self.session)

    
    def test_snap_and_rename_remove(self):
        s, started = startVM(self.session,self.testvm)
        self.assertTrue(started)

        s, cloned_vm = quickCloneVM(self.session,self.testvm)
        
        s,shouldberegistered = isRegisteredVM(self.session,cloned_vm)
        self.assertTrue(shouldberegistered)

        # Make the snapshot
        s,snap_name = snapshotVM(self.session,cloned_vm)
        self.assert_(snap_name)
        
        sleep(2)
        
        s,new_name = renameSnapshotVM(self.session,cloned_vm,snap_name)
        self.assert_(new_name)

        
        # remove the snapshot
        s = removeSnapshotVM(self.session,cloned_vm,new_name)


        s = destroyVM(self.session,cloned_vm)

        sleep(2)

        s,should_not_be_registered = isRegisteredVM(self.session,cloned_vm)
        self.assertFalse(should_not_be_registered)

        # Make sure we return the test vm to it's off state
        s,state1 = getStateVM(s,self.testvm)
        if state1 == 'poweredOn':
            stopVM(self.session,self.testvm)
        elif state1 == 'suspended':
            startVM(self.session,self.testvm)
            stopVM(self.session,self.testvm)
        
        s,state2 = getStateVM(s,self.testvm)
        self.assertEqual('poweredOff',state2)


if __name__ == '__main__':
    unittest.main()
