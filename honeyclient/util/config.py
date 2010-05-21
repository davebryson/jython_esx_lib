
import org.dom4j.Document
import org.dom4j.Node
from org.dom4j.io import SAXReader
import org.dom4j.XPath

import logging,inspect,re

CONF_FILE = "etc/honeyclient.xml"

# Global XPath and Logger
XP = None
LOG = None
 
def loadConfig():
    """
    Load the configuration file
    return Document
    """
    document = None
    reader = SAXReader()
    try:
        document = reader.read(CONF_FILE)
    except DocumentException, detail:
        print "Error: %s" % detail.getMessage()
        
    return document

def getArg(name,namespace=None,attribute=None):
    """
    Helper function to extract values from the honeyclient.xml configuration file.
    
    Inputs -
      name:      the name of the tag to extract information from
      namespace: search within the namespace of the given tags. Format is 'honeyclient::manager::esx' etc...
                 if NOT set, the code will try to locate where it's being called from and set the namespace
                 based upon that
      attribute: the name of an attribute to extract

    Example:
    <honeyclient>
        <manager>
           <esx>
             <session_timeout description='hello'>1000</session_timeout>
           </esx>
        </manager>
    </honeyclient>

     getArg('session_timeout','honeyclient::manager::esx') => 1000

     getArg('session_timeout','honeyclient::manager::esx','description') => 'hello'

     getArg('esx','honeyclient::manager') => {'session_timeout',[{'1000':{'description':'hello'}}]}
    """
    if not name:
        LOG.error("No name tag specified!")
        return 'undef'
    
    if not namespace:
        # If the user does not specify the namespace. Attempt to locate where we're
        # at in the package space using the caller.

        # Get the package name of the *caller*
        frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])
        
        # Convert the package name into Xpath substituting '.' for '/'
        namespace = "//" + re.sub(r'\.','/',mod.__name__)
    else:
        namespace = "//" + re.sub(r'::','/',namespace)

    # Here I deviate from the logic in the original Perl code. I instead
    # check to see if there's a matching node from 'namespace/name' if NOT
    # return 'undef' and log the reason why. The original code would recursively check
    # the entire document looking for the first matching namespace. It would then
    # use this to grab all ancestors to find the value of the tag you're looking for.  
    # This (to me) seems like it tries to compensate for user error and could lead
    # to the possibilty of someone grabbing the wrong value for a tag.
        
    # build xpath expression
    xpath = namespace + "/" + name
    if attribute:
        # Just return the value of the attribute
        xpath = xpath + "/@"+ attribute

    # Do the search
    node = XP.selectSingleNode(xpath)
    
    # If no results return undef
    if not node:
            return 'undef'
    
    # Check if it's an attribute
    if attribute:
        return node.text.strip()
    
    if node.nodeCount() == 1:
        # we have a single Element
        return node.text.strip()
        
    # If we get this far we have multiple elements - create a hash
    val = {}
    for n in node.elementIterator():
        tag_name = n.name
        if not val.get(tag_name):
            # new key
            val[tag_name] = []
        if n.attributes().size() > 0:
            attr = {}
            #Create a hash of the attributes
            for a in n.attributes():
                attr[a.name] = a.text
            attr2 = {n.text.strip():attr}
            val[tag_name].append(attr2)
        else:
            val[tag_name].append(n.text.strip())
   
    return val
        

def getLogger():
    """
    Hardcoded logger for now. This will use a configuration file in the future.
    returns a logger
    """
    # Format definition for the logger
    format = "%(asctime)s %(levelname)5s [%(funcName)s] (%(filename)s:%(lineno)d) - [PID: %(process)d] - %(message)s"
    
    log = logging.getLogger('honeyclient')
    log.setLevel(logging.DEBUG)
    ch = logging.StreamHandler() 
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter(format)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    return log

LOG = getLogger()
XP = loadConfig()
