import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *
from time import sleep

class FullCloneSnapShotTest(unittest.TestCase):
    """
    PASSED
    """
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')
        self.session = login(self.url,self.un,self.pw)

    def tearDown(self):
        logout(self.session)


    def test_make_snapshot_and_revert(self):
        
        s,cloned_vm = fullCloneVM(self.session,self.testvm)
        s,shouldberegistered = isRegisteredVM(self.session,cloned_vm)
        self.assertTrue(shouldberegistered)

        # Make the snapshot
        s,snap_name = snapshotVM(self.session,cloned_vm)
        self.assert_(snap_name)

        # Now test reverting it
        sleep(2)
        s = revertVM(self.session,cloned_vm,snap_name)

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

        

if __name__ == '__main__':
    unittest.main()
