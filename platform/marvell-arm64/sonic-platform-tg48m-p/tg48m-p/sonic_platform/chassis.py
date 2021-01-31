#!/usr/bin/env python

#############################################################################
#
# Module contains an implementation of SONiC Platform Base API and
# provides the platform information
#
#############################################################################

try:
    import os
    import sys
    import glob
    from sonic_platform_base.chassis_base import ChassisBase
    from sonic_platform.sfp import Sfp
    from sonic_platform.eeprom import Eeprom
    from sonic_platform.fan import Fan
    from .fan_drawer import RealDrawer, VirtualDrawer
    from sonic_platform.psu import Psu
    from sonic_platform.thermal import Thermal
    from sonic_platform.component import Component
    from sonic_daemon_base.daemon_base import Logger
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")


MAX_SELECT_DELAY = 3600
COPPER_PORT_START = 1
COPPER_PORT_END = 48
SFP_PORT_START = 49
SFP_PORT_END = 52
PORT_END = 52

# Device counts
MAX_FAN_DRAWER = 1
MAX_FAN = 3
MAX_PSU = 2
MAX_THERMAL = 6

# Temp - disable these to help with early debug
MAX_COMPONENT = 2

SYSLOG_IDENTIFIER = "chassis"
logger = Logger()

class Chassis(ChassisBase):
    """
    platform-specific Chassis class
        Derived from Dell S6000 platform.
        customized for the platform.
    """

    reset_reason_dict = {}
    reset_reason_dict[0x02] = ChassisBase.REBOOT_CAUSE_POWER_LOSS
    reset_reason_dict[0x20] = ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_ASIC

    reset_reason_dict[0x08] = ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_CPU
    reset_reason_dict[0x10] = ChassisBase.REBOOT_CAUSE_WATCHDOG

    def __init__(self):
        ChassisBase.__init__(self)

        #-------------------------------------------------------------------------
        # Port numbers for Initialize SFP list
        self.COPPER_PORT_START = COPPER_PORT_START
        self.COPPER_PORT_END = COPPER_PORT_END
        self.SFP_PORT_START = SFP_PORT_START
        self.SFP_PORT_END = SFP_PORT_END
        self.PORT_END = PORT_END

        # Until Chassis API is updated for non-sfp ports create dummy objects for copper / non-sfp ports
        for index in range(self.COPPER_PORT_START, self.COPPER_PORT_END+1):
            sfp_node = Sfp(index, 'COPPER', 'N/A' , 'N/A')
            self._sfp_list.append(sfp_node)

        # Mux Ordering
        mux_dev = sorted(glob.glob("/sys/class/i2c-adapter/i2c-1/i2c-[0-9]"))
        # Enable optoe2 Driver
        eeprom_path = "/sys/class/i2c-adapter/i2c-{0}/{0}-0050/eeprom"

	y = 0
        for index in range(self.SFP_PORT_START, self.SFP_PORT_END+1):
            mux_dev_num = mux_dev[y]
            port_i2c_map = mux_dev_num[-1]
            y = y + 1
            port_eeprom_path = eeprom_path.format(port_i2c_map)
            if not os.path.exists(port_eeprom_path):
	    	logger.log_info(" DEBUG - path %s -- did not exist " % port_eeprom_path )
            sfp_node = Sfp(index, 'SFP', port_eeprom_path, port_i2c_map )
            self._sfp_list.append(sfp_node)

        self.sfp_event_initialized = False
        #-------------------------------------------------------------------------

        # Instantiate ONIE system eeprom object
        self._eeprom = Eeprom()

        # Construct lists of fan drawers, fans, power supplies, thermal sensors,
        # and other chassis components
        drawer_num = MAX_FAN_DRAWER
        fan_num_per_drawer = MAX_FAN
        drawer_type = "virtual"
        drawer_ctor = VirtualDrawer

        fan_index = 0
        # Construct lists of fan drawers and fans
        for drawer_index in range(drawer_num):
            drawer = drawer_ctor(drawer_index)
            self._fan_drawer_list.append(drawer)
            for index in range(fan_num_per_drawer):
                fan = Fan(fan_index, drawer)
                fan_index += 1
                drawer._fan_list.append(fan)
                self._fan_list.append(fan)

        for i in range(MAX_PSU):
            psu = Psu(i)
            self._psu_list.append(psu)

        for i in range(MAX_THERMAL):
            thermal = Thermal(i)
            self._thermal_list.append(thermal)

        for i in range(MAX_COMPONENT):
            component = Component(i)
            self._component_list.append(component)


    def get_sfp(self, index):
        """
        Retrieves sfp represented by (1-based) index <index>

        Args:
            index: An integer, the index (1-based) of the sfp to retrieve.
            The index should be the sequence of physical SFP ports in a chassis,
            starting from 1.
            For example, 1 for first SFP port in the chassis and so on.

        Returns:
            An object dervied from SfpBase representing the specified sfp
        """
        sfp = None

        try:
            # The index will start from 1
            sfp = self._sfp_list[index-1]

        except IndexError:
            sys.stderr.write("SFP index {} out of range (1-{})\n".format(
                             index, len(self._sfp_list)))
        return sfp

    def get_name(self):
        """
        Retrieves the name of the chassis
        Returns:
            string: The name of the chassis
        """
        return self._eeprom.modelstr()

    def get_presence(self):
        """
        Retrieves the presence of the chassis
        Returns:
            bool: True if chassis is present, False if not
        """
        return True

    def get_model(self):
        """
        Retrieves the model number (or part number) of the chassis
        Returns:
            string: Model/part number of chassis
        """
        return self._eeprom.part_number_str()

    def get_serial(self):
        """
        Retrieves the serial number of the chassis (Service tag)
        Returns:
            string: Serial number of chassis
        """
        return self._eeprom.serial_str()

    def get_status(self):
        """
        Retrieves the operational status of the chassis
        Returns:
            bool: A boolean value, True if chassis is operating properly
            False if not
        """
        return True

    def get_base_mac(self):
        """
        Retrieves the base MAC address for the chassis

        Returns:
            A string containing the MAC address in the format
            'XX:XX:XX:XX:XX:XX'
        """
        return self._eeprom.base_mac_addr()

    def get_serial_number(self):
        """
        Retrieves the hardware serial number for the chassis

        Returns:
            A string containing the hardware serial number for this
            chassis.
        """
        return self._eeprom.serial_number_str()

    def get_system_eeprom_info(self):
        """
        Retrieves the full content of system EEPROM information for the
        chassis

        Returns:
            A dictionary where keys are the type code defined in
            OCP ONIE TlvInfo EEPROM format and values are their
            corresponding values.
        """
        return self._eeprom.system_eeprom_info()

    def get_reboot_cause(self):
        """
        Retrieves the cause of the previous reboot
        Returns:
            A tuple (string, string) where the first element is a string
            containing the cause of the previous reboot. This string must be
            one of the predefined strings in this class. If the first string
            is "REBOOT_CAUSE_HARDWARE_OTHER", the second string can be used
            to pass a description of the reboot cause.
        """

        #lrr = self._get_cpld_register('mb_reboot_cause')
        #if (lrr != 'ERR'):
        #    reset_reason = lrr
        #    if (reset_reason in self.reset_reason_dict):
        #        return (self.reset_reason_dict[reset_reason], None)
        #
        return (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, None)

    def get_change_event(self, timeout=0):
        """
        Returns a nested dictionary containing all devices which have
        experienced a change at chassis level

        Args:
            timeout: Timeout in milliseconds (optional). If timeout == 0,
                this method will block until a change is detected.

        Returns:
            (bool, dict):
                - True if call successful, False if not;
                - A nested dictionary where key is a device type,
                  value is a dictionary with key:value pairs in the format of
                  {'device_id':'device_event'},
                  where device_id is the device ID for this device and
                        device_event,
                             status='1' represents device inserted,
                             status='0' represents device removed.
                  Ex. {'fan':{'0':'0', '2':'1'}, 'sfp':{'11':'0'}}
                      indicates that fan 0 has been removed, fan 2
                      has been inserted and sfp 11 has been removed.
        """
        # Initialize SFP event first
        if not self.sfp_event_initialized:
            from sonic_platform.sfp_event import sfp_event
            self.sfp_event = sfp_event()
            self.sfp_event.initialize()
            self.MAX_SELECT_EVENT_RETURNED = self.PORT_END
            self.sfp_event_initialized = True

        wait_for_ever = (timeout == 0)
        port_dict = {}
        if wait_for_ever:
            # xrcvd will call this monitor loop in the "SYSTEM_READY" state
            # logger.log_info(" wait_for_ever get_change_event %d" % timeout)
            timeout = MAX_SELECT_DELAY
            while True:
                status = self.sfp_event.check_sfp_status( port_dict, timeout)
                if not port_dict == {}:
                    break
        else:
            # At boot up and in "INIT" state call from xrcvd will have a timeout value
            # return true without change after timeout and will transition to "SYSTEM_READY"
            # logger.log_info(" initial get_change_event %d" % timeout )
            status = self.sfp_event.check_sfp_status( port_dict, timeout)

        if status:
            return True, {'sfp':port_dict}
        else:
            return True, {'sfp':{}}



    def get_thermal_manager(self):
        from .thermal_manager import ThermalManager
        return ThermalManager