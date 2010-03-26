import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *
from time import sleep

class TestBasics(unittest.TestCase):
    """
    Test basics methods. ALL PASSED
    """
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')
        self.session = login(self.url,self.un,self.pw)

    def tearDown(self):
        logout(self.session)

    def testIsRegisteredVM(self):
        s,r = isRegisteredVM(self.session,self.testvm)
        self.assertTrue(r)

    def testListRegisteredVMS(self):
        s,r = listAllRegisteredVMS(self.session)
        self.assertTrue(len(r) > 0)

    def testEsxHostname(self):
        s,hostname = getHostnameESX(self.session)
        self.assert_(hostname,"Hostname was null")
        
    def testEsxIpAddress(self):
        s,ip = getIPaddrESX(self.session)
        flag = re.search(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',ip)
        self.assert_(flag)

    def test_vm_mac(self):
        s,started = startVM(self.session,self.testvm)
        self.assertTrue(started)

        # Sometimes this may fail because the VM appears
        # to take some time to assign a MAC address when powered on
        # so we'll sleep some time to give it a chance...

        for i in range(240):
            s,mac = getMACaddrVM(self.session,self.testvm)
            if mac:
                break
            else:
                sleep(1)
                
        flag = re.search(r'[0-9a-f][0-9a-f]\:[0-9a-f][0-9a-f]\:[0-9a-f][0-9a-f]\:[0-9a-f][0-9a-f]\:[0-9a-f][0-9a-f]',mac)
        self.assert_(flag)

        s,stopped = stopVM(self.session,self.testvm)
        self.assertTrue(stopped)

    def test_vm_ip(self):
        s,started = startVM(self.session,self.testvm)
        self.assertTrue(started)
        
        for i in range(240):
            s,ip = getIPaddrVM(self.session,self.testvm)
            if ip:
                break
            else:
                sleep(1)
                
        flag = re.search(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',ip)
        self.assert_(flag)

        s,stopped = stopVM(self.session,self.testvm)
        self.assertTrue(stopped)

    def test_vm_config(self):
        # Test getting the VMs config
        s, v = getConfigVM(self.session,self.testvm)
        self.assertTrue(v.endswith('vmx'))
        
        
    def test_get_snapshots(self):
        # note h is a hash {name:[snaps],name:[snaps]}
        # Note using a special VM name I know has snapshots
        s, h = getAllSnapshotsVM(self.session,'Drone')
        self.assertTrue(len(h) > 0)
        

    def testDataStoreSpaceAvailable(self):
        s,r = getDatastoreSpaceAvailableVM(self.session,self.testvm)
        self.assertTrue(len(r) > 0)


if __name__ == '__main__':
    unittest.main()
    
