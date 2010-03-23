import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *

class StateTest(unittest.TestCase):
    """
    This is a large test and may take several minutes to complete.
    It exercises the full api
    """
    def setUp(self):
        self.url = getArg('service_url','honeyclient::manager::esx::test')
        self.un = getArg('user_name','honeyclient::manager::esx::test')
        self.pw = getArg('password','honeyclient::manager::esx::test')
        self.testvm = getArg('test_vm_name','honeyclient::manager::esx::test')
        self.session = login(self.url,self.un,self.pw)

    def tearDown(self):
        logout(self.session)

    def test_start_stop(self):
        # Start it
        s, started = startVM(self.session,self.testvm)
        self.assertTrue(started)
        
        # check state
        s, state1 = getStateVM(self.session,self.testvm)
        self.assertEqual("poweredOn",state1)

        # stop it
        s, stopped = stopVM(self.session,self.testvm)
        self.assertTrue(stopped)
        
        # check state
        s, state2 = getStateVM(self.session,self.testvm)
        self.assertEqual("poweredOff",state2)

    def test_reset(self):
        # Start it
        s, started = startVM(self.session,self.testvm)
        self.assertTrue(started)
        
        s, resetted = resetVM(self.session,self.testvm)
        self.assertTrue(resetted)

        # check state
        s, state2 = getStateVM(self.session,self.testvm)
        self.assertEqual("poweredOn",state2)

        s, stopped = stopVM(self.session,self.testvm)
        self.assertTrue(stopped)

    def test_suspend(self):
        # Start it
        s, started = startVM(self.session,self.testvm)
        self.assertTrue(started)
        
        s, suspended = suspendVM(self.session,self.testvm)
        self.assertTrue(suspended)

        # check state
        s, state1 = getStateVM(self.session,self.testvm)
        self.assertEqual("suspended",state1)
        
        startVM(self.session,self.testvm)
        stopVM(self.session,self.testvm)

        # check state
        s, state2 = getStateVM(self.session,self.testvm)
        self.assertEqual("poweredOff",state2)

    def test_isregistered(self):
        s,shouldbetrue = isRegisteredVM(self.session,self.testvm)
        self.assertTrue(shouldbetrue)

        s,shouldbefalse = isRegisteredVM(self.session,"blabblabblacb")
        self.assertFalse(shouldbefalse)




    
if __name__ == '__main__':
    unittest.main()
