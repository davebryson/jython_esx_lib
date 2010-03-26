

"""
Simple Jython API for interacting with VMWare machines running on VMWare ESX Server. This 
wrapper library makes use of the VI Java API (http://vijava.sourceforge.net/). 

To use this module you must run it through Jython using JDK 1.6

author Dave Bryson

Example use from a Jython shell: 

>> import esx
>> session = esx.login('https://yourserver/sdk','username','password')
>> session,results = esx.listAllRegisteredVMS(session)
>> for i in results: print i 
"""

from java.net import URL
import java.lang as lang
from com.vmware.vim25 import *
from com.vmware.vim25.mo import *
from com.vmware.vim25.mo.util import *

import os.path,re,uuid,sys,time
from honeyclient.util.config import *
from time import sleep


def login(service_url,un,pw):
    """
    Login to the ESX Server and create a Session
    
    :param service_url: full URL to ESX server. ex: 'https://esx_server/sdk/'
    :param un: the account username
    :param pw: the account password
    
    :return:  a 'session' object to pass to other functions
    """
    try:
       return ServiceInstance(URL(service_url),un,pw,True)
    except:
        croak("Error logging into the ESX Server. Check login credentials. Exiting...")

def logout(session):
    """
    Logout the current session

    :param session: the session to close
    :return: None
    """
    session.getServerConnection().logout()
    return None

def isRegisteredVM(session,vm_name):
    """
    Given the name of a VM, check if it's registered

    :param session:
    :param vm_name: the name of the VM
    :return: (session,True | False) 
    """
    rootFolder = session.getRootFolder()
    vm = InventoryNavigator(rootFolder).searchManagedEntity("VirtualMachine",vm_name)
    if vm:
        return (session,True)
    else:
        return (session,False)

def listAllRegisteredVMS(session):
    """ 
    Get a list of all registered VMs (names)
    
    :param session:
    :return: (session,[names])
    """
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("VirtualMachine")
    
    def extract_name(vm): return vm.getName()
    results = map(extract_name,list)
    
    return (session,results)


def registerVM(session,path,name):
    """
    Register the VM in the inventory
    
    :param session:
    :param path: the path to the VMX file
    :param name: the desired registered name of the VM
    :return: session or die on error
    """
    rootFolder = session.getRootFolder()
    data_center = InventoryNavigator(rootFolder).searchManagedEntity("Datacenter","ha-datacenter")
    hostsystem_list = InventoryNavigator(rootFolder).searchManagedEntities("HostSystem")
    
    host = None
    if hostsystem_list and len(hostsystem_list) > 0:
        host = hostsystem_list[0]
    else:
        croak("Error. Can't find a hostsystem needed to register the VM")

    vm_folder = data_center.getVmFolder()
    host_folder = data_center.getHostFolder()
    
    resource = None
    for entry in host_folder.getChildEntity():
        if isinstance(entry,ComputeResource):
            resource = entry
            break
    try:
        task = vm_folder.registerVM_Task(path,name,False,resource.getResourcePool(),host)
        if task.waitForMe() != Task.SUCCESS:
            croak("Failed to register VM: %s",name)
    except MethodFault, detail:
        croak("Error registering the VM. Reason: %s" % detail.getMessage())

    return session

def unRegisterVM(session,name):
    """
    Unregister/remove a VM from the Inventory
    
    :param session:
    :param name: the registered name of the VM
    :return: (session,filename of the VM) on success 
    or (session,'undef') if the VM wasn't found
    """
    vm = getVMbyName(session,name)

    try:
        fn = vm.getConfig().getFiles().getVmPathName()
        vm.unregisterVM()
        return (session,fn)
    
    except MethodFault,detail:
        LOG.error("Error unregistering VM: %s. Reason: %s" % (name,detail.getMessage()))
        return (session,'undef')

def getStateVM(session,name):
    """
    Get the current state of a given VM. Possible states are:
    'poweredOn, 'poweredOff', 'suspended', pendingquestion'.
    
    :param name: the name of the VM
    :return: (session,state) on success or dies on error
    """
    vm = getVMbyName(session,name)
    state = ''

    # Check for possible pending questions
    if vm.getRuntime().getQuestion():
        state = 'pendingquestion'
    elif vm.getRuntime().getPowerState():
        state = str(vm.getRuntime().getPowerState())
    else:
        croak("Could not get execution state of %s" % name)
    
    return (session,state)

