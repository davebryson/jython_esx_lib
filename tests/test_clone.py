import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class TestCloneVm(unittest.TestCase):
    """
    Unit tests for the ESX module. login and logout on each test
    """
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')


    def testQuickClone(self):
        s = login(self.url,self.un,self.pw)
        
        s,state0 = getStateVM(s,self.testvm)
        if state0 == 'poweredOn':
            s,stopit = stopVM(s,self.testvm)
            self.assertTrue(stopit)

        # start the testvm
        s,started1 = startVM(s,self.testvm)
        self.assertTrue(started1)

        # quickCloneit
        s, cloned_vm = quickCloneVM(s,self.testvm)
        print "Quick cloned VM is %s" % cloned_vm
        
        # test if it's a quickclone
        s,result = isQuickCloneVM(s,cloned_vm)
        self.assertTrue(result)

        # destory the clone
        sa = destroyVM(s,cloned_vm)
        from time import sleep
        sleep(20)

        # start and stop the testvm
        s,started2 = startVM(s,self.testvm)
        self.assertTrue(started2)

        s,stopit1 = stopVM(s,self.testvm)
        self.assertTrue(stopit1)

        logout(s)
        

if __name__ == '__main__':
    unittest.main()
