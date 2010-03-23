import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class FullCloneTest(unittest.TestCase):
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')
        self.session = login(self.url,self.un,self.pw)

    def tearDown(self):
        logout(self.session)

    def test_fullclone(self):
        s,cloned_vm = fullCloneVM(self.session,self.testvm)
        
        s,shouldberegistered = isRegisteredVM(self.session,cloned_vm)
        self.assertTrue(shouldberegistered)
        
        s = destroyVM(self.session,cloned_vm)

        from time import sleep
        sleep(20)

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
