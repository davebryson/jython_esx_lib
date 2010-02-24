import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class TestEsxLib(unittest.TestCase):
    """
    Unit tests for the ESX module. login and logout on each test
    """
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')

    def testLogin(self):
        s = login(self.url,self.un,self.pw)
        self.assertTrue(s)
        logout(s)

    def testIsRegisteredVM(self):
        s = login(self.url,self.un,self.pw)
        s,r = isRegisteredVM(s,self.testvm)
        self.assertTrue(r)
        logout(s)

    def testListRegisteredVMS(self):
        s = login(self.url,self.un,self.pw)
        s,r = listAllRegisteredVMS(s)
        self.assertTrue(len(r) > 0)
        logout(s)
    
    def testStartStop(self):
        s = login(self.url,self.un,self.pw)
        
        s,state0 = getStateVM(s,self.testvm)
        
        if state0 == 'poweredOn':
            s,stopit = stopVM(s,self.testvm)
            self.assertTrue(stopit)
            
        s,start = startVM(s,self.testvm)
        self.assertTrue(start)
        
        s,state = getStateVM(s,self.testvm)
        
        self.assertEqual('poweredOn',state)

        s,stopit = stopVM(s,self.testvm)
        self.assertTrue(stopit)
        
        s,state1 = getStateVM(s,self.testvm)
        self.assertEqual('poweredOff',state1)
        logout(s)

    def testSuspendVM(self):
        s = login(self.url,self.un,self.pw)
        
        s,state0 = getStateVM(s,self.testvm)
        if state0 == 'poweredOff' or state0 == 'suspended':
            s,start = startVM(s,self.testvm)
            self.assertTrue(start)

        s,suspended = suspendVM(s,self.testvm)
        
        self.assertTrue(suspended)
        s,state1 = getStateVM(s,self.testvm)
        self.assertEqual("suspended",state1)

        logout(s)
        
    def testFullClone(self):
        dest_name = "testfc1"
        s = login(self.url,self.un,self.pw)
        r = fullCloneVM(s,self.testvm,dest_name)
        self.assertFalse(r == "undef")
        
        sa = destroyVM(s,dest_name)
        from time import sleep
        sleep(20)

        s,b = isRegisteredVM(s,dest_name)
        self.assertFalse(b)
        logout(s)
        


if __name__ == '__main__':
    
    unittest.main()