def startVM(session,name):
    """
    Start a VM by name
    
    :param session:
    :param name: the name of the VM
    :return: (session, True) or dies on error
    """
    s,state = getStateVM(session,name)
    if state == 'poweredOn':
        return (session,True)

    if state == 'pendingquestion':
        session = answerVM(session,name)
        session,state = getStateVM(session,name)
    
    vm = getVMbyName(session,name)
    task = vm.powerOnVM_Task(None)

    # Note: uses our 'pool' wrapper to check for pending questions
    flag = __poll_task_for_question(task,session,name)
    if flag == Task.SUCCESS:
        return (session,True)
    else:
        croak("Could not start VM %s" % name)

def stopVM(session,name):
    """
    Stop a VM by name

    :param session:
    :param name: the name of the VM
    :return: (session, True) or dies on error
    """
    s,state = getStateVM(session,name)
    if state == 'poweredOff':
        return (session,True)

    # If the thing is suspended you need to start it
    # first to stop it.
    if state == 'suspended':
        startVM(session,name)

    vm = getVMbyName(session,name)
    task = vm.powerOffVM_Task()
    flag = __poll_task_for_question(task,session,name)
    if flag == Task.SUCCESS:
        return (session,True)
    else:
        croak("Could not stop the VM: %s" % name)
        

def rebootVM(session,name):
    """
    Reboot the VM

    :param session:
    :param name: the name of the VM
    :return (session,True) or die on error
    """
    vm = getVMbyName(session,name)

    try: 
        vm.rebootGuest()
        return (session,True)
    except:
        croak("Reboot failed for VM: %s!" % name)

def suspendVM(session,name):
    """
    Suspend a VM
    
    :param session:
    :param name: the name of the VM
    :return: (session,True) or die on error
    """
    s,state = getStateVM(session,name)
    if state == 'suspended':
        return (session,True)

    if state == 'poweredOff':
        croak("Cannot suspend a poweredOff VM. VM name: %s" % name)

    vm = getVMbyName(session,name)
    task = vm.suspendVM_Task()
    flag = __poll_task_for_question(task,session,name)
    if flag == Task.SUCCESS:
        return (session,True)
    else:
        croak("Failed to suspend VM: %s" % name)

def resetVM(session,name):
    """
    Reset (cold boot) the VM
    
    :param session:
    :param name: the name of the VM
    :return (session,True) or die on error
    """
    vm = getVMbyName(session,name)

    task = vm.resetVM_Task()
    flag = __poll_task_for_question(task,session,name)
    if flag == Task.SUCCESS:
        return (session,True)
    else:
        croak("Failed to reset VM: %s" % name)


