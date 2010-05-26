
from com.vmware.vix import *
from honeyclient.manager import esx
from honeyclient.util.config import *
 
import sys
from datetime import datetime, timedelta
from time import sleep

class Clone(object):
    
    def __init__(self,**kwargs):
        """
        This replaces the 'new' call in the old Perl code
        """
        # Note ESX mod expects a URL while vix expects hostname/IP
        self.service_url = None

        # ESX username
        self.un = None
        
        # ESX password
        self.pw = None
        
        # A VIX host handle, used when accessing the VMware ESX server remotely.
        # (This internal variable should never be modified externally.)
        self.host_handle = VixHandle.VIX_INVALID_HANDLE
        
        # A VIX VM handle, used when accessing the VM on the VMware ESX server
        # remotely.  (This internal variable should never be modified externally.)
        self.vm_handle = VixHandle.VIX_INVALID_HANDLE
        
        # A variable, indicating when the last time the VIX host handle was updated.
        # (This internal variable should never be modified externally.)
        self.host_updated_at = None
        
        # A variable, indicating when the last time the VIX VM handle was updated.
        # (This internal variable should never be modified externally.)
        self.vm_updated_at = None
        
        # This comes from calling ESX getConfig in do_init
        self.vm_config = "[datastore1] Agent.Master-44-IE6/Agent.Master-44-IE6.vmx"
        
        # Vix login info
        self.guest_username = None
        self.guest_password = None
        
        # A variable specifying the temporary filename in the guest OS
        # which has the registry settings that force the application to
        # always display in a maximized state.
        self.maximize_registry_file = None

        # The name of the master VM, whose
        # contents will be the basis for each subsequently cloned VM.
        self.master_vm_name = getArg('master_vm_name','HoneyClient::Manager::ESX')
        
        
        # The name of the quick clone VM, whose
        # contents will be the basis this cloned VM.
        self.quick_clone_vm_name = None

        # A variable containing the MAC address of the cloned VM's primary
        # interface.
        self.mac_address = None
    
        # A variable containing the IP address of the cloned VM's primary
        # interface.
        self.ip_address = None
    
        # A variable containing the snapshot name the cloned VM.
        self.name = None

        # A variable reflecting the current status of the cloned VM.
        self.status = "uninitialized"

        # A variable reflecting the driver assigned to this cloned VM.
        self.driver_name = getArg("default_driver","HoneyClient::Agent")

        # A variable indicating the number of work units processed by this
        # cloned VM.
        self.work_units_processed = 0

        # A variable indicating the filename of the 'load complete' image
        # to use, when performing image analysis of the screenshot when
        # the application has successfully loaded all content.
        self.load_complete_image = None

        # A Vim session object, used as credentials when accessing the
        # VMware ESX server remotely.  (This internal variable
        # should never be modified externally.)
        self.vm_session = None

        # A Net::Stomp session object, used to interact with the 
        # HoneyClient::Manager::Firewall::Server daemon. (This internal variable
        # should never be modified externally.)
        self.firewall_session = None

        # A Net::Stomp session object, used to interact with the
        # HoneyClient::Manager::Pcap::Server daemon. (This internal variable
        # should never be modified externally.)
        self.pcap_session = None

        # A Net::Stomp session object, used to interact with the 
        # Drone server. (This internal variable
        # should never be modified externally.)
        self.emitter_session = None
        
        # A SOAP handle to the Agent daemon.  (This internal variable
        # should never be modified externally.)
        self.agent_handle = None

        # A variable indicated how long the object should wait for
        # between subsequent retries to any SOAP server
        # daemon (in seconds).  (This internal variable should never
        # be modified externally.)
        self.retry_period = 2

        # A variable indicating if the firewall should be bypassed.
        # (For testing use only.)
        self.bypass_firewall = False

        # A variable indicating if the cloned VM has been granted
        # network access.
        self.has_network_access = False

        # A variable indicating the number of snapshots currently
        # associated with this cloned VM.
        self.num_snapshots = 0

        # A variable indicating the number of failed retries in attempting
        # to contact the clone VM upon initialization.
        self.num_failed_inits = 0
        
        # A buffer, used to store the latest screenshot acquired via VIX.
        # (This internal variable should never be modified externally.)
        self.vix_image_bytes = None

        # A variable indicating how long to wait for each VIX call to finish.
        # (This internal variable should never be modified externally.)
        self.vix_call_timeout = getArg("vix_timeout","HoneyClient::Manager::ESX::Clone")

        # Update the internal dictionary with args passed in
        self.__dict__.update(kwargs)

        
        if not self.guest_username:
            self.__croak("Guest Username was not provided")
            
        if not self.guest_password:
            self.__croak("Guest Passeword was not provided")
            
        # TODO: Add code for loading 'complete_image' here

        if not self.vm_session:
            
            LOG.info("Creating a new ESX Session to %s" % self.service_url)
            self.vm_session = esx.login(self.service_url,self.un,self.pw)
            
            # notify drone about the new host
            s, hostname = esx.getHostnameESX(self.vm_session)
            s, ip = esx.getIPaddrESX(self.vm_session)
            
            LOG.info("Setup EventEmitter host with %s %s" % (hostname,ip))
            
        self.__check_space_available()
        
        # Connect (or reconnect) to host via VIX, if enabled.
        if int(getArg('vix_enable','HoneyClient::Manager::ESX::Clone')):
            self.vix_disconnect_vm()
            self.vix_disconnect_host()
            self.vix_connect_host()

        if self.bypass_firewall:
            LOG.info("TODO: Setup Firewall...")
        
        if self.num_snapshots >= getArg('max_num_snapshots','HoneyClient::Manager::ESX'):
            LOG.info("Suspending Clone VM. Reached the maximum number of snapshots")
            
            s,r = esx.suspendVM(self.vm_session,self.quick_clone_vm_name)
            
            self.quick_clone_vm_name = None
            self.name = None
            self.mac_address = None
            self.ip_address = None
            self.num_snapshots = 0
        
        if self.dont_init:
            return self
        else:
           self.do_init() 
           # TODO pickup here on error logic

    def __check_space_available(self):
        """
        Check to make sure there's enough free space in the ESX datastore
        IF NOT exit()
        """
        s, free_space = esx.getDatastoreSpaceAvailable(self.vm_session,self.master_vm_name)
        min_space_free = getArg('min_space_free','HoneyClient::Manager::ESX')
        
        if min_space_free == 'undef':
            self.__croak('Cannot determine the min_space_available in honeyclient.xml')
        
        min_space_free = int(min_space_free) * (1024 * 1024 * 1024)

        if free_space < min_space_free:
            store_free_space = free_space / (1024 * 1024 * 1024)
            self.__croak("Primary datastore has low disk space: %0.2f GBs" % store_free_space)


    def do_init(self):
        """
        replaces the 'init' call in the Perl code
        """
        if not self.quick_clone_vm_name or not self.name or not self.mac_address or not self.ip_address:
            LOG.info("Quick cloning master VM: %s" % self.master_vm_name)
            s, dest_name = esx.quickCloneVM(self.vm_session,self.master_vm_name)
            
            self.quick_clone_vm_name = dest_name
            self.num_snapshots += 1
            self.__change_status("initialized")

            registered = False
            while registered:
                s, registered = esx.isRegisteredVM(self.vm_session,self.quick_clone_vm_name)
                if not registered:
                    # poll for it
                    sleep( self.retry_period )
            
            LOG.info("Retrieving config of clone VM")
            s, self.vm_config = esx.getConfigVM(self.vm_session,self.quick_clone_vm_name)
            self.__change_status("registered")

            started = "no"
            while started != 'poweredon':
                s, started = esx.getStateVM(self.vm_session,self.quick_clone_vm)
                if started != 'poweredon':
                    sleep(self.retry_period)
            self.__change_status('running')

            LOG.info("No waiting on valid MAC/IP for clone")
            temp_ip = None
            while not self.ip_address or not self.mac_address:
                s, self.mac_address = esx.getMACaddrVM(self.vm_session,self.quick_clone_vm)
                s, temp_ip = esx.getIPaddrVM(self.vm_session,self.quick_clone_vm)
                
                if temp_ip and temp_ip != self.ip_address:
                    LOG.info("Cloned VM has a new IP")
                    
                    # TODO: call self._deny_network()
                    
                    self.ip_address = temp_ip

                if not self.ip_address or not self.mac_address:
                    # TODO: Pickup here
                    pass
                
            
            
            

    # Temp REMOVE THIS LATER
    def shutdown(self):
        self.vix_logout_from_guest()
        self.vix_disconnect_vm()
        self.vix_disconnect_host()
        
    # Replace with croak in 'config'
    def __croak(self,msg):
        """
        Helper to log errors and die
        msg: message to log
        """
        LOG.error(msg)
        sys.exit(msg)

    # VIX Calls...
    def vix_connect_host(self):
        """
        Connect to ESX Server
        """
        from urlparse import urlparse
        u = urlparse(self.host)
        try:
            self.host_handle =  VixVSphereHandle(u.hostname,self.un,self.pw)
            self.host_updated_at = datetime.now()
        except VixException, e:
            self.__croak("Error connecting to host: %s" % e.getMessage())
            
    def vix_disconnect_host(self):
        """ 
        Disconnect from the ESX Server
        """
        if not self.host_handle.equals(VixHandle.VIX_INVALID_HANDLE):
            self.host_handle.disconnect()
            self.host_handle = VixHandle.VIX_INVALID_HANDLE
        
    def vix_connect_vm(self):
        """
        Connect to a VM on host
        config_file: the full path to the .vmx file of the VM to connect with
        """
        if not self.host_handle or self.host_handle.equals(VixHandle.VIX_INVALID_HANDLE):
            self.__croak("Invalid Host Handle")
        try:
            self.vm_handle = self.host_handle.openVm(self.vm_config)
            self.vm_updated_at = datetime.now()
        except VixException:
            self.__croak("Error connecting to VM %s" % config_file)
                
    def vix_disconnect_vm(self):
        """
        Disconnect from the VM
        """
        if not self.vm_handle or self.vm_handle.equals(VixHandle.VIX_INVALID_HANDLE):
            pass
        else:
            self.vm_handle.release()
            self.vm_handle = VixHandle.VIX_INVALID_HANDLE
        

    def vix_is_host_valid(self):
        """
        Helper function to check if the current handle is valid.
        return True if valid else False
        """
        if not self.host_handle or self.host_handle.equals(VixHandle.VIX_INVALID_HANDLE):
            return False
        try:
            l = self.host_handle.getRegisteredVms()
            if len(l) > 0:
                return True
            else:
                return False
        except VixException:
            self.__croak("Error valid host call failed")
            
            
    def vix_is_vm_valid(self):
        """
        Helper function to test if the VM Handle is valid.  This deviates from
        the original Perl code and simply checks if the current vm_handle can return
        an IP address. If so, it's valid (True) else False
        """
        if not self.vm_handle or self.vm_handle.equals(VixHandle.VIX_INVALID_HANDLE):
            return False
        try:
            ip = self.vm_handle.getIpAddress()
            if ip:
                return True
            else:
                return False
        except VixException:
            self.__croak("Error VM Valid call failed")
            

    def vix_login_to_guest(self,bypass_validation=False):
        """
        Login to the Guest VM
        """
        try:
            # add hook to call validateHandles
            
            if not bypass_validation:
                self.vix_validate_handles(True)

            # Make seconds configurable
            self.vm_handle.waitForToolsInGuest(30)
            self.vm_handle.loginInGuest(self.guest_username,
                                        self.guest_password,
                                        VixConstants.VIX_LOGIN_IN_GUEST_REQUIRE_INTERACTIVE_ENVIRONMENT)
        except VixException, e:
            self.__croak("Error login to guest: %s" % e.getMessage())
    

    def vix_logout_from_guest(self):
        
        self.vix_validate_handles()
        try:
            self.vm_handle.logoutFromGuest()
        except VixException:
            self.__croak("Error logging out from Guest")
        
    def vix_validate_handles(self,bypass_login=False):
        
        # TEMP: Place holder for getArgs()
        session_timeout = 30

        if datetime.now() - timedelta(seconds=session_timeout) > self.host_updated_at:
            if not self.vix_is_host_valid():
                self.vix_disconnect_vm()
                self.vix_disconnect_host()
                self.vix_connect_host()
                self.vix_connect_vm()
                if not bypass_login:
                    self.vix_login_to_guest(True)
            else:
                self.host_updated_at = datetime.now()
                
        if datetime.now() - timedelta(seconds=session_timeout) > self.vm_updated_at:
            if not self.vix_is_vm_valid():
                self.vix_disconnect_vm()
                self.vix_connect_vm()
                if not bypass_login:
                    self.vix_login_to_guest(True)
            else:
                self.vm_updated_at = datetime.now()
    
    def vix_maximize_application(self):
        """
        Copy registry settings to the Agent to maximize the browser
        """
        self.vix_validate_handles()
        if not self.maximize_registry_file:
            # Create a temp file for the reg_file
            # Assumes we are already logged in to Guest via validate_handles
            temp_file = self.vm_handle.createGuestTempFile()
            # Copy it from Host to Guest
            self.vm_handle.copyFileFromHostToGuest("/home/daveb/test.txt",temp_file);
            
        self.vm_handle.runScriptInGuest("C:\WINDOWS\System32\cmd.exe","dir",True)

    def vix_capture_screen_image(self):
        pass

    def vix_drive_application(self):
        pass

    def vix_close_application(self):
        pass

    def drive(self):
        pass
    
    def suspend(self):
        pass

    def __change_status(self,value=None):
        if not value:
            self.__croak("Error. No status argument supplied")
        
        if self.status == "suspicious" or \
                self.status == "compromised" or \
                self.status = "error" or \
                self.status == "bug" or self.status == "deleted":
                
                return


        self.status = value
        
        if self.quick_clone_vm_name and self.name:
            LOG.info("TODO: contact the message client and event emitter")
            
    
    # Should this be __del__
    def destroy(self):
        pass
        
    
