import basetest
import unittest
import time
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class TestVMInfo(basetest.BaseTest):
    
    def testMacAndIpAddr(self):

        s,started = startVM(self.session,self.testvm)
        self.assertTrue(started)

        # Sometimes this may fail because the VM appears
        # to take some time to assign a MAC address when powered on
        # so we'll sleep some time to give it a chance...
        s,mac = getMACaddrVM(self.session,self.testvm)
        self.assertTrue(mac)

        s,stopped = stopVM(self.session,self.testvm)
        self.assertTrue(stopped)

        
    def testDataStoreSpaceAvailable(self):
        s,r = getDatastoreSpaceAvailableVM(self.session,self.testvm)
        self.assertTrue(len(r) > 0)
        
    

if __name__ == '__main__':
    unittest.main()
