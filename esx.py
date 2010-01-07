

"""
Simple Jython API for interacting with VMWare machines running on VMWare ESX Server. This 
wrapper library makes use of the VI Java API (http://vijava.sourceforge.net/). To use this 
module you must run it through Jython using JDK 1.6

author Dave Bryson

Example use from a Jython shell: 

 >> import esx
 >> session = esx.login('https://yourserver/sdk','username','password')
 >> session,results = esx.listAllRegisteredVMS(session)
 >> for i in results: print i 

NOTE: Not ready for production use!!

"""

from java.net import URL
import java.lang as lang
import os.path, re

from com.vmware.vim25 import *
from com.vmware.vim25.mo import *

def login(service_url,un,pw):
    """
    Login to the ESX Server
    
    service_url: full URL to server (https://esx_server/sdk/)
    un: username
    pw: password
    
    returns a 'session' object to pass to other functions
    """
    return ServiceInstance(URL(service_url),un,pw,True)

def logout(session):
    """
    Logout the current session 
    """
    session.getServerConnection().logout()
    return None

def isRegisteredVM(session,vm_name):
    """
    Given a vm_name check if it's registered
    return (session,True|False)
    """
    vm = getVMbyName(session,vm_name)
    if vm:
        return (session,True)
    else:
        return (session,False)

def listAllRegisteredVMS(session):
    """ 
    Get a list of the names of registered VMs
    returns (session,list)
    """
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("VirtualMachine")
    
    def extract_name(vm): return vm.getName()
    results = map(extract_name,list)
    
    return (session,results)


def registerVM(session,name,config):
    """ TODO """
    pass

def unRegisterVM(session,name):
    """
    Unregister a VM given it's name
    """
    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,"error")

    vm.unregisterVM()

    return (session,True)

def getStateVM(session,name):
    """
    Get the state of a given VM
    return (session,state) or (session,"error") if vm not found
    """
    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,"error")

    state = vm.getRuntime().getPowerState()
    return (session,state)

def startVM(session,name):
    """
    Start a VM by name
    return (session, True|False)
    """
    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,False)

    task = vm.powerOnVM_Task(None)
    if task.waitForMe() == Task.SUCCESS:
        return (session,True)
    else:
        return (session,False)

def stopVM(session,name):
    """
    Stop a VM by name
    return (session, True|False)
    """
    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,False)

    task = vm.powerOffVM_Task()
    
    if task.waitForMe() == Task.SUCCESS:
        return (session,True)
    else:
        return (session,False)
   

def rebootVM(session,name):

    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,False)
    
    vm.rebootGuest()
    return (session,True)

def suspendVM(session,name):

    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,False)

    task = vm.suspendVM_Task()
   
    if task.waitForMe() == Task.SUCCESS:
        return (session,True)
    else:
        return (session,False)

def resetVM(session,name):

    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,False)
   
    task = vm.resetVM_Task()
    if task.waitForMe() == Task.SUCCESS:
        return (session,True)
    else:
        return (session,False)
   

def fullCloneVM(session,srcname,dstname):
    """
    Create a full clone of an existing VM
    srcname: is the existing VM to clone
    dstname: is the name of the clone
    returns (session,VirtualMachineCloneSpec) or (session,False) if it fails
    """
    vm = getVMbyName(session,srcname)

    if not vm:
        print "VM %s not found!" % srcname
        return (session,False)


    # Create a default spec
    cloneSpec = VirtualMachineCloneSpec()
    cloneSpec.setLocation(VirtualMachineRelocateSpec())
    cloneSpec.setPowerOn(False)
    cloneSpec.setTemplate(False)
    
    task = vm.cloneVM_Task(vm.getParent(),dstname,cloneSpec)
    if task.waitForMe() == Task.SUCCESS:
        return (session,cloneSpec)
    else:
        return (session,False)
    


