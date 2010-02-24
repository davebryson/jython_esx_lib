import basetest
import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class TestEsxInfo(basetest.BaseTest):

    def testEsxHostname(self):
        s,hostname = getHostnameESX(self.session)
        self.assert_(hostname,"Hostname was null")
        
    def testEsxIpAddress(self):
        s,ip = getIPaddrESX(self.session)
        self.assert_(ip,"IP of ESX was null")

if __name__ == '__main__':
    unittest.main()