def fullCloneVM(session,srcname,dstname=None):
    """
    Create a full copy of the src VM to the destination folder, To include associated files (vmdk,nvram, etc...)
    :param srcname: is the name of the existing VM to clone
    :param dstname: is the name of the new directory to copy the VM to.
    :return (session,dstname) or die on error

    Steps:
     1. Generate a VMID if dstname wasn't given
     2. Check if the VM is registered. Then search the snapshot tree
     3. Check if vm is suspended or off If NOT suspend it
     4. Make a full copy of it
     5. register the copy
     6. If it was suspended reset it
    """
    if not srcname:
        croak("Error cloning the VM: srcname wasn't specified")

    if not dstname:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            dstname = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            s,registeredVal = isRegisteredVM(session,dstname)
            if not registeredVal:
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,dstname):
                    # If we didn't find the name in all the snapshots, we're done
                    break
        
    else:
        s,valVM = isRegisteredVM(session,dstname)
        if valVM:
            croak("The dest_name %s matches a registered VM. Please use another name" % dstname)
        if __isSnapshotByName(session,dstname):
            croak("The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname)

    s,src_state = getStateVM(session,srcname)
    
    # Check to make the VM is either powered off or suspended. If it's not in either
    # of these states try to suspend it
    if src_state == 'poweredOn':
        suspendVM(session,srcname)
        s,src_state = getStateVM(session,srcname)

        if src_state == 'poweredOn':
            # If we can't suspend the VM die...
            croak("Cannot perform a fullclone of VM %s - the VM is not suspended or off" % srcname)
    
    session,vmxfile = fullCopyVM(session,srcname,dstname)

    registerVM(session,vmxfile,dstname)
    
    startVM(session,dstname)

    if src_state == 'suspended':
        resetVM(session,dstname)

    return (session,dstname)
    

def quickCloneVM(session,srcname,dstname=None):
    """
    Creates a differential clone of the specified VM.

    :param session:
    :param srcname: the name of the VM to clone
    :param dstname: (OPTIONAL) the name of the clone. If not specified UUID name will be generated  
                    for the dstname

    :return: (session,dstname) or die on error
    """
    if not srcname:
        croak("Error cloning the VM: srcname wasn't specified")

    if not dstname:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            dstname = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            s,r = isRegisteredVM(session,dstname)
            if not r:
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,dstname):
                    # If we didn't find the name in all the snapshots, we're done
                    break
    else:
        s,r = isRegisteredVM(session,dstname)
        if r:
            croak("The dest_name %s matches and existing VM. Please use another name" % dstname)
        if __isSnapshotByName(session,dstname):
            croak("The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname)

    s,src_state = getStateVM(session,srcname)
    
    # Check to make the VM is either powered off or suspended. If it's not in either
    # of these states try to suspend it
    if src_state == 'poweredOn':
        suspendVM(session,srcname)
        s,src_state = getStateVM(session,srcname)

        if src_state == 'poweredOn':
            # If we can't suspend the VM die...
            croak("Cannot perform a quickclone of VM %s - the VM is not suspended or off" % srcname)
    
    src_vm = getVMbyName(session,srcname)

    if src_vm.getSnapshot():
        croak('Cannot quick clone it has snapshots for %s. Delete the snapshots and try again' % srcname)

    LOG.debug("Quick cloning %s to %s" % (srcname,dstname))

    # Make the copy
    session,vmxfile = quickCopyVM(session,srcname,dstname)

    configSpec = VirtualMachineConfigSpec()
    configSpec.setAnnotation(getArg("default_quick_clone_master_annotation","honeyclient::manager::esx"))
    
    try:
        task = src_vm.reconfigVM_Task(configSpec) 
        if not task.waitForMe() == Task.SUCCESS:
            msg = "Error copying %s to %s" % (srcname,dstname)
            croak(msg)
    except MethodFault,detail:
        msg = "Error copying %s to %s Reason: %s" % (srcname,dstname,detail)
        croak(msg)
    
    # register the VM
    registerVM(session,vmxfile,dstname)

    # Reconfigure the clone VM's virtual disk paths, so that they all point to absolute directories of the source VM.
    dst_vm = getVMbyName(session,dstname)

    # Iterate through each virtual disk associated with the source VM and
    # update the corresponding virtual disk on the destination VM.
    dconfigSpec = VirtualMachineConfigSpec()
    vm_device_specs = []
    for dev in src_vm.getConfig().getHardware().getDevice():
         if isinstance(dev,VirtualDisk):

            vdsk_fmt = dev.getBacking()
            if not isinstance(vdsk_fmt,VirtualDiskFlatVer1BackingInfo) and not isinstance(vdsk_fmt,VirtualDiskFlatVer2BackingInfo):
                croak("Error copying %s to %s. Unsupported disk format." % (srcname, dst_name))
            
            dest_dev = None
            for devA in dst_vm.getConfig().getHardware().getDevice():
                if devA.getKey() == dev.getKey():
                    dest_dev = devA
                    break

            # Modify the backing VMDK filename for this virtual disk.
            dest_dev.getBacking().setFileName(dev.getBacking().getFileName())
            
            # Create a virtual device config spec for this virtual disk. 
            vm_device_spec = VirtualDeviceConfigSpec()
            vm_device_spec.setDevice(dest_dev)
            vm_device_spec.setOperation(VirtualDeviceConfigSpecOperation.edit)
            vm_device_specs.append(vm_device_spec)

    dconfigSpec.setDeviceChange(vm_device_specs)
    dconfigSpec.setAnnotation("Type: Quick Cloned VM\n Master VM: " + srcname)
    optvalue = OptionValue()
    optvalue.setKey("uuid.action")
    optvalue.setValue("create")
    dconfigSpec.setExtraConfig([optvalue])

    # Now, reconfigure the destination VM's configuration accordingly.
    try:
        taskA = dst_vm.reconfigVM_Task(dconfigSpec) 
        if not taskA.waitForMe() == Task.SUCCESS:
            croak("Failed to reconfig the dest VM for a quickCopy")
    except MethodFault,detail:
        croak("Failed to reconfig the dest VM for a quickCopy. Reason: %s",detail)
    
    # Now make a snapshot
    snapname = getArg("default_quick_clone_snapshot_name","honeyclient::manager::esx")
    snapdesc = getArg("default_quick_clone_snapshot_description","honeyclient::manager::esx")
    ignore_collisions = True

    # Make an initial snapshot
    session,n = snapshotVM(session,dstname,snapname,snapdesc,ignore_collisions)

    # Start the VM
    startVM(session,dstname)

    # If the Master VM was suspended, then this clone
    # will awake from a suspended state.  We'll still
    # need to issue a full reboot, in order for the
    # clone to get assigned a new network MAC address.
    if src_state == 'suspended':
        resetVM(session,dstname)
        
    return (session,dstname)


def isQuickCloneVM(session,name):
    """
    Test if a given VM was made via quickclone

    :param session:
    :param name: the name of the VM
    :return: (session, True|False)
    """
    vm = getVMbyName(session,name)

    # Helper function that searches all the backing files of each virtual
    # disk and determines if any of them are located outside the VM's main
    # directory.
    # 
    # Inputs: the VM config
    # Outputs: true if the VM is a quick clone; false otherwise
    def isBackingQuickClone(config):
        vm_dirname = os.path.dirname(config.getFiles().getVmPathName())

        for dev in config.getHardware().getDevice():
            if isinstance(dev,VirtualDisk):
                vdsk_fmt = dev.getBacking()
                if not isinstance(vdsk_fmt,VirtualDiskFlatVer1BackingInfo) and not isinstance(vdsk_fmt,VirtualDiskFlatVer2BackingInfo):
                    # If the disk format isn't file-based, then it's definately a
                    # quick clone.
                    return True
                
                backing_dirname = os.path.dirname(dev.getBacking().getFileName())
                if vm_dirname != backing_dirname:
                    # If the backing directory is different than the VM's
                    # directory, then it's a quick clone.
                    return True
        return False
    
    if isBackingQuickClone(vm.getConfig()):
        return (session,True)

    # Helper function that searches all the snapshots of a VM and determines
    # if any of the backing virtual disks are located outside the VM's main
    # directory.
    # 
    # Inputs: snapshot_list
    # Outputs: true if the VM is a quick clone; false otherwise
    def findQuickCloneSnapshots(snap_list):
        for item in snap_list:

            oh_snap = item.getSnapshot()

            snap_view = MorUtil.createExactManagedObject(session.getServerConnection(),oh_snap)

            if isBackingQuickClone(snap_view.getConfig()):
                return True
            
            # If we have children, check them...
            chillin = item.getChildSnapshotList()
            if chillin and findQuickCloneSnapshots(chillin):
                return True

        return False

    snapInfo = vm.getSnapshot()
    if snapInfo and snapInfo.getRootSnapshotList() and findQuickCloneSnapshots(snapInfo.getRootSnapshotList()):
        return (session,True)
    
    return (session,False)


def getDatastoreSpaceAvailableVM(session,name):
    """
    Return all the freespace in the datastore(s) associated with the VM
    
    :param session:
    :param name: the name of the VM
    :return (session,{name,bytes})
    """
    results = {}
    vm = getVMbyName(session,name)

    for d in vm.getDatastores():
        info = d.getInfo()
        results[info.getName()] = info.getFreeSpace()

    return (session,results)

def getHostnameESX(session):
    """
    Get hostname of the ESX server. Although the search returns a list
    of HostSystems, we only check the first for the hostname.

    :param session:
    :return: (session,hostname) on success or (session,None) if hostname is not found
    """
    hostname = None
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("HostSystem")
    if list:
        hostname = list[0].getSummary().getConfig().getName()
        
    return (session,hostname)

def getIPaddrESX(session):
    """
    Get the IP address of the ESX server. Although both the HostSystems and VirtualNic calls
    return an array of values, we only check the first of each.

    :param session:
    :return (session,ip) on success or (session,None) if the IP address is not found
    """
    ip = None
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
   
    :param session:
    :param vmname: the name of the VM
    :return (session,mac)
    """
    mac = None
    vm = getVMbyName(session,name)

    nics = vm.getGuest().getNet()
    if nics and len(nics) > 0:
        mac = nics[0].getMacAddress()
        
    return (session,mac)

def getIPaddrVM(session,name):
    """
    Get the IP address for a VMs first NIC
    
    :param session:
    :param vmname: Is the name of the VM
    :return: (session,IP) on success or (session,None) on fail
    """
    ip = None
    vm = getVMbyName(session,name)

    nics = vm.getGuest().getNet()
    if nics and len(nics) > 0:
        ips = nics[0].getIpAddress()
        if len(ips) > 0:
            ip = ips[0]
        
    return (session,ip)


def getConfigVM(session,name):
    """
    Get the .vmx file information
    
    :param session:
    :param vmname: the name of the VM
    :return: (session,filename) or (session,undef) on error
    """
    vm = getVMbyName(session,name)
    
    filename = vm.getConfig().getFiles().getVmPathName()
    if filename:
        return (session,filename)
    else:
        return (session,"undef")


def destroyVM(session,vmname):
    """
    Destroy a registered VM
    
    :param session:
    :param vmname: the name of the VM
    :return the session on success or dies on failure
    """
    s,state = getStateVM(session,vmname)
    
    if state == 'poweredOn':
        #stop it
        stopVM(session,vmname)
    
    if isQuickCloneVM(s,vmname):
        __delete_filesVM(s,vmname)
        return s
        
    vm = getVMbyName(session,vmname)
    try:
        task = vm.destroy_Task()
        if not task.waitForMe() == Task.SUCCESS:
            croak("Error destroying VM: %s" % vmname)
    except:
        croak("Error destroying VM: %s" % vmname)

    return session

def snapshotVM(session,name,snapshot_name=None,desc=None,ignore_collisions=False):
    """
    Create a snapshot of an existing VM

    :param session:
    :param name: the name of the VM to snapshot
    :param snapshot_name: the name of the snapshot
    :param desc: a description of the snapshot
    :param ignore_collisions: whether to check for existing VMs and snapshots with the same name
                              (default False)
    :return (session,snapshot name) on success or die on failure
    """
    vm = getVMbyName(session,name)

    if not desc:
        desc = snapshot_name

    if not snapshot_name:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            snapshot_name = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            s,r = isRegisteredVM(session,snapshot_name)
            if not r:
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,snapshot_name):
                    # If we didn't find the name in all the snapshots, we're done
                    break
    elif not ignore_collisions:
        s,r1 = isRegisteredVM(session,snapshot_name)
        if r1:
            croak("The dest_name %s matches an existing VM. Please use another name" % snapshot_name)
        if __isSnapshotByName(session,snapshot_name):
            croak("The dest_name %s matches an existing VM Snapshot name. Please use another name" % snapshot_name)
    try:
        task = vm.createSnapshot_Task(snapshot_name,desc,True,True)
        if task.waitForMe() == Task.SUCCESS:
            return (session,snapshot_name)
        else:
            croak("Unable to take a snapshot of VM %s" % name)
    except MethodFault, detail:
        croak("failed to create snapshot. Reason: %s" % detail.getMessage())

def getAllSnapshotsVM(session,name):
    """
      Return the name of all snapshots for a given VM

      :param session:
      :param name: the name of the VM
      
      :return (session, {name:[]}) where:
              'name' is the name of a parent snapshot
              and '[]' is an array of the names of the children in the parent snapshot.
              If the VM doesn't have any snapshots, returns an empty dict
    """
    results = {}

    vm = getVMbyName(session,name)
    
    snapInfo = vm.getSnapshot()
    if not snapInfo:
        return (session,results)

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

    :param session:
    :param vmname: The name of the root VM
    :snapshot_name: The name of the snapshot to revert to
    :return: session on success or die on error
    """

    if not vmname:
        croak("Missing VM name")

    if not snapshot_name:
        croak("Missing Snapshot name to revert to")

    vm = getVMbyName(session,vmname)
    vmsnap = __getSnapshotInTree(vm, snapshot_name)

    if not vmsnap:
        croak("Could not revert VM %s back to snapshot %s" % (vmname,snapshot_name)) 

    task = vmsnap.revertToSnapshot_Task(None)
    if task.waitForMe() == Task.SUCCESS:
        return session
    else:
        croak("Could not revert VM %s back to snapshot %s" % (vmname,snapshot_name)) 


def renameSnapshotVM(session,vmname,old_name,new_name=None,desc=None):
    """
    Rename a snapshot on the given VM

    :param session:
    :param vmname: the name of the VM containing the snapshot
    :param old_name: the name of the existing snapshot
    :param new_name: the new name, if blank a name will be generated
    :param desc: Add a description for the renamed VM (optional)
    :return (session,new_name) on success or die
    """
    vm = getVMbyName(session,vmname)

    if not old_name:
        croak("You must specifiy the old name of the snapshot you want to rename!")

    if not new_name:
        # Create a UUID for the name and check that if doesn't exist 
        while(True):
            new_name = __generateVMID()
            # First check to see it's NOT a registered VM name
            # if it does match an existing name, keep trying with another name
            s,r = isRegisteredVM(session,new_name)
            if not r:
                # Next, check there are NO snapshots with the same name
                if not __isSnapshotByName(session,new_name):
                    # If we didn't find the name in all the snapshots, we're done
                    break
    else:
        s,r = isRegisteredVM(session,new_name)
        if r:
            croak("The new_name %s matches and existing VM. Please use another name" % new_name)
        if __isSnapshotByName(session,new_name):
            croak("The new_name %s matches and existing VM Snapshot name. Please use another name" % new_name)

    if not desc:
        desc = new_name

    #snapshot_tree = None
    #snapInfo = vm.getSnapshot()
    #if snapInfo and snapInfo.getRootSnapshotList():
    #    snapshot_tree = __findSnapshotInTree(snapInfo.getRootsnapshotList(),old_name)
    #
    #if not snapshot_tree:
    #    croak("Problem renaming the snapshot.  Snapshot: %s not found." % old_name)

    # Get the VirtualMachineSnapshot object.
    #oh_snap = snapshot_tree.getSnapshot()
    #snapshot = MorUtil.createExactManagedObject(session.getServerConnection(),oh_snap)

    snapshot = __getSnapshotInTree(vm,old_name)

    if not snapshot:
        croak("Cannot rename a snapshot for VM %s no snapshot found with name %s" % (vmname,old_name))
    try:
        snapshot.renameSnapshot(name_name,desc)
    except:
        croak("Error encountered renaming the snapshot")
    
    return (session,new_name)
    
    

def removeSnapshotVM(session,name,snapshot_name,removeChild=True):
    """
    Remove a given snapshot by name
    
    :param session:
    :param name: is the name of the VM
    :param snapshot_name: is the name of the snapshot
    :param removeChild: Should I remove children on a snapshot?  Default: True
    :return session on success or die on failure
    """
    vm = getVMbyName(session,name)
    
    vmsnap = __getSnapshotInTree(vm, snapshot_name)
    if not vmsnap:
        croak("Could not remove snapshot %s for VM %s" % (snapshot_name,vmname))
        
    task = vmsnap.removeSnapshot_Task(removeChild);

    if task.waitForMe() == Task.SUCCESS:
        return session
    else:
        croak("Could not remove snapshot %s for VM %s" % (snapshot_name,vmname))


""" Helper methods below """

def answerVM(session,name):
    """
    Tries to answer question posed by the server
    
    :param session:
    :param name: the name of the VM
    :return: session or die on error
    """
    powerState = "undef"
    s, powerState = getStateVM(session,name)
    if not powerState == 'pendingquestion':
        return session

    vm = getVMbyName(session,name)
    question = vm.getRuntime().getQuestion()
    questionId = question.getId()
    questionMsg = question.getText().strip().split(":")[0]

    #lista = question.getChoice().getChoiceInfo()
    #for l in lista:
    #    print("label: %s   Summary: %s" % (l.getLabel(),l.getSummary()))

    choice = ""
    if questionMsg == 'msg.uuid.moved':
        choice = "2" # Always create
    elif questionMsg == 'msg.disk.adapterMismatch':
        choice = "0"
    else:
        croak("Encountered unknown question for VM  %s" % name)

    # NOW answer the VM
    try:
        vm.answerVM(questionId,choice)
    except Exception, e:
        croak("Error answering question on VM %r" % e)
        
    time.sleep(2)
        
    return session
        

def getVMbyName(session,name):
    """
    Return the VirtualMachine object for a VM by name. If the VM is NOT
    found, log the error and exit the process
    
    :param session:
    :param name: the name of the VM
    :return: the VM or die
    """
    rootFolder = session.getRootFolder()
    vm = InventoryNavigator(rootFolder).searchManagedEntity("VirtualMachine",name)

    if vm:
        return vm
    else:
        croak("VM name: %s not found" % name)

def __isSnapshotByName(session,snapshot_name):
    """
    Searches for a snapshot by name in a given VM
    
    :param session:
    :param snapshot_name: the name of the snapshot
    :return: True if a snapshot is found
    """
    list = InventoryNavigator(session.getRootFolder()).searchManagedEntities("VirtualMachine")
    for vm in list:
        snShot = vm.getSnapshot()
        if snShot:
            snapTree = snShot.getRootSnapshotList()
            if snapTree:
                if __findByNameInSnapshotTree(snapTree,snapshot_name): 
                    return True
    return False
                                          
def __findByNameInSnapshotTree(snapTree,name):
    """
    Only used by __isSnapshotByName()
    """
    for node in snapTree:
        if name == node.getName():
            return True
        else:
            childTree = node.getChildSnapshotList()
            if childTree and len(childTree) > 0:
                found = __findByNameInSnapshotTree(childTree,name)
                if found: return True
    return False


def __getSnapshotInTree(vm,snapname):
    """
    Find and return a snapshot by name
    
    :param vm: the vm to search
    :param snapname: then name of the snapshot
    :return: snapshot on success or None
    """
    if not vm:
        croak("Missing VM need to find snapshot")

    if not snapname:
        croak("Missing snapshot name needed to find the snapshot")
        
    snap = vm.getSnapshot()
    if not snap:
        return None

    snapTree = snap.getRootSnapshotList()
    if snapTree:
        mor = __findSnapshotInTree(snapTree,snapname)
        if mor:
            return VirtualMachineSnapshot(vm.getServerConnection(), mor)
    
    return None

def __findSnapshotInTree(snapshot_list, snapshot_name):
    """
    Does a recursive search into the snapshop tree finds the first snapshot
    
    :param snapshot_list: the snapshot list
    :param snapshotname: the name of the snapshot
    :return: the snapshot if found or None
    """
    for node in snapshot_list:
        if snapshot_name == node.getName():
            return node.getSnapshot()
        else:
            # check the children
            childTree = node.getChildSnapshotList()
            if childTree:
                mor = __findSnapshotInTree(childTree, snapshot_name)
                if mor:
                    return mor
    return None


def __generateVMID():
    """ 
    Generate a random Unique ID for the VM name
    :return: a Unique ID as a String
    """
    return uuid.uuid4().hex


def fullCopyVM(session,src_name,dst_name):
    """
    Make a *complete* copy of the VM and it's associated files.

    :param session:  the session object
    :param src_name: the name of the VM to copy
    :param dst_name: the new directory name to copy the VM to
    
    :return: The fullpath to the copied VMX or die on error
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
      croak("FileManager not available. Cannot copy the VM")
    
    # Now get the VirtualMachine we're copying
    vm = getVMbyName(session,src_name)

    # Get the name of the datastore that holds the source VM
    # We assume the source VM is located on only one datastore.
    datastore_view = vm.getDatastores()[0]
    datastore_name = datastore_view.getInfo().getName()

    basePath = "["+datastore_name+"] " + dst_name
    #print "BasePath %s" % basePath

    try:
        fileMgr.makeDirectory(basePath,data_center,True)
    except MethodFault, detail:
        croak("Problem making a directory for the VM copy: %s" % detail)
        
    # Loop over all devices attached to the src VM
    for dev in vm.getConfig().getHardware().getDevice():
        if isinstance(dev,VirtualDisk):
            
            key = dev.getControllerKey()
            #print "Controller key %r" % key
            vdsk_fmt = dev.getBacking()

            if not isinstance(vdsk_fmt,VirtualDiskFlatVer1BackingInfo) and not isinstance(vdsk_fmt,VirtualDiskFlatVer2BackingInfo):
                croak("Error copying %s to %s. Unsupported disk format." % (src_name, dst_name))

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
                    croak("Error copying the virtualdisk to destination")
            except MethodFault, detail:
                croak("Error copying the virtualdisk to destination. Reason: %s" % detail)
                
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
                LOG.error("Error copying the NVRAM file(s) to destination")
        except MethodFault,detail:
            LOG.error("Skipping the nvram file...")
        
    if source_vmss and dest_vmss:
        # Attempt to gracefully handle errors.  If the copy fails, we can still continue
        try:
            taskB = fileMgr.copyDatastoreFile_Task(source_vmss,data_center,dest_vmss,data_center,True)
            if not taskB.waitForMe() == Task.SUCCESS:
                LOG.error("Error copying the VMSS file to destination")
        except MethodFault,detail:
             LOG.error("Skipping the vmss file...")

    try:
        taskC = fileMgr.copyDatastoreFile_Task(source_vmx,data_center,dest_vmx,data_center,True)
        if not taskC.waitForMe() == Task.SUCCESS:
            croak("Error copying the VMX file to destination. Some other files may have already been copied")
    except MethodFault, detail:
        croak("Error copying the VMX file to destination. Some other files may have already been copied")
    
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
      croak("FileManager not available. Cannot do a quick copy")
    
    # Now get the VirtualMachine we're copying
    vm = getVMbyName(session,src_name)

    # Get the name of the datastore that holds the source VM
    # We assume the source VM is located on only one datastore.
    datastore_view = vm.getDatastores()[0]
    datastore_name = datastore_view.getInfo().getName()

    basePath = "["+datastore_name+"] " + dst_name

    try:
        fileMgr.makeDirectory(basePath,data_center,True)
    except MethodFault, detail:
        croak("Problem making a directory for the copy: %s" % detail)

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
                croak("Error copying the NVRAM file(s) to destination")
        except MethodFault,detail:
            # Catch the exception and ignore it
            croak('Skipping the nvram file...')

    if source_vmss and dest_vmss:
        # Attempt to gracefully handle errors.  If the copy fails, we can still continue
        try:
            taskB = fileMgr.copyDatastoreFile_Task(source_vmss,data_center,dest_vmss,data_center,True)
            if not taskB.waitForMe() == Task.SUCCESS:
                croak("Error copying the VMSS file to destination")
        except MethodFault,detail:
             croak("Skipping the vmss file...")

    try:
        taskC = fileMgr.copyDatastoreFile_Task(source_vmx,data_center,dest_vmx,data_center,True)
        if not taskC.waitForMe() == Task.SUCCESS:
            croak("Error copying the VMX file to destination")
    except MethodFault, detail:
        croak('Error copying the VMX file!')
    
    return (session,dest_vmx)


def croak(msg):
    """
    Helper method for logging an Error and exiting

    :param msg: the message to log
    """
    LOG.error(msg)
    sys.exit(msg)


def __delete_filesVM(session,name):
    """
    Unregister and delete all files associated with a given VM
    
    :param session:
    :param name: the name of the VM
    :return: True on succes or die
    """
    # Must get this info BEFORE unregistering the VM
    vm = getVMbyName(session,name)
    datastore_list = vm.getDatastores()
    vm_dirname = os.path.dirname(vm.getConfig().getFiles().getVmPathName())

    session,config = unRegisterVM(session,name)
    
    fileMgr = session.getFileManager()
    datacenter_view = InventoryNavigator(session.getRootFolder()).searchManagedEntity("Datacenter","ha-datacenter")

    file_list = []
    for data_storage in datastore_list:
        browser = data_storage.getBrowser()
            
        file_list.append(vm_dirname)
        
        search_spec = HostDatastoreBrowserSearchSpec()
        search_spec.setSortFoldersFirst(True)
        
        task = browser.searchDatastoreSubFolders_Task(vm_dirname,search_spec)
        if task.waitForMe() == Task.SUCCESS:
            results = task.getTaskInfo().getResult().getHostDatastoreBrowserSearchResults()
            
            for r in results:
                folder = r.getFolderPath()
                for f in r.getFile():
                    file_list.append( "/".join([folder,f.getPath()]) )
        else:
            croak("SubFolder search failed!")
            
        reversed_list = sorted(file_list,reverse=True)

        for i in reversed_list:
            task1 = fileMgr.deleteDatastoreFile_Task(i,datacenter_view)
            if not task1.waitForMe() == Task.SUCCESS:
                croak("Unable to delete all of the VM files for VM (%s)" % name)
                
    return True



def __poll_task_for_question(t,session,vmname):
    """
    Checks for questions from ESX. This is a wrapper for the task object. It polls 
    the task and periodically checks for questions.

    :param t: the task
    :param session: the session
    :params vmname: The VM name
    :return: the state of the task or die
    """
    tState = None
    tries = 0 
    maxTries= 3
    problem = None

    while tState == None or tState == str(TaskInfoState.running) or tState == str(TaskInfoState.queued):
        tState = None
        problem = None
        tries=0

        while tState == None:
            tries += 1
            
            if tries > maxTries:
                # Break out of the inner while
                croak("task poller reach max tries!")

            try:
                tState = str(t.getTaskInfo().getState())
            except Exception, e:
                problem = e

        if tState == str(TaskInfoState.running):
            sleep(2)
            
            # Check if the VM is stuck
            s, st = getStateVM(session,vmname)
            
            if st == 'pendingquestion':
                print("We have a pending question!")
                answerVM(session,vmname)
        else:
            sleep(1)

    return str(tState)