def quickCloneVM(session,srcname,dstname):
    """
    This function is defined in ESX.pm but I'm not
    sure what the difference between a quickclone and fullclone is.
    For now clone capability is defined above?
    """
    pass


def isQuickCloneVM(session,vmname):
    """
    What constitutes a quick clone?
    """
    pass

def getDatastoreSpaceAvailableVM(session,name):
    """
    Return all the freespace in the datastore(s) associated with the VM
    returns (session,{}) where the hash is {name of datastore: freespace}
    """
    results = {}

    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,False)

    for d in vm.getDatastores():
        info = d.getInfo()
        results[info.getName()] = info.getFreeSpace()

    return (session,results)

def getHostnameESX(session):
    """
    Get hostname of the ESX server. Although the search returns a list
    of HostSystems, we only check the first for the hostname
    returns (session,hostname) on success or (session,'undef') if hostname is not found
    """
    hostname = "undef"
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("HostSystem")
    if list:
        hostname = list[0].getSummary().getConfig().getName()
        
    return (session,hostname)

def getIPaddrESX(session):
    """
    Get the IP address of the ESX server. Although both the HostSystems and VirtualNic calls
    return an array of values, we only check the first of each.
    returns (session,ip) on success or (session,'undef') if the IP address is not found
    """
    ip = "undef"
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("HostSystem")
    if list:
        nics = list[0].getConfig().getNetwork().getVnic()
        if nics:
           ip =  nics[0].getSpec().getIp().getIpAddress()
    
    return (session,ip)

def getMACaddrVM(session,name):
    """
    Get the macaddress of the VMs first NIC
    vmname: the name of the VM
    returns (session,mac)
    """
    mac = ""

    vm = getVMbyName(session,name)
    if not vm :
        print "VM %s not found!" % name
        return (session,"error")
     
    nics = vm.getGuest().getNet()
    if nics and len(nics) > 0:
        mac = nics[0].getMacAddress()
        
    return (session,mac)

def getIPaddrVM(session,name):
    """
    Get the IP address for a VMs first NIC
    vmname: Is the name of the VM
    returns: (session,IP) on success or (session,error) on fail
    """
    ip = ""
    vm = getVMbyName(session,name)

    if not vm:
        print "VM %s not found!" % name
        return (session,"error")
    
    nics = vm.getGuest().getNet()
    if nics and len(nics) > 0:
        ips = nics[0].getIpAddress()
        if len(ips) > 0:
            ip = ips[0]
        
    return (session,ip)


def getConfigVM(session,name):
    """
    Get the .vmx file information
    vmname: the name of the VM
    return (session,filename)
    """
    vm = getVMbyName(session,name)
    if not vm:
        print "VM %s not found!" % name
        return (session,"error")
    
    filename = vm.getConfig().getFiles().getVmPathName()
    if filename:
        return (session,filename)
    else:
        return (session,"undefined")


def destroyVM(session,vmname):
    pass

def snapshotVM(session,name,snapshot_name,desc="This is a snapshot"):
    """
    Create a snapshot of an existing VM
    where - 
    vmname: the name of the snapshot to create
    snapshot_name: the name of the snapshot
    desc: a description of the snapshot
    returns (session,True) on success and (session,False) on failure
    """
    vm = getVMbyName(session,name)
    
    if not vm:
        print "VM %s not found!" % name
        return (session,False)

    task = vm.createSnapshot_Task(snapshot_name,desc,False,False)
    
    if task.waitForMe() == Task.SUCCESS:
        return (session,True)
    else:
        return (session,False)
    

def getAllSnapshotsVM(session,name):
    """
      Return the name of snapshots
      returns (session, hash {name:[]}) where 'name' id the name of a parent snapshot
      and '[]' is an array of the names of children of the parent snapshot
    """
    results = {}

    vm = getVMbyName(session,name)
    
    if not vm:
        print "VM %s not found!" % name
        return (session,"error")

    snapInfo = vm.getSnapshot()
    snapTree = snapInfo.getRootSnapshotList()
    for node in snapTree:
        childTree = []
        name = node.getName()
        children = node.getChildSnapshotList()
        if children:
            for c in children:
                childTree.append(c.getName())
        results[name] = childTree
    
    return (session,results)
                                 
    
