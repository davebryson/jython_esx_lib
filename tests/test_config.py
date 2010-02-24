import unittest
from honeyclient.util.config import *

class TestConfig(unittest.TestCase):
    """
    Unit tests for config.py
    """
    def testLoadDocument(self):
        """
        Assert the document is loaded on import config
        """
        self.assert_(XP)

    def testGetAttribute(self):
        r = getArg('session_timeout','honeyclient::manager::esx','description')
        self.assertEqual(r,"A")

    def testGetElement(self):
        r = getArg('session_timeout','honeyclient::manager::esx')
        self.assertEqual(r,"900")

if __name__ == '__main__':
    unittest.main()
