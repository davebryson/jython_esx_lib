import unittest
from honeyclient.manager.esx import *
from honeyclient.util.config import *
from honeyclient.manager.clone import Clone


class TestClone1(unittest.TestCase):
    """
    """
    def setUp(self):
        url = getArg('service_url','honeyclient::manager::esx::test')
        un = getArg('user_name','honeyclient::manager::esx::test')
        pw = getArg('password','honeyclient::manager::esx::test')
        self.c = Clone(host="127.0.0.1",un=str(un),pw=str(pw),guest_username="",guest_password="")

    def test_maximize(self):
        self.assert_(self.c)
        self.c.vix_maximize_application()
        
    def tearDown(self):
        self.c.shutdown()


if __name__ == '__main__':
    unittest.main()