def revertVM(session,vmname,snapshot_name):
    """ 
    Revert back to a previous snapshot
    vmname: The name of the root VM
    snapshot_name: The name of the VM to revert to
    returns (session,True) on success and (session,False) on fail
    """
    vmsnap = getSnapshotInTree(vm, snapshot_name)
    if vmsnap:
        task = vmsnap.revertToSnapshot_Task(None)
        if task.waitForMe() == Task.SUCCESS:
            return (session,True)
        else:
            return (session,False)
    else:
        return (session,False)

def renameSnapshotVM(session,vmname,old_name,new_name):
    pass

def removeSnapshotVM(session,name,snapshot_name,removeChild=True):
    """
    Remove a given snapshot
    vmname: is the original name of the VM
    snapshot_name: is the name of the snapshot
    removeChild: Should I remove children on a snapshot?  Default: True
    returns (session,True) on success and (session,False) on failure
    """
    vm = getVMbyName(session,name)
    
    if not vm:
        print "VM %s not found!" % name
        return (session,False)
   
    vmsnap = getSnapshotInTree(vm, snapshot_name)
    if vmsnap:
        task = vmsnap.removeSnapshot_Task(removeChild);

        if task.waitForMe() == Task.SUCCESS:
            return (session,True)
        else:
            return (session,False)
    else:
        return (session,False)


""" Helper methods below """
def __getSnapshotInTree(vm,snapshot_name):

    if vm == None or snapshot_name == None:
        return None

    snapTree = vm.getSnapshot().getRootSnapshotList()
    if snapTree :
        mor = findSnapshotInTree(snapTree, snapshot_name)
        if mor: 
            return VirtualMachineSnapshot(vm.getServerConnection(), mor)
    return None

def __findSnapshotInTree(snapTree, snapshot_name):
    
    for node in snapTree:
        if snapshot_name == node.getName():
            return node.getSnapshot()
        else:
            # check the children
            childTree = node.getChildSnapshotList()
            if childTree:
                mor = findSnapshotInTree(childTree, snapshot_name)
                if mor:
                    return mor
    return None


