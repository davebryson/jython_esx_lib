

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
from com.vmware.vim25 import *
from com.vmware.vim25.mo import *
from com.vmware.vim25.mo.util import *

import os.path,re,uuid,sys,time
from honeyclient.util.config import *
from time import sleep


def login(service_url,un,pw):
    """
    Login to the ESX Server
    
    service_url: full URL to server (https://esx_server/sdk/)
    un: username
    pw: password
    
    returns a 'session' object to pass to other functions
    (TESTED)
    """
    try:
       return ServiceInstance(URL(service_url),un,pw,True)
    except:
        croak("Error logging into the ESX Server. Check login credentials. Exiting...")

def logout(session):
    """
    Logout the current session
    (TESTED)
    """
    session.getServerConnection().logout()
    return None

def isRegisteredVM(session,vm_name):
    """
    Given a vm_name check if it's registered
    returns (session,True)
    (TESTED)
    """
    rootFolder = session.getRootFolder()
    vm = InventoryNavigator(rootFolder).searchManagedEntity("VirtualMachine",vm_name)
    if vm:
        return (session,True)
    else:
        return (session,False)

def listAllRegisteredVMS(session):
    """ 
    Get a list of the names of registered VMs
    returns (session,list)
    (TESTED)
    """
    rootFolder = session.getRootFolder()
    list = InventoryNavigator(rootFolder).searchManagedEntities("VirtualMachine")
    
    def extract_name(vm): return vm.getName()
    results = map(extract_name,list)
    
    return (session,results)


def registerVM(session,path,name):
    """ TODO (TESTED) """
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
    Unregister a VM given it's name
    """
    vm = getVMbyName(session,name)

    #if not vm:
    #    return (session,'undef')

    try:
        fn = vm.getConfig().getFiles().getVmPathName()
        vm.unregisterVM()
        return (session,fn)
    
    except MethodFault,detail:
        LOG.error("Error unregistering VM: %s. Reason: %s" % (name,detail.getMessage()))
        return (session,'undef')

def getStateVM(session,name):
    """
    Get the state of a given VM
    return (session,state) or (session,"error") if vm not found
    (TESTED)
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
    return (session, True|False)
    (TESTED)
    """
    s,state = getStateVM(session,name)
    if state == 'poweredOn':
        return (session,True)

    if state == 'pendingquestion':
        session = answerVM(session,name)
        session,state = getStateVM(session,name)
    
    vm = getVMbyName(session,name)
    task = vm.powerOnVM_Task(None)
    
    flag = __poll_task_for_question(task,session,name)
    #flag = task.waitForMe()

    if flag == Task.SUCCESS:
        return (session,True)
    else:
        croak("Could not start VM %s" % name)

def stopVM(session,name):
    """
    Stop a VM by name
    return (session, True|False)
    (TESTED)
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
    (TESTED)
    """
    vm = getVMbyName(session,name)

    try: 
        vm.rebootGuest()
        return (session,True)
    except:
        croak("Reboot failed for VM: %s!" % name)

def suspendVM(session,name):
    """
    (TESTED)
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
    (TESTED)
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
    srcname: is the name of the existing VM to clone
    dstname: is the name of the new directory to copy the VM to.
    returns (session,dstname) or (session,'undef') if the copy fails

    Steps:
    1. Generate a VMID if dstname wasn't given
    2. Check if the VM is registered. Then search the snapshot tree
    3. Check if vm is suspended or off If NOT suspend it
    4. Make a full copy of it
    5. register the copy
    6. If it was suspended reset it

    (TESTED)
    """
    if not srcname:
        LOG.error("Error cloning the VM: srcname wasn't specified")
        return (session,'undef')

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
            LOG.error("The dest_name %s matches a registered VM. Please use another name" % dstname)
            return (session,'undef')
        if __isSnapshotByName(session,dstname):
            LOG.error("The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname)
            return (session,'undef')

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
    (TESTED)
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
    (TESTED)
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

    # REWORK THIS BELOW. ERROR IS HAPPENING WHEN YOU PASS SNAP
    # to isBackingQuickClone(). Snapshot is NOT a VM...
    def findQuickCloneSnapshots(snap_list):
        for item in snap_list:

            oh_snap = item.getSnapshot()
            print "The snapshot is a %r" % oh_snap
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
    returns (session,{}) where the hash is {name of datastore: freespace}
    (TESTED)
    """
    results = {}

    vm = getVMbyName(session,name)

    #if not vm:
    #    print "VM %s not found!" % name
    #    return (session,False)

    for d in vm.getDatastores():
        info = d.getInfo()
        results[info.getName()] = info.getFreeSpace()

    return (session,results)

def getHostnameESX(session):
    """
    Get hostname of the ESX server. Although the search returns a list
    of HostSystems, we only check the first for the hostname
    returns (session,hostname) on success or (session,None) if hostname is not found
    (TESTED)
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
    returns (session,ip) on success or (session,None) if the IP address is not found
    (TESTED)
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
    vmname: the name of the VM
    returns (session,mac)
    (TESTED)
    """
    mac = None
    vm = getVMbyName(session,name)

    #if not vm:
    #    croak("Couldn't find VM %s" % name)
     
    nics = vm.getGuest().getNet()
    if nics and len(nics) > 0:
        mac = nics[0].getMacAddress()
        
    return (session,mac)

