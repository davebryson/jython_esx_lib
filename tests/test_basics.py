import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class TestEsxLib(unittest.TestCase):
    """
    Test basics methods
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

    def testEsxHostname(self):
        s,hostname = getHostnameESX(self.session)
        self.assert_(hostname,"Hostname was null")
        
    def testEsxIpAddress(self):
        s,ip = getIPaddrESX(self.session)
        self.assert_(ip,"IP of ESX was null")

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