def fullCopyVM(session,src_name,dst_name):
    """
    Still testing, more to come...
    """
    # Regular expression used for converting the adapter type
    adapterPattern = re.compile(r"([A-Za-z]{3})(.*)")
    
    rootFolder = session.getRootFolder()
    data_center = InventoryNavigator(rootFolder).searchManagedEntity("Datacenter", "ha-datacenter")
    fileMgr = session.getFileManager()
    vdiskMgr = session.getVirtualDiskManager()
    
    if not fileMgr:
      print "FileManager not available."
      return (session,'undef')
    
    # Now get the VirtualMachine we're copying
    vm = getVMbyName(session,src_name)
    if not vm:
        print "No VirtualMachine found with name %s" % src_name
        
    # Get the name of the datastore that holds the source VM
    # We assume the source VM is located on only one datastore.
    datastore_view = vm.getDatastores()[0]
    datastore_name = datastore_view.getInfo().getName()

    basePath = "["+datastore_name+"] " + dst_name
    print "BasePath %s" % basePath

    fileMgr.makeDirectory(basePath,data_center,True)

    # Loop over all devices attached to the src VM
    for dev in vm.getConfig().getHardware().getDevice():
        if isinstance(dev,VirtualDisk):
            
            key = dev.getControllerKey()
            print "Controller key %r" % key
            vdsk_fmt = dev.getBacking()

            if not isinstance(vdsk_fmt,VirtualDiskFlatVer1BackingInfo) and not isinstance(vdsk_fmt,VirtualDiskFlatVer2BackingInfo):
                print "Error copying %s to %s. Unsupported disk format." % (src_name, dst_name)
                return (session,"undef")

            # Now get the filename for it
            source_vmdk = vdsk_fmt.getFileName()
            print "Source vmdk is %s" % source_vmdk
            dest_vmdk = basePath + "/" + os.path.basename(source_vmdk)
            print "Dest VMDK is %s" % dest_vmdk

            # We *have* to loop over all the devices again discover 
            # the SCSI Adapter type by matching on the controller key
            for dev in vm.getConfig().getHardware().getDevice():
                if dev.getKey() == key:
                    adapter_type = dev.getDeviceInfo().getSummary()
                    # Strip whitespace
                    adapter_type1 = "".join(adapter_type.split())
                    # parse the name on the first 3 characters
                    m = adapterPattern.match(adapter_type1)
                    # make the first 3 chars lowercase
                    adapterType = m.group(1).lower() + m.group(2)
                    break
                
            diskSpec = VirtualDiskSpec()
            
            esx_version = session.getAboutInfo().getVersion()
            if esx_version > "4.0.0":
                diskSpec.setDiskType("preallocated")
            else:
                diskSpec.setDiskType("")

            diskSpec.setAdapterType(adapterType)

            # Finally lets copy the virtual disk
            task = vdiskMgr.copyVirtualDisk_Task(src_vmdk,data_center,dst_vmdk,data_center,diskSpec,true)
            if not task.waitForMe() == Task.SUCCESS:
                print "Error copying the virtualdisk to destination"
                return (session,"undef")
    
    # --- Copy the other files associated with the source VM. ---
    # Get the nvram/vmss files associated with the source VM and construct
    # the nvram/vmss files associated with the destination VM.
    source_nvram = None
    dest_nvram = None
    source_vmss = None
    dest_vmss = None
    for entry in vm.getConfig().getExtraConfig():
        # Note: getValue() is an Object
        k = entry.getKey()
        v = str(entry.getValue())
        if k == "nvram" and v != "":
            source_nvram = os.path.dirname(vm.getConfig().getFiles().getVmPathName()) + "/" + v
            dest_nvram = basePath + "/" + v
        if k == "checkpoint.vmState" and v != "":
            source_vmss = vm.getConfig().getFiles().getSuspendDirectory() + "/" +  v
            dest_vmss = basePath +  "/" +  v
        if source_nvram and dest_nvram and source_vmss and dest_vmss:
            break
    
    source_vmx = vm.getConfig().getFiles().getVmPathName()
    dest_vmx = basePath + "/" + os.path.basename(source_vmx)

    if source_nvram and dest_nvram:
        taskA = fileMgr.copyDatastoreFile_Task(source_nvram,data_center,dest_nvram,data_center,True)
        if not taskA.waitForMe() == Task.SUCCESS:
            print "Error copying the NVRAM file(s) to destination"
            return (session,"undef")
        
    if source_vmss and dest_vmss:
        taskB = fileMgr.copyDatastoreFile_Task(source_vmss,data_center,dest_vmss,data_center,True)
        if not taskB.waitForMe() == Task.SUCCESS:
            print "Error copying the NVRAM file(s) to destination"
            return (session,"undef")

    taskC = fileMgr.copyDatastoreFile_Task(source_vmx,data_center,dest_vmx,data_center,True)
    if not taskC.waitForMe() == Task.SUCCESS:
        print "Error copying the NVRAM file(s) to destination"
        return (session,"undef")
    
    
    return (session,dest_vmx)


def getVMbyName(session,name):
    """
    Return the VirtualMachine object for a VM by name
    """
    rootFolder = session.getRootFolder()
    vm = InventoryNavigator(rootFolder).searchManagedEntity("VirtualMachine",name)
    return vm