def getIPaddrVM(session,name):
    """
    Get the IP address for a VMs first NIC
    vmname: Is the name of the VM
    returns: (session,IP) on success or (session,None) on fail
    (TESTED)
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
    vmname: the name of the VM
    return (session,filename)
    (TESTED)
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
    vmname: the name of the VM
    returns the session on success or dies on failure
    (TESTED)
    """
    s,state = getStateVM(session,vmname)
    
    if state == 'poweredOn':
        #stop it
        stopVM(session,vmname)
    
    if isQuickCloneVM(s,vmname):
        LOG.info("Deleting VM %s" % vmname)
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

def snapshotVM(session,name,snapshot_name,desc,ignore_collisions=False):
    """
    Create a snapshot of an existing VM
    where - 
    name: the name of the snapshot to create
    snapshot_name: the name of the snapshot
    desc: a description of the snapshot
    ignore_collisions: whether to check for existing VMs and snapshots with the same name
    returns (session,snapshot name) on success and (session, 'undef') on failure
    (TESTED)
    """
    vm = getVMbyName(session,name)

    if not desc:
        desc = snapshot_name

    if not snapshot_name:
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
    elif not ignore_collisions:
        s,r1 = isRegisteredVM(session,dstname)
        if r1:
            LOG.error("The dest_name %s matches and existing VM. Please use another name" % dstname)
            return (session,'undef')
        if __isSnapshotByName(session,dstname):
            LOG.error("The dest_name %s matches and existing VM Snapshot name. Please use another name" % dstname)
            return (session,'undef')
    
    try:
        task = vm.createSnapshot_Task(snapshot_name,desc,True,True)
        if task.waitForMe() == Task.SUCCESS:
            return (session,snapshot_name)
        else:
            return (session,'undef')
    except MethodFault, detail:
        LOG.error("failed to create snapshot. Reason: %s" % detail)
        return (session,'undef')
    

def getAllSnapshotsVM(session,name):
    """
      Return the name of snapshots
      returns (session, hash {name:[]}) where 'name' id the name of a parent snapshot
      and '[]' is an array of the names of children of the parent snapshot
    """
    results = {}

    vm = getVMbyName(session,name)
    
    # This will fail if there's no snapshot
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

def renameSnapshotVM(session,vmname,old_name=None,new_name=None,desc=None):
    """
    Rename a snapshot
    vmname: the name of the VM containing the snapshot
    old_name: the name of the snapshot
    new_name: the new name, if blank a name will be generated
    desc: Add a description for the renamed VM (optional)
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

    snapshot_tree = None
    snapInfo = vm.getSnapshot()
    if snapInfo and snapInfo.getRootSnapshotList():
        snapshot_tree = __findSnapshot(snapInfo.getRootsnapshotList(),old_name)
    
    if not snapshot_tree:
        croak("Problem renaming the snapshot.  Snapshot: %s not found." % old_name)

    # Get the VirtualMachineSnapshot object.
    oh_snap = snapshot_tree.getSnapshot()
    snapshot = MorUtil.createExactManagedObject(session.getServerConnection(),oh_snap)
    
    try:
        snapshot.renameSnapshot(name_name,desc)
    except:
        croak("Error encountered remaining the snapshot")
    
    return (session,new_name)
    
    

def removeSnapshotVM(session,name,snapshot_name,removeChild=True):
    """
    Remove a given snapshot
    vmname: is the original name of the VM
    snapshot_name: is the name of the snapshot
    removeChild: Should I remove children on a snapshot?  Default: True
    returns (session,True) on success and (session,False) on failure
    """
    vm = getVMbyName(session,name)
    
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


def answerVM(session,name):
    """
    Tries to answer question posed by the server
    returns: session
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
    """
    rootFolder = session.getRootFolder()
    vm = InventoryNavigator(rootFolder).searchManagedEntity("VirtualMachine",name)

    if vm:
        return vm
    else:
        croak("VM name: %s not found" % name)


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
    s,list = getAllVMS(session)
    for vm in list:
        snShot = vm.getSnapshot()
        if snShot:
            snapTree = snShot.getRootSnapshotList()
            if snapTree:
                if __findByNameInSnapshotTree(snapTree,snapshot_name): 
                    return True
    return False
                                          
def __findByNameInSnapshotTree(snapTree,name):
    for node in snapTree:
        if name == node.getName():
            return True
        else:
            childTree = node.getChildSnapshotList()
            if childTree and len(childTree) > 0:
                found = __findByNameInSnapshotTree(childTree,name)
                if found: return True
    return False


#def __getSnapshotInTree(vm,snapshot_name):
#
#    if vm == None or snapshot_name == None:
#        print "Error missing VM and or snapshot_name"
#        return False
#
#    snapTree = vm.getSnapshot().getRootSnapshotList()
#    if snapTree:
#        return  __findSnapshotInTree(snapTree, snapshot_name)
#    else:
#        return None

def __findSnapshot(snapshot_list, snapshot_name):
    for snapshot_tree in snapshot_list:
        if snapshot_name == snapshot_tree.getName():
            return snapshot_tree
        else:
            # check the children
            childTree = snapshot_tree.getChildSnapshotList()
            if childTree:
                __findSnapshot(childTree, snapshot_name)
    return None


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
    #if not vm:
    #    print "No VirtualMachine found with name %s" % src_name
    #    return (session,'undef')

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


def croak(msg):
    """
    Helper method for logging an Error and exiting
    """
    LOG.error(msg)
    sys.exit(msg)


def __delete_filesVM(session,name):

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
    Checks for questions from ESX. This is a wrapper for the task
    param: t the task
    param: session the session
    params: vmname: The VM name
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

