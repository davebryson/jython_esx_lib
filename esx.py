

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
import os.path,re,uuid

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


def registerVM(session,path,name):
    """ TODO """
    rootFolder = session.getRootFolder()
    data_center = InventoryNavigator(rootFolder).searchManagedEntity("Datacenter","ha-datacenter")
    hostsystem_list = InventoryNavigator(rootFolder).searchManagedEntities("HostSystem")
    
    host = None
    if hostsystem_list and length(hostsystem_list) > 0:
        host = hostsystem_list[0]
    else:
        print "Error. Can't find a hostsystem needed to register the VM"
        return (session)

    vm_folder = data_center.getVmFolder()
    host_folder = data_center.getHostFolder()
    
    resource = None
    for entry in host_folder.getChildEntity():
        if isinstance(entry,ComputeResource):
            resource = entry
            break

    try:
        task = vm_folder.registerVM_Task(path,name,False,resource.getResourcePool(),host)
        if task.waitForMe() == Task.SUCCESS:
            print "VM successfully registered"
        else:
            print "Failed to register the VM"
    except MethodFault, detail:
        print "Error registering the VM. Reason: %s" % detail

    return session

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
    Create a full copy of the src VM to the destination folder, To include associated files (vmdk,nvram, etc...)
    srcname: is the name of the existing VM to clone
    dstname: is the name of the new directory to copy the VM to.
    returns (session,path_to_the_copy.vmx) or (session,'undef') if the copy fails

    Steps:
    1. Generate a VMID if dstname wasn't given
    2. Check if the VM is registered. Then search the snapshot tree
    3. Check if vm is suspended or off If NOT suspend it
    4. Make a full copy of it
    5. register the copy
    6. If it was suspended reset it
    """
    if not srcname:
        print "Error cloning the VM: srcname wasn't specified"
        return (session,'undef')

    if not dstname:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            dstname = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            if not isRegisteredVM(session,dstname):
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,dstname):
                    # If we didn't find the name in all the snapshots, we're done
                    break
        
    else:
        if isRegisteredVM(session,dstname):
            print "The dest_name %s matches and existing VM. Please use another name" % dstname
            return (session,'undef')
        if __isSnapshotByName(session,dstname):
            print "The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname
            return (session,'undef')

    src_state = getStateVM(session,srcname)
    
    # Check to make the VM is either powered off or suspended. If it's not in either
    # of these states try to suspend it
    if not src_state == 'poweredoff' and not src_state == 'suspended':
        if suspendVM(session,srcname):
            src_state = 'suspended'
        else:
            # If we can't suspend the VM die...
            print 'Error: Unable to suspend the VM before copying it'
            return (session,'undef')
    
    session,vmxfile = fullCopyVM(session,srcname,dstname)

    registerVM(session,vmxfile,dstname)
    
    startVM(session,dstname)

    if src_state == 'suspended':
        resetVM(session,dstname)
    

    return vmxfile
    

def quickCloneVM(session,srcname,dstname):
    """
    """
    if not srcname:
        print "Error cloning the VM: srcname wasn't specified"
        return (session,'undef')

    if not dstname:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            dstname = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            if not isRegisteredVM(session,dstname):
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,dstname):
                    # If we didn't find the name in all the snapshots, we're done
                    break
    else:
        if isRegisteredVM(session,dstname):
            print "The dest_name %s matches and existing VM. Please use another name" % dstname
            return (session,'undef')
        if __isSnapshotByName(session,dstname):
            print "The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname
            return (session,'undef')

    src_state = getStateVM(session,srcname)
    
    # Check to make the VM is either powered off or suspended. If it's not in either
    # of these states try to suspend it
    if not src_state == 'poweredoff' and not src_state == 'suspended':
        if suspendVM(session,srcname):
            src_state = 'suspended'
        else:
            # If we can't suspend the VM die...
            print 'Error: Unable to suspend the VM before copying it'
            return (session,'undef')

    src_vm = getVMbyName(session,srcname)
    if not src_vm:
        print "VM %s not found!" % srcname
        return (session,'undef')

    if src_vm.getSnapshot():
        print 'Cannot quick clone it has snapshots for %s. Delete the snapshots and try again' % srcname
        return (session,'undef')

    # Make the copy
    vmxfile = quickCopyVM(session,srcname,dstname)

    configSpec = VirtualMachineConfigSpec()
    configSpec.setAnnotation("default_quick_clone_master_annotation")
    
    try:
        task = src_vm.reconfigVM_Task(configSpec) 
        if not task.waitForMe() == Task.SUCCESS:
            print 'Failed to reconfig the VM for a quickCopy'
            return (session,'undef')
    except MethodFault,detail:
        print 'Error occured reconfiguring the VM'
        return (session,'undef')
    
    # register the VM
    registerVM(session,vmxfile,dstname)

    # Reconfigure the clone VM's virtual disk paths, so that they all point to absolute directories of the source VM.
    dst_vm = getVMbyName(session,dstname)
    if not dst_vm:
        print "VM %s not found!" % dstname
        return (session,'undef')

    # Iterate through each virtual disk associated with the source VM and
    # update the corresponding virtual disk on the destination VM.
    dconfigSpec = VirtualMachineConfigSpec()
    vm_device_specs = []
    for dev in src_vm.getConfig().getHardware().getDevice():
        if isinstance(dev,VirtualDisk):

            vdsk_fmt = dev.getBacking()
            if not isinstance(vdsk_fmt,VirtualDiskFlatVer1BackingInfo) and not isinstance(vdsk_fmt,VirtualDiskFlatVer2BackingInfo):
                print "Error copying %s to %s. Unsupported disk format." % (src_name, dst_name)
                return (session,"undef")
            
            dest_dev = None
            for devA in dst_vm.getConfig().getHardware().getDevice():
                if devA.getKey() == dev.getKey():
                    dest_dev = devA
                    break

            # Modify the backing VMDK filename for this virtual disk.
            dest_dev.getBacking().setFilename(dev.getBacking().getFilename())
            
            # Create a virtual device config spec for this virtual disk. 
            vm_device_spec = VirtualDeviceConfigSpec()
            vm_device_spec.setDevice(dest_dev)
            vm_device_spec.setOperation(VirtualDeviceConfigSpecOperation.edit)
            
            vm_device_specs.append(vm_device_spec)

    dconfigSpec.setDeviceChange(vm_device_specs)
    dconfigSpec.setAnnotation("Type: Quick Cloned VM\n Master VM: " + src_name)
    optvalue = OptionValue()
    optvalue.setKey("uuid.action")
    optvalue.setValue("create")
    dconfigSpec.setExtraConfig([optvalue])

    # TODO: Pick up here...
    # Now, reconfigure the destination VM's configuration accordingly.
    
    
    return ''


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
        return (session,"undef")


def destroyVM(session,vmname):
    pass


def snapshotVM(session,name,snapshot_name,desc,ignore_collisions=False):
    """
    Create a snapshot of an existing VM
    where - 
    name: the name of the snapshot to create
    snapshot_name: the name of the snapshot
    desc: a description of the snapshot
    ignore_collisions: whether to check for existing VMs and snapshots with the same name
    returns (session,snapshot name) on success and (session, 'undef') on failure
    """
    vm = getVMbyName(session,name)
    if not vm:
        print "VM %s not found!" % name
        return (session,'undef')

    if not desc:
        desc = snapshot_name

    if not snapshot_name:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            dstname = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            if not isRegisteredVM(session,dstname):
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,dstname):
                    # If we didn't find the name in all the snapshots, we're done
                    break
    elif not ignore_collisions:
        if isRegisteredVM(session,dstname):
            print "The dest_name %s matches and existing VM. Please use another name" % dstname
            return (session,'undef')
        if __isSnapshotByName(session,dstname):
            print "The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname
            return (session,'undef')
    
    try:
        task = vm.createSnapshot_Task(snapshot_name,desc,True,True)
        if task.waitForMe() == Task.SUCCESS:
            return (session,snapshot_name)
        else:
            return (session,'undef')
    except MethodFault, detail:
        print "failed to create snapshot. Reason: %s" detail
        return (session,'undef')
    

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


def getVMbyName(session,name):
    """
    Return the VirtualMachine object for a VM by name
    """
    rootFolder = session.getRootFolder()
    vm = InventoryNavigator(rootFolder).searchManagedEntity("VirtualMachine",name)
    return vm



def getAllVMS(session):
    """ 
    Returns a list of all VMs in the system
    """
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("VirtualMachine")
    return (session,list)


# TODO: I need 2 different version: one that can return a Snapshot and one
# that can just check if there's a given name of the snapshot
def __isSnapshotByName(session,snapshot_name):
    for vm in getAllVMS(session):
        snapTree = vm.getSnapshot().getRootSnapshotList()
        if snapTree:
            if __findByNameInSnapshotTree(snapTree,snapshot_name): 
                return True
    return False
                                          
def __findByNameInSnapshotTree(snapTree,name):
    found = False
    for node in snapTree:
        if snapshot_name == node.getName():
            return True
        else:
            childTree = node.getChildSnapshotList()
            if childTree and len(childTree) > 0:
                found = __findByNameInSnapshotTree(childTree,name)
                if found: return True
    
    return found


def __getSnapshotInTree(vm,snapshot_name):

    if vm == None or snapshot_name == None:
        print "Error missing VM and or snapshot_name"
        return False

    snapTree = vm.getSnapshot().getRootSnapshotList()
    if snapTree:
        return  __findSnapshotInTree(snapTree, snapshot_name)
    else:
        return None

def __findSnapshotInTree(snapTree, snapshot_name):
    for node in snapTree:
        if snapshot_name == node.getName():
            #return node.getSnapshot()
            return True
        else:
            # check the children
            childTree = node.getChildSnapshotList()
            if childTree:
                __findSnapshotInTree(childTree, snapshot_name)
            else:
                return False


def __generateVMID():
    """ 
    Generate a random Unique ID for the VM name
    returns ID as a String
    """
    return uuid.uuid4().hex


def fullCopyVM(session,src_name,dst_name):
    """
    Make a *complete* copy of the VM and it's associated files.

    session:  the session object
    src_name: the name of the VM to copy
    dst_name: the new directory name to copy the VM to
    
    returns: The fullpath to the copied VMX file
    """
    # Regular expression used for converting the adapter type
    adapterPattern = re.compile(r"([A-Za-z]{3})(.*)")
    
    rootFolder = session.getRootFolder()
    data_center = InventoryNavigator(rootFolder).searchManagedEntity("Datacenter","ha-datacenter")
    #print "Datacenter: %r" % data_center

    fileMgr = session.getFileManager()
    #print "FileMgr: %r" % fileMgr

    vdiskMgr = session.getVirtualDiskManager()
    
    if not fileMgr:
      print "FileManager not available."
      return (session,'undef')
    
    # Now get the VirtualMachine we're copying
    vm = getVMbyName(session,src_name)
    if not vm:
        print "No VirtualMachine found with name %s" % src_name
        return (session,'undef')

    # Get the name of the datastore that holds the source VM
    # We assume the source VM is located on only one datastore.
    datastore_view = vm.getDatastores()[0]
    datastore_name = datastore_view.getInfo().getName()

    basePath = "["+datastore_name+"] " + dst_name
    #print "BasePath %s" % basePath

    try:
        fileMgr.makeDirectory(basePath,data_center,True)
    except MethodFault, detail:
        print "Problem making a directory for the copy: %s" % detail
        return (session,'undef')
        
    # Loop over all devices attached to the src VM
    for dev in vm.getConfig().getHardware().getDevice():
        if isinstance(dev,VirtualDisk):
            
            key = dev.getControllerKey()
            #print "Controller key %r" % key
            vdsk_fmt = dev.getBacking()

            if not isinstance(vdsk_fmt,VirtualDiskFlatVer1BackingInfo) and not isinstance(vdsk_fmt,VirtualDiskFlatVer2BackingInfo):
                print "Error copying %s to %s. Unsupported disk format." % (src_name, dst_name)
                return (session,"undef")

            # Now get the filename for it
            source_vmdk = vdsk_fmt.getFileName()
            #print "Source vmdk is %s" % source_vmdk
            dest_vmdk = basePath + "/" + os.path.basename(source_vmdk)
            #print "Dest VMDK is %s" % dest_vmdk

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

            # Finally lets copy the virtual disk. Any errors should exit the process
            try:
                task = vdiskMgr.copyVirtualDisk_Task(source_vmdk,data_center,dest_vmdk,data_center,diskSpec,True)
                if not task.waitForMe() == Task.SUCCESS:
                    print "Error copying the virtualdisk to destination"
                    return (session,"undef")
            except MethodFault, detail:
                print "Error copying the virtualdisk to destination. Reason: %s" % detail
                return (session,"undef")
                
    # --- Copy the other files associated with the source VM. ---
    # Get the nvram/vmss files associated with the source VM and construct
    # the nvram/vmss files associated with the destination VM.
    source_nvram = None
    dest_nvram = None
    source_vmss = None
    dest_vmss = None

    # For some reason, the nvram key is set to the "vmname.nvram" EVEN
    # if the nvram file DOES NOT exist! So we need to gracefully handle the error
    # and continue on 
    for entry in vm.getConfig().getExtraConfig():
        # Note: getValue() is an Object
        #print "Entry: K: %s  V: %s" % (entry.getKey(),str(entry.getValue()))
        k = entry.getKey()
        v = str(entry.getValue())
        if k == "nvram" and v != "":
            source_nvram = os.path.dirname(vm.getConfig().getFiles().getVmPathName()) + "/" + v
            #print "Source nvram: %s" % source_nvram
            dest_nvram = basePath + "/" + v
        if k == "checkpoint.vmState" and v != "":
            source_vmss = vm.getConfig().getFiles().getSuspendDirectory() + "/" +  v
            #print "Source vmss: %s" % source_vmss
            dest_vmss = basePath +  "/" +  v
        if source_nvram and dest_nvram and source_vmss and dest_vmss:
            break
    
    source_vmx = vm.getConfig().getFiles().getVmPathName()
    dest_vmx = basePath + "/" + os.path.basename(source_vmx)

    if source_nvram and dest_nvram:
        # Attempt to gracefully handle errors.  If the copy fails, we can still continue
        try:
            taskA = fileMgr.copyDatastoreFile_Task(source_nvram,data_center,dest_nvram,data_center,True)
            if not taskA.waitForMe() == Task.SUCCESS:
                print "Error copying the NVRAM file(s) to destination"
        except MethodFault,detail:
            print "Skipping the nvram file..."
        
    if source_vmss and dest_vmss:
        # Attempt to gracefully handle errors.  If the copy fails, we can still continue
        try:
            taskB = fileMgr.copyDatastoreFile_Task(source_vmss,data_center,dest_vmss,data_center,True)
            if not taskB.waitForMe() == Task.SUCCESS:
                print "Error copying the VMSS file to destination"
        except MethodFault,detail:
             print "Skipping the vmss file..."

    try:
        taskC = fileMgr.copyDatastoreFile_Task(source_vmx,data_center,dest_vmx,data_center,True)
        if not taskC.waitForMe() == Task.SUCCESS:
            print "Error copying the VMX file to destination"
            return (session,"undef")
    except MethodFault, detail:
        print "Error copying the VMX file reason: %s" % detail
        return (session,'undef')
    
    return (session,dest_vmx)



def quickCopyVM(session,src_name,dst_name):
    """
    Make a quick copy of the VM and it's associated files. This mainly differs from
    the full copy by not copying the VMDK file(s)

    session:  the session object
    src_name: the name of the VM to copy
    dst_name: the new directory name to copy the VM to
    
    returns: The fullpath to the copied VMX file
    """
    rootFolder = session.getRootFolder()
    data_center = InventoryNavigator(rootFolder).searchManagedEntity("Datacenter","ha-datacenter")
    
    fileMgr = session.getFileManager()
    
    if not fileMgr:
      print "FileManager not available."
      return (session,'undef')
    
    # Now get the VirtualMachine we're copying
    vm = getVMbyName(session,src_name)
    if not vm:
        print "No VirtualMachine found with name %s" % src_name
        return (session,'undef')

    # Get the name of the datastore that holds the source VM
    # We assume the source VM is located on only one datastore.
    datastore_view = vm.getDatastores()[0]
    datastore_name = datastore_view.getInfo().getName()

    basePath = "["+datastore_name+"] " + dst_name

    try:
        fileMgr.makeDirectory(basePath,data_center,True)
    except MethodFault, detail:
        print "Problem making a directory for the copy: %s" % detail
        return (session,'undef')

    source_nvram = None
    dest_nvram = None
    source_vmss = None
    dest_vmss = None

    # For some reason, the nvram key is set to the "vmname.nvram" EVEN
    # if the nvram file DOES NOT exist! So we need to gracefully handle the error
    # and continue on 
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
        # Attempt to gracefully handle errors.  If the copy fails, we can still continue
        try:
            taskA = fileMgr.copyDatastoreFile_Task(source_nvram,data_center,dest_nvram,data_center,True)
            if not taskA.waitForMe() == Task.SUCCESS:
                print "Error copying the NVRAM file(s) to destination"
        except MethodFault,detail:
            # Catch the exception and ignore it
            print 'Skipping the nvram file...'

    if source_vmss and dest_vmss:
        # Attempt to gracefully handle errors.  If the copy fails, we can still continue
        try:
            taskB = fileMgr.copyDatastoreFile_Task(source_vmss,data_center,dest_vmss,data_center,True)
            if not taskB.waitForMe() == Task.SUCCESS:
                print "Error copying the VMSS file to destination"
        except MethodFault,detail:
             print "Skipping the vmss file..."

    try:
        taskC = fileMgr.copyDatastoreFile_Task(source_vmx,data_center,dest_vmx,data_center,True)
        if not taskC.waitForMe() == Task.SUCCESS:
            print "Error copying the VMX file to destination"
            return (session,"undef")
    except MethodFault, detail:
        print 'Error copying the VMX file!'
        return (session,'undef')
    
    return (session,dest_vmx)
    

    


