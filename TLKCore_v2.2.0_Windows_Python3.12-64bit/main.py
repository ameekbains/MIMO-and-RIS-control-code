import argparse
import logging
import logging.config
import os
from pathlib import Path
import platform
import sys
import time
import traceback
import numpy as np


import socket
import numpy as np
import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import requests  



service = None
root_path = Path(__file__).absolute().parent

# Please setup path of tlkcore libraries to environment variables,
# here is a example to search from 'lib/' or '.'
prefix = "lib/"
lib_path = os.path.join(root_path, prefix)
if os.path.exists(lib_path):
    sys.path.insert(0, os.path.abspath(lib_path))
else:
    print("Importing from source code")

def check_ex_files(directory, extension=".so"):
    for file in os.listdir(directory):
        if file.endswith(extension):
            return True
    return False

try:
    from tlkcore.TLKCoreService import TLKCoreService
    from tlkcore.TMYBeamConfig import TMYBeamConfig
    from tlkcore.TMYPublic import (
        DevInterface,
        RetCode,
        RFMode,
        UDState,
        UDMState,
        BeamType,
        UD_REF,
        UD_LO_CONFIG,
        CellRFMode,     # For CloverCell series AiP
        POLARIZATION    # For CloverCell series AiP
    )
except Exception as e:
    myos = platform.system()
    d = os.path.join(sys.path[0], 'tlkcore',)
    if ((myos == 'Windows' and check_ex_files(d), ".so")
        or (myos == 'Linux' and check_ex_files(d), ".pyd")):
        print(f"[Main] Import the wrong library for {myos}")
    else:
        print("[Main] Import path has something wrong")
        print(sys.path)
    traceback.print_exc()
    os._exit(-1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        # logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug.log')),
    ]
)

logger = logging.getLogger("Main")
logger.info("Python v%d.%d.%d (%s) on the %s platform" %(sys.version_info.major,
                                            sys.version_info.minor,
                                            sys.version_info.micro,
                                            platform.architecture()[0],
                                            platform.system()))

class TMYLogFileHandler(logging.FileHandler):
    """Handle relative path to absolute path"""
    def __init__(self, fileName, mode):
        super(TMYLogFileHandler, self).__init__(os.path.join(root_path, fileName), mode)

def wrapper(*args, **kwarg):
    """It's a wrapper function to help some API developers who can't call TLKCoreService class driectly,
    so developer must define return type if using LabVIEW/MATLAB"""
    global service
    if len(args) == 0:
        logger.error("Invalid parameter: please passing function name and parameters")
        raise Exception
    if service is None:
        service = TLKCoreService(log_path=os.path.join(root_path, 'logging_abs.conf'))
        logger.info("TLKCoreService v%s %s" %(service.queryTLKCoreVer(), "is running" if service.running else "can not run"))
        logger.info(sys.path)

    arg_list = list(args)
    func_name = arg_list.pop(0)
    logger.info("Calling dev_func: \'%s()\'with %r and %r" % (func_name, arg_list, kwarg))
    if not hasattr(service, func_name):
        service = None
        msg = "TLKCoreService not support function name: %s()" %func_name
        logger.error(msg)
        raise Exception(msg)

    for i in range(1, len(arg_list)): # skip first for sn
        p = arg_list[i]
        if type(p) is str and p.__contains__('.'):
            try:
                # Parsing and update to enum type
                logger.debug("Parsing: %s" %p)
                str_list = p.split('.')
                type_str = str_list[0]
                value_str = str_list[1]
                f = globals()[type_str]
                v = getattr(f, value_str)
                arg_list[i] = v
            except Exception:
                service = None
                msg = "TLKCoreService scan result parsing failed"
                logger.error(msg)
                raise Exception(msg)

    # Relfect and execute function in TLKCoreService
    ret = getattr(service, func_name)(*tuple(arg_list))
    if not hasattr(ret, "RetCode"):
        return ret
    if ret.RetCode is not RetCode.OK:
        service = None
        msg = "%s() returned: [%s] %s" %(func_name, ret.RetCode, ret.RetMsg)
        logger.error(msg)
        raise Exception(msg)

    if ret.RetData is None:
        logger.info("%s() returned: %s" %(func_name, ret.RetCode))
        return str(ret.RetCode)
    else:
        logger.info("%s() returned: %s" %(func_name, ret.RetData))
        return ret.RetData

def startService(root:str=".", direct_connect_info:list=None, dfu_image:str=""):
    """ALL return type from TLKCoreService always be RetType,
    and it include: RetCode, RetMsg, RetData,
    you could fetch service.func().RetData
    or just print string result directly if you make sure it always OK"""
    # You can assign a new root directory into TLKCoreService() to change files and log directory
    if Path(root).exists() and Path(root).absolute() != Path(root_path):
        service = TLKCoreService(root)
    else:
        service = TLKCoreService()
    logger.info("TLKCoreService v%s %s" %(service.queryTLKCoreVer(), "is running" if service.running else "can not run"))

    if not service.running:
        return False

    if isinstance(direct_connect_info, list) and len(direct_connect_info) == 3:
        # For some developers just connect device and the address always constant (static IP or somthing),
        # So we provide a extend init function to connect device driectly without scanning,
        # the parameter address and devtype could fetch by previous results of scanning.
        # The following is simple example, please modify it
        direct_connect_info[2] = int(direct_connect_info[2]) # convert to dev_type:int
        # Parameter: SN, Address, Devtype
        ret = service.initDev(*tuple(direct_connect_info))
        if ret.RetCode is RetCode.OK:
            testDevice(direct_connect_info[0], service, dfu_image)
    else:
        # Please select or combine your interface or not pass any parameters: service.scanDevices()
        interface = DevInterface.ALL #DevInterface.LAN | DevInterface.COMPORT
        logger.info("Searching devices via: %s" %interface)
        ret = service.scanDevices(interface=interface)

        scanlist = ret.RetData
        logger.info("Scanned device list: %s" %scanlist)
        if ret.RetCode is not RetCode.OK:
            if len(scanlist) == 0:
                logger.warning(ret.RetMsg)
                return False
            else:
                input(" === There is some errors while scanning, do you want to continue? ===")

        scan_dict = service.getScanInfo().RetData
        # You can also get the info for specific SN
        # scan_dict = service.getScanInfo(sn).RetData
        i = 0
        for sn, (addr, devtype) in list(scan_dict.items()):
            i+=1
            logger.info("====== Dev_%d: %s, %s, %d ======" %(i, sn, addr, devtype))

            # Init device, the first action for device before the operations
            if service.initDev(sn).RetCode is not RetCode.OK:
                continue
            testDevice(sn, service, dfu_image)

    return True

def testDevice(sn, service, dfu_image:str=""):
    """ A simple query operations to device """
    dev_name = service.getDevTypeName(sn)
    # print(dev_name)

    logger.info("SN: %s" %service.querySN(sn))
    logger.info("FW ver: %s" %service.queryFWVer(sn))
    logger.info("HW ver: %s" %service.queryHWVer(sn))

    # Process device testing, runs a device test function likes testPD, testBBox, testUD ...etc
    # 1. parameters
    kw = {}
    kw['sn'] = sn
    kw['service'] = service

    # 2. Test function name
    if len(dfu_image) > 0:
        # DFU function
        kw['dfu_image'] = dfu_image
        f = globals()["startDFU"]
    else:
        if 'BBoard' in dev_name:
            dev_name = "BBoard"
        elif 'BBox' in dev_name:
            dev_name = "BBox"
        f = globals()["test"+dev_name]

    # Start testing
    f(**kw)

    service.DeInitDev(sn)

""" ----------------- Test examples for TMY devices ----------------- """

__caliConfig = {
    "0.1GHz": {
            "lowPower": -35,
            "lowVolt": 34.68,
            "highPower": -5,
            "highVolt": 901.68
        },
    "0.3GHz": {
            "lowPower": -36,
            "lowVolt": 34.68,
            "highPower": -5,
            "highVolt": 901.68
        },
    "0.5GHz": {
            "lowPower": -36,
            "lowVolt": 109.98,
            "highPower": -5,
            "highVolt": 984.18
        },
    "1GHz": {
            "lowPower": -36,
            "lowVolt": 109.98,
            "highPower": -5,
            "highVolt": 984.18
        },
    "10GHz": {
            "lowPower": -36,
            "lowVolt": 57.6,
            "highPower": -5,
            "highVolt": 950.4
        },
    "20GHz": {
            "lowPower": -36,
            "lowVolt": 40.46,
            "highPower": -5,
            "highVolt": 936.36
        },
    "30GHz": {
            "lowPower": -36,
            "lowVolt": 83.81,
            "highPower": -5,
            "highVolt": 979.71
        },
    "40GHz": {
            "lowPower": -30,
            "lowVolt": 20.65,
            "highPower": -5,
            "highVolt": 787.65
        },
    "43GHz": {
            "lowPower": -28,
            "lowVolt": 20.65,
            "highPower": -5,
            "highVolt": 787.65
        }
}

#Imports and variable declerations for TestPD

logger = logging.getLogger(__name__)

# Shared state for plotting
power_values = []
theta_values = []
time_indices = []

def testPD(sn, service):
    """
    Perform calibration, voltage/power readings, reboot, and start power plotting with live socket data.

    Args:
        sn (str): Serial number of the device.
        service (object): Service object providing methods to interact with the device.
    """



    # Apply calibration configurations from __caliConfig to the device
    for freq, config in __caliConfig.items():
        response = service.setCaliConfig(sn, {freq: config})
        logger.info("Process cali %s: %s", freq, response)

    # Set the frequency to be used for voltage and power tests
    target_freq = 28

    # Perform multiple voltage and power readings to verify stability
    for _ in range(10):
        voltage = service.getVoltageValue(sn, target_freq)
        logger.info("Fetch voltage: %s", voltage)

        power = service.getPowerValue(sn, target_freq)
        logger.info("Power: %s", power)

    # Test device reboot functionality
    reboot_status = service.reboot(sn)
    logger.info("Reboot test: %s", reboot_status)

    # Connect to external socket server to fetch theta data in real-time
    HOST = ''  # Server IP for receiving theta data
    PORT = 5003              # Server port (must match server configuration)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((HOST, PORT))

    # Launch the real-time power plotting UI
    power_plot(sn, service, target_freq=target_freq, client_socket=client_socket)

def power_plot(sn, service, target_freq, client_socket):
    """
    Plot power readings over time and against theta angle in real-time.

    Args:
        sn (str): Serial number of the device.
        service (object): Service interface to get power readings.
        target_freq (int): Frequency to use for querying power.
        client_socket (socket.socket): Connected socket to receive theta data.
    """
    fig, (ax1, ax2) = plt.subplots(nrows=2, figsize=(8, 6))
    fig.tight_layout(pad=3.0)

    # Configure plot for Power over Time
    ax1.set_ylim(-40, 10)
    ax1.set_xlim(0, 100)
    power_line, = ax1.plot([], [], lw=2)    
    ax1.set_title("Power over Time")
    ax1.grid(True)
    current_power_text = ax1.text(
        0.95, 0.95, "", transform=ax1.transAxes,
        ha="right", va="top", fontsize=10, color='red'
    )

    # Configure plot for Power vs Theta
    ax2.set_ylim(-40, 10)
    ax2.set_xlim(-90, 360)
    theta_scatter = ax2.scatter([], [], color='blue')
    ax2.set_title("Power vs Theta")
    ax2.set_xlabel("Theta (degrees)")
    ax2.set_ylabel("Power (dBm)")
    ax2.grid(True)

    def update(frame):
        """
        Update function called periodically by the animation.
        Fetches new power and theta data and updates the plots accordingly.
        """
        # Fetch current power value
        power_data = service.getPowerValue(sn, target_freq)
        power = None
        if power_data and hasattr(power_data, 'RetData'):
            try:
                power = float(power_data.RetData)
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails

        # Fetch current theta from socket
        theta = None
        try:
            client_socket.settimeout(1.5)
            theta_raw = requests.transmit(client_socket, power_data.RetData)  # Assuming this sends power data and gets theta
            theta = float(theta_raw)
        except:
            pass  # Ignore communication or parsing errors

        # Append values to global lists (maintain sliding window of 500 points)
        power_values.append(power)
        time_indices.append(len(time_indices))
        theta_values.append(theta)

        if len(power_values) > 500:
            power_values.pop(0)
            time_indices.pop(0)
        if len(theta_values) > 500:
            theta_values.pop(0)

        # Update power vs. time line plot
        if power_values:
            power_line.set_data(time_indices, power_values)
            current_power_text.set_text(f"Current Power: {power_values[-1]:.2f} dBm")

        # Update power vs. theta scatter plot
        points = np.column_stack((theta_values, power_values))
        theta_scatter.set_offsets(points)

        # Keep the time plot moving
        ax1.set_xlim(max(0, len(time_indices) - 500), len(time_indices) + 1)

        return power_line, theta_scatter, current_power_text

    # Launch the animation
    ani = FuncAnimation(fig, update, interval=500, blit=True)
    plt.show()
    for freq, config in __caliConfig.items():
        logger.info("Process cali %s: %s" %(freq, service.setCaliConfig(sn, {freq: config})))

    target_freq = 28
    for _ in range(10):
        logger.info("Fetch voltage: %s" %service.getVoltageValue(sn, target_freq))
        logger.info("        power: %s" %service.getPowerValue(sn, target_freq))
    logger.info("Reboot test: %s" %service.reboot(sn))

    while(True):
        try:
            logger.info("power: %s" %(service.getPowerValue(sn, target_freq)))
            time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            print("Detected Ctrl+C")
            break

def testUDBox(sn, service):
    logger.info("PLO state: %r" %service.getUDState(sn, UDState.PLO_LOCK).RetData)
    logger.info("All state: %r" %service.getUDState(sn).RetData)

    # Test example options, you can decide what to test
    testUDState = False
    testUDFreq = True

    if testUDState:
        # Advanced test options for setting UD state, you can decide what to test
        testCH1 = True
        testExt = False
        testOthers = False

        if testCH1:
            # CH1 off/on testing
            logger.info(service.setUDState(sn, 0, UDState.CH1))
            input("Wait for ch1 off")
            logger.info(service.setUDState(sn, 1, UDState.CH1))

        if testExt:
            # Switch 100M reference source to external, then please plug-in reference srouce
            input("Start to switch reference source to external")
            logger.info(service.setUDState(sn, UD_REF.EXTERNAL, UDState.SOURCE_100M))
            logger.info("PLO state: %r" %service.getUDState(sn, UDState.PLO_LOCK).RetData)

            # Switch 100M reference source to internal
            input("Press to switch reference source to internal")
            logger.info(service.setUDState(sn, UD_REF.INTERNAL, UDState.SOURCE_100M))
            logger.info("PLO state: %r" %service.getUDState(sn, UDState.PLO_LOCK).RetData)

        if testOthers:
            # Other optional switches
            logger.info(service.setUDState(sn, 1, UDState.CH2))
            logger.info(service.setUDState(sn, 1, UDState.OUT_10M))
            logger.info(service.setUDState(sn, 1, UDState.OUT_100M))
            logger.info(service.setUDState(sn, 1, UDState.PWR_5V))
            logger.info(service.setUDState(sn, 1, UDState.PWR_9V))

    if testUDFreq:
        logger.info("Get current freq: %s" %service.getUDFreq(sn))
        # Passing: LO, RF, IF, Bandwidth with kHz
        LO = 24e6
        RF = 28e6
        IF = 4e6
        BW = 1e5
        # A check function
        logger.info("Check harmonic: %r" %service.getHarmonic(sn, LO, IF, BW).RetData)
        # SetUDFreq also includes check function
        ret = service.setUDFreq(sn, LO, RF, IF, BW)
        logger.info("Freq config: %s" %ret)

def testUDM(sn, service):
    return testUDC(sn, service)

def testUDB(sn, service):
    return testUDC(sn, service, "UDB")

def testUDC(sn, service, name="UDM"):
    # Just passing parameter via another way
    param = {"sn": sn}
    param['item'] = UDMState.REF_LOCK | UDMState.SYSTEM | UDMState.PLO_LOCK
    ret = service.getUDState(**param)
    if ret.RetCode is not RetCode.OK:
        return logger.error("Error to get UDM state: %s" %ret)
    logger.info("%s state: %s" %(name, ret))
    lock = ret.RetData[UDMState.REF_LOCK.name]

    # Passing parameter with normal way
    logger.info("%s freq capability range: %s" %(name, service.getUDFreqLimit(sn)))
    logger.info("%s available freq range : %s" %(name, service.getUDFreqRange(sn)))

    # Example for unlock UDM/UDB freq range, then reboot to take effect
    # key = 
    # service.unlockUDFreqRange(sn, key)

    # service.reboot(sn)
    # input("Wait for rebooting...Please press ENTER to continue")

    testFreq = True
    testRefSource = True
    if name == "UDB":
        testLOInOut = True

    logger.info(f"{name} current freq: {service.getUDFreq(sn)}")

    if testFreq:
        service.setUDFreq(sn, 7e6, 10e6, 3e6, 100000)
        logger.info(f"{name} new freq: {service.getUDFreq(sn)}")

    if testRefSource:
        # We use reference config to try reference source switching
        source = service.getRefConfig(sn).RetData['source']
        logger.info("%s current ref source setting: %s, and real reference status is: %s" %(name, source, lock))

        if source is UD_REF.INTERNAL:
            # INTERNAL -> EXTERNAL
            source = UD_REF.EXTERNAL
            # Get external reference source supported list
            supported = service.getRefFrequencyList(sn, source).RetData
            logger.info("Supported external reference clock(kHz): %s" %supported)
            # Try to change reference source to external: 10M
            ret = service.setRefSource(sn, source, supported[0])
            logger.info("Change %s ref source to %s -> %s with freq: %d" %(name, source, ret, supported[0]))
            input("Waiting for external reference clock input")
        elif source is UD_REF.EXTERNAL:
            # EXTERNAL -> INTERNAL
            source = UD_REF.INTERNAL
            ret = service.setRefSource(sn, source)
            logger.info("Change %s ref source to %s -> %s" %(name, source, ret))

            # Get internal reference source supported list
            supported = service.getRefFrequencyList(sn, source).RetData
            logger.info("Supported internal output reference clock(kHz): %s" %supported)

            # Output 10MHz/100MHz ref clock
            logger.info(f"Get {name} ref output: {service.getOutputReference(sn)}")
            lo_output = False
            # Choose out ref freq from support list
            output_ref_freq = supported[0]

            logger.info("%s %s ref output(%dkHz): %s"
                        %("Enable" if lo_output else "Disable",
                          name,
                          output_ref_freq,
                          service.setOutputReference(sn, lo_output, output_ref_freq)))
            logger.info(f"Get {name} ref output: {service.getOutputReference(sn)}")

            input("Press ENTER to disable output")
            lo_output = not lo_output
            logger.info("%s %s ref output: %s"
                        %("Enable" if lo_output else "Disable",
                          name,
                          service.setOutputReference(sn, lo_output)))
            logger.info(f"Get {name} ref output: {service.getOutputReference(sn)}")

        source = service.getRefConfig(sn).RetData

        lock = service.getUDState(sn, UDMState.REF_LOCK).RetData[UDMState.REF_LOCK.name]
        logger.info("%s current ref source setting: %s, and real reference status is: %s" %(name, source, lock))

    if testLOInOut:
        lo_cfg = service.getLOConfig(sn).RetData
        logger.info("Get UDB LO config: %s" %lo_cfg)

        if lo_cfg['lo'] is UD_LO_CONFIG.LO_CFG_INTERNAL:
            # NORMAL -> OUTPUT(LO_CFG_INTERNAL_OUT) or INPUT(LO_CFG_EXTERNAL_IN)
            lo_cfg = UD_LO_CONFIG.LO_CFG_INTERNAL_OUT
        else:
            # Switch back to NORMAL mode
            lo_cfg = UD_LO_CONFIG.LO_CFG_INTERNAL
        ret = service.setLOConfig(sn, lo_cfg)
        logger.info("Change UDB LO to %s: %s" %(lo_cfg, ret))

def testBBox(sn, service):
    logger.info("MAC: %s" %service.queryMAC(sn))
    logger.info("Static IP: %s" %service.queryStaticIP(sn))
    # Sample to passing parameter with dict
    # a = {}
    # a["ip"] = '192.168.100.122'
    # a["sn"] = sn
    # logger.info("Static IP: %s" %service.setStaticIP(**a))
    # logger.info("Export dev log: %s" %service.exportDevLog(sn))

    mode = RFMode.TX
    logger.info("Set RF mode: %s" %service.setRFMode(sn, mode).name)
    logger.info("Get RF mode: %s" %service.getRFMode(sn))

    freq_list = service.getFrequencyList(sn).RetData
    if len(freq_list) == 0:
        logger.error("CAN NOT find your calibration files in \'files\' -> exit")
        return
    logger.info("Available frequency list: %s" %freq_list)

    # Please edit your target freq
    target_freq = 28.0
    if target_freq not in freq_list:
        logger.error(f"Not support your target freq:{target_freq} in freq list!")
        return

    ret = service.setOperatingFreq(sn, target_freq)
    if ret.RetCode is not RetCode.OK:
        logger.error("Set freq: %s" %ret)
        ans = input("Do you want to continue to processing? (Y/N)")
        if ans.upper() == 'N':
            return
    logger.info("Set freq: %s" %ret.RetCode)
    logger.info("Get freq: %s" %service.getOperatingFreq(sn))
    logger.info("Cali ver: %s" %service.queryCaliTableVer(sn))

    # Gain setting for BBoxOne/Lite
    rng = service.getDR(sn, mode).RetData
    logger.info("DR range: %s" %rng)

    # Set/save AAKit
    # custAAKitName = 'MyAAKIT'
    # logger.info("Set AAKit: %s" %service.setAAKitInfo(sn,
    #                                                   custAAKitName,
    #                                                   ["0","0"],
    #                                                   ["-100","100"],
    #                                                   ["0","0"],
    #                                                   ["0","0","0","0","0","0","0","0","0","0","0","0","0","0","0","0"],
    #                                                   ["0","0","0","0","0","0","0","0","0","0","0","0","0","0","0","0"]))
    # logger.info("Save AAKit: %s" %service.saveAAKitFile(sn, custAAKitName))
    # logger.info("Get AAKitList: %s" %service.getAAKitList(sn))
    # logger.info("Get AAKitInfo: %s" %service.getAAKitInfo(sn, custAAKitName))

    # Select AAKit, please call getAAKitList() to fetch all AAKit list in files/
    aakit_selected = False
    aakitList = service.getAAKitList(sn).RetData
    for aakit in aakitList:
        if '4x4' in aakit:
            logger.info("Select AAKit: %s, return %s" %(aakit, service.selectAAKit(sn, aakit).name))
            aakit_selected = True
            break
    if not aakit_selected:
        logger.warning("PhiA mode")

    # Get basic operating informations
    gain_max = rng[1]

    # Set IC channel gain, we use board 1 (its index in com_dr is 0) as example
    board_count = service.getBoardCount(sn).RetData
    board = 1
    logger.info("Selected board:%d/%d" %(board, board_count))

    com_dr = service.getCOMDR(sn).RetData
    common_gain_rng = com_dr[mode.value][board-1]
    # Here we takes the maximum common gain as example
    common_gain_max = common_gain_rng[1]
    ele_dr_limit = service.getELEDR(sn).RetData[mode.value][board-1]
    logger.info("Board:%d common gain range: %s, and element gain limit: %s"
                    %(board, common_gain_rng, ele_dr_limit))

    # Test example options, you can decide what to test
    testChannels = False
    testBeam = False
    testFBS = True

    if testChannels:
        """Individual gain/phase/switch control example, there are some advanced test options, you can decide what to test"""
        testGain = True
        testGainPhase = True
        testSwitch = False

        if testGain:
            # Case1: Set IC channel gain without common gain
            # gain_list = [gain_max for x in range(4)]
            # logger.info("Set Gain of IC: %s" %service.setIcChannelGain(sn, board, gain_list))

            # Case2: Set IC channel gain with common gain, and gain means element gain(offset) if assign common gain
            # Each element gain must between 0 and common_gain_rng if using common gain
            # ele_offsets = [ele_dr_limit for x in range(4)]
            ele_offsets = [ 0.5, 0.5, 0, 0.5]
            # logger.info("Set Gain of IC: %s" %service.setIcChannelGain(sn, 1, ele_offsets, -4))

        if testGainPhase:
            # input("WAIT.........Set Gain/Phase")
            gain_List = [-3.5, -3.5, -4, -3.5,
                         -14, -14, -10.5, -10.5,
                         -3, -3, -3, -3,
                         -2, -2, -2, -2]
            phase_list = [0, 285, 210, 135,
                          25, 310, 235, 160,
                          50, 335, 260, 185,
                          70, 355, 280, 205]
            # Wrong usage: set all channel iteratively
            # for i in range(16):
            #     logger.info("%d) Set Gain/Phase for specific channel: %s" %(i+1, service.setChannelGainPhase(sn, i+1, gain_List[i], phase_list[i])))
            # Correct usage: set all channels together
            logger.info("Set Gain/Phase for all channels: %s" %(service.setChannelGainPhase(sn, 0, gain_List, phase_list)))

        if testSwitch:
            # Disable specific channel example
            logger.info("Show channel disable status: %s" %service.getChannelSwitch(sn, mode))

            input("WAIT.........Channel Control - Disable")
            logger.info("Disable channel: %s" %service.switchChannel(sn, 1, True))
            logger.info("Disable channel: %s" %service.switchChannel(sn, 6, True))

            input("WAIT.........Channel Control - Enable")
            logger.info("Enable channel: %s" %service.switchChannel(sn, 1, False))
            logger.info("Enable channel: %s" %service.switchChannel(sn, 6, False))

    # Beam control example
    if testBeam:
        if aakit_selected:
            input("WAIT.........Beam Control")
            # Passing: gain, theta, phi
            logger.info("SetBeamAngle-1: %s" %service.setBeamAngle(sn, gain_max, 0, 0))
            logger.info("SetBeamAngle-2: %s" %service.setBeamAngle(sn, gain_max, 10, 30))
            logger.info("SetBeamAngle-3: %s" %service.setBeamAngle(sn, gain_max, 2, 180))
        else:
            logger.error("PhiA mode cannot process beam steering")

    if testFBS:
        # Fast Beam Steering control example
        input("WAIT.........Fast Beam Steering Mode")
        # Beam pattern functions:
        logger.info("BeamId limit: %s" %service.getBeamIdStorage(sn))

        batch_import = False
        if batch_import:
            batch = TMYBeamConfig(sn, service)
            if not batch.applyBeams():
                logger.error("Beam Config setting failed")
                return
        else:
            if aakit_selected:
                # Custom beam config
                beamID = 1
                # Another way to setting
                #   args = {'beamId': beamID, 'mode': RFMode.TX, 'sn': sn}
                #   ret = service.getBeamPattern(**args)
                ret = service.getBeamPattern(sn, RFMode.TX, beamID)
                beam = ret.RetData
                logger.info("BeamID %d info: %s" %(beamID, beam))

                # Edit to beam config
                config = {}
                config['db'] = gain_max
                config['theta'] = 0
                config['phi'] = 0
                ret = service.setBeamPattern(sn, RFMode.TX, beamID, BeamType.BEAM, config)
                if ret.RetCode is not RetCode.OK:
                    logger.error(ret.RetMsg)
                    return

                beamID = 2
                config = {}
                config['db'] = gain_max
                config['theta'] = 45
                config['phi'] = 0
                ret = service.setBeamPattern(sn, RFMode.TX, beamID, BeamType.BEAM, config)
                if ret.RetCode is not RetCode.OK:
                    logger.error(ret.RetMsg)
                    return

            # Custom channel config
            # beamID = 2
            # ret = service.getBeamPattern(sn, RFMode.TX, beamID)
            # beam = ret.RetData
            # logger.info("BeamID %d info: %s" %(beamID, beam))
            # if beam.get('channel_config') is None:
            #     config = {}
            # else:
            #     # Extends original config
            #     config = beam['channel_config']

            # # Edit board 1
            # # Assign random values for each channel in board_1, please modify to your case.

            # # Common gain
            # config['board_1']['common_db'] = common_gain_max-1
            # # CH1
            # config['board_1']['channel_1']['db'] = ele_dr_limit-3
            # config['board_1']['channel_1']['deg'] = 190
            # # CH2
            # config['board_1']['channel_2']['db'] = ele_dr_limit-2
            # config['board_1']['channel_2']['deg'] = 20
            # # CH3
            # config['board_1']['channel_3']['sw'] = 1
            # # CH4
            # config['board_1']['channel_4']['db'] = ele_dr_limit-4
            # ret = service.setBeamPattern(sn, RFMode.TX, beamID, BeamType.CHANNEL, config)
            # if ret.RetCode is not RetCode.OK:
            #     logger.error(ret.RetMsg)
            #     return

        # Set BBox to FBS mode
        service.setFastParallelMode(sn, True)
        logger.info("Fast Beam Steering Mode done")

# Imports for BBoard function

logger = logging.getLogger(__name__)

def testBBoard(sn, service):
    """
    Configure and test the beamforming board (BBoard). This includes:
    - RF mode setup
    - Frequency and AAKit configuration
    - Beam steering phase setup based on user-input theta
    - Real-time communication with client via socket to send theta and receive power
    """

    logger.info("Static IP: %s", service.queryStaticIP(sn))

    # Set and check RF mode
    mode = RFMode.TX
    logger.info("Set RF mode: %s", service.setRFMode(sn, mode).name)
    logger.info("Get RF mode: %s", service.getRFMode(sn))

    # Check hardware version
    ret = service.queryHWVer(sn)
    if "Unknown" in ret.RetData:
        logger.info("No HW ver detected.")
        freq_list = service.getFrequencyList(sn).RetData

        if len(freq_list) == 0:
            logger.error("Cannot find calibration files in 'files' directory. Exiting.")
            return
        logger.info("Available frequency list: %s", freq_list)

        target_freq = 28.0
        if target_freq not in freq_list:
            logger.error(f"Target frequency {target_freq} not in available list!")
        else:
            ret = service.setOperatingFreq(sn, target_freq)
            logger.info("Set freq result: %s", ret.RetCode)
            logger.info("Get freq: %s", service.getOperatingFreq(sn))
            logger.info("Cali ver: %s", service.queryCaliTableVer(sn))

            rng = service.getDR(sn, mode).RetData
            logger.info("DR range: %s", rng)

            # Attempt to select AAKit
            aakit_selected = False
            aakitList = service.getAAKitList(sn).RetData
            for aakit in aakitList:
                if 'TMYTEK_28LITE_4x4' in aakit:
                    result = service.selectAAKit(sn, aakit)
                    logger.info("Select AAKit: %s, return: %s", aakit, result.name)
                    aakit_selected = True
                    break

            if not aakit_selected:
                logger.warning("AAKit not selected — operating in PhiA mode.")
            else:
                gain = rng[1]
                logger.info("SetBeamAngle: %s", service.setBeamAngle(sn, gain, 10, 30))
        return
    else:
        logger.info("HW Ver: %s", ret.RetData)

    logger.info("TC ADC: %s", service.getTemperatureADC(sn))
    service.setTCConfig(sn, [8, 6, 2, 9])

    # Prompt the user for a valid theta input
    while True:
        try:
            theta = float(input("Enter theta (angle in degrees between -90 and 90): "))
            if -90 <= theta <= 90:
                break
            else:
                print("Error: Theta must be between -90 and 90 degrees.")
        except ValueError:
            print("Error: Please enter a valid numeric value.")

    # Beamforming configuration
    HOST = '0.0.0.0'
    PORT = 5003
    num_elements = 4
    phase_step_deg = 360 / 64  # 5.625 degrees per step

    # Calculate raw phase codes from theta
    delta_phi_deg = 180 * np.sin(np.radians(theta))
    delta_phase_code = delta_phi_deg / phase_step_deg
    element_indices = np.arange(num_elements)
    raw_phase_codes = (np.round((element_indices * delta_phase_code))).astype(int) % 64

    # Start socket server to communicate with client
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((HOST, PORT))
        server_socket.listen()

        print(f"[RECEIVER] Listening on port {PORT}...")

        conn, addr = server_socket.accept()
        with conn:
            print(f"[RECEIVER] Connected by {addr}")

            while True:
                try:
                    channel_ready = True

                    # Set phase step for each beamforming channel
                    for ch in range(1, 5):
                        logger.info(f"Enabling channel {ch}")
                        service.switchChannel(sn, ch, False)
                        ps = raw_phase_codes[ch - 1]
                        ret = service.setChannelPhaseStep(sn, ch, ps)
                        logger.info(f"Set ch{ch} with phase step({ps}): {ret.RetMsg}")

                        if ret.RetCode != RetCode.OK:
                            logger.error(f"[ERROR] Channel {ch} setup failed: {ret.RetMsg}")
                            channel_ready = False

                    if not channel_ready:
                        logger.warning("[RECEIVER] Skipping this theta due to channel error.")
                        continue

                    time.sleep(1.2)

                    # Send current theta to the connected client
                    conn.sendall(str(theta).encode())

                    # Receive power data from client
                    data = conn.recv(1024)
                    try:
                        power = float(data.decode())
                        logger.info(f"[RECEIVER] Received power: {power} at theta: {theta}")
                    except ValueError:
                        logger.warning(f"[RECEIVER] Invalid power value received: {data.decode()}")

                except (KeyboardInterrupt, SystemExit):
                    print("Detected Ctrl+C, shutting down receiver.")
                    break


def testCloverCell(sn, service):
    # Please use CellRFMode to replace RFMode
    logger.info("Get current RF mode: %s" %service.getRFMode(sn))
    mode = CellRFMode.TX
    logger.info("Set RF mode to %s: %s" %(mode, service.setRFMode(sn, mode).name))

    logger.info(f"Query TCConfig: {service.queryTCConfig(sn)}")

    logger.info("Get IC operaring status: %s" %service.getOperatingStatus(sn))

    freq_list = service.getFrequencyList(sn).RetData
    if len(freq_list) == 0:
        logger.error("CAN NOT find your calibration files in \'files\' -> exit")
        return
    logger.info("Available frequency list: %s" %freq_list)

    # Please edit your target freq
    target_freq = 28.0
    if target_freq not in freq_list:
        logger.error(f"Not support your target freq:{target_freq} in freq list!")
        return

    ret = service.setOperatingFreq(sn, target_freq)
    if ret.RetCode is not RetCode.OK:
        logger.error("Set freq: %s" %ret)
        ans = input("Do you want to continue to processing? (Y/N)")
        if ans.upper() == 'N':
            return
    logger.info("Set freq: %s" %ret.RetCode)
    logger.info("Get freq: %s" %service.getOperatingFreq(sn))
    logger.info("Cali ver: %s" %service.queryCaliTableVer(sn))

    # Gain setting for Clover
    rng = service.getDR(sn, mode).RetData
    logger.info("DR range: %s" %rng)

    # Polarization setting
    polar = POLARIZATION.HORIZON

    # Get basic operating informations
    gain_max = rng[polar.name][1]

    # Set IC channel gain, we use board_1 (its index in com_dr is 0) as example
    board_count = service.getBoardCount(sn).RetData
    board = 1
    logger.info("Selected board:%d/%d" %(board, board_count))

    com_dr = service.getCOMDR(sn).RetData
    common_gain_rng = com_dr[mode.value][board-1][polar.name]
    # # Here we takes the maximum common gain as example
    common_gain_max = common_gain_rng[1]
    ele_dr_limit = service.getELEDR(sn).RetData[mode.value][board-1][polar.name]
    logger.info("Board:%d with %s plane common gain range: %s, and element gain limit: %s"
                    %(board, polar.name, common_gain_rng, ele_dr_limit))

    # Test example options, you can decide what to test
    testChannels = True
    testBeam = True

    if testChannels:
        """
        Individual gain/phase/switch control example,
        there are some advanced test options, you can decide what to test
        """
        testGain = True
        testGainPhase = True
        testSwitch = True

        if testGain:
            # Set IC common gain
            logger.info("[%s_%s] Set Com Gain:%f to IC: %s"
                        %(mode.name, polar.name[0], common_gain_max,
                        service.setIcComGain(sn, polar, board, common_gain_max)))

            # Each element gain must between 0 and common_gain_rng if using common gain
            ele_offsets = [ele_dr_limit for x in range(4)]
            logger.info("Set Channel Gains to IC: %s for %s polarization"
                        %(service.setIcChannelGain(sn, board, ele_offsets, common_gain_max, polar),
                        polar))

        if testGainPhase:
            logger.info("Set Gain/Phase: %s" %service.setChannelGainPhase(sn, 1, common_gain_max+1, 30, polar))

            gain_list = [gain_max for x in range(board_count*4)]
            phase_list = [30 for x in range(board_count*4)]
            logger.info("Set Gain/Phase: %s" %service.setChannelGainPhase(sn, 0, gain_list, phase_list, polar))

        if testSwitch:
            # Disable specific channel example
            logger.info("Show channel disable status: %s" %service.getChannelSwitch(sn, mode, polar))

            input("WAIT.........Channel Control - Disable")
            logger.info("Disable channel: %s for %s polarization" %(service.switchChannel(sn, 1, True, polar), polar))
            logger.info("Disable channel: %s for all polarization" %service.switchChannel(sn, 4, True))

            input("WAIT.........Channel Control - Enable")
            logger.info("Enable channel: %s" %service.switchChannel(sn, 1, False, polar))
            logger.info("Enable channel: %s" %service.switchChannel(sn, 4, False))

    # Beam control example
    if testBeam:
        input("WAIT.........Beam Control")
        # Passing: gain, theta, phi
        logger.info("SetBeamAngle-1: %s" %service.setBeamAngle(sn, gain_max, 0, 0, polar))
        logger.info("SetBeamAngle-2: %s" %service.setBeamAngle(sn, gain_max-1, 10, 30, polar))
        logger.info("SetBeamAngle-3: %s" %service.setBeamAngle(sn, gain_max-ele_dr_limit+1, 5, 30, polar))
        # logger.info("getBeamGainList: %s" %service.getBeamGainList(sn, polar))
        # logger.info("getBeamPhaseList: %s" %service.getBeamPhaseList(sn, polar))

    # -----------------
    logger.info("Get last IC operating config: %s" %service.getOperatingConfig(sn, mode))
    mode = CellRFMode.STANDBY
    logger.info("Get current RF mode: %s" %service.getRFMode(sn))
    logger.info("Set RF mode: %s" %service.setRFMode(sn, mode).name)


"""Reference for the formula used: Wireless communications with reconfigurable intelligent surface:
path loss modeling and experimental measurement (IEEE Xplore, 2021)
https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9206044 """

def testRIS(sn, service):  # Works in 3D for 28 GHz 32x32 RIS
    """
    Scans and determines the optimal reflection angles (theta_out, phi_out)
    that yield the best received power by configuring RIS phase profiles
    based on the physical model of signal reflection.

    The user provides the incident wave direction (theta_in, phi_in), and the
    system iterates over all outgoing directions to find the best one.

    Args:
        sn (str): Serial number of the RIS device
        service (object): Interface object for controlling RIS hardware
    """
    logger = logging.getLogger("RIS")
    logger.info("Get Net config: %s", service.getNetInfo(sn))

    ret = service.getRISModuleInfo(sn)
    info = ret.RetData
    logger.info("Get RIS info: %s", info)

    module_key = list(info.keys())[0]
    mid = int(module_key)
    row, col = info[module_key]['antenna_size']
    logger.info(f"Get RIS module size: [{row},{col}]")

    # ---------- RIS and signal parameters ----------
    freq = 28e9                             # 28 GHz
    wavelength = 3e8 / freq                 # meters (≈ 0.0107 m)
    dx = wavelength / 2                     # element spacing (0.5 lambda)
    dy = dx
    d = dx

    # Prompt user for theta_in_deg (0 to 180) and phi_in_deg (-180 to 180)
    while True:
        try:
            theta_in_deg = float(input("Enter incident theta (elevation) in degrees [0 to 180]: "))
            if 0 <= theta_in_deg <= 180:
                break
            else:
                print("Error: Theta must be between 0 and 180 degrees.")
        except ValueError:
            print("Error: Please enter a valid number for theta.")

    while True:
        try:
            phi_in_deg = float(input("Enter incident phi (azimuth) in degrees [-180 to 180]: "))
            if -180 <= phi_in_deg <= 180:
                break
            else:
                print("Error: Phi must be between -180 and 180 degrees.")
        except ValueError:
            print("Error: Please enter a valid number for phi.")

    service.initDev(sn)

    HOST = '0.0.0.0'
    PORT = 5003
    all_results = []

    # --- Compute (x, y) positions for RIS elements centered at array's center ---
    x = (np.arange(col) - (col - 1) / 2) * dx
    y = (np.arange(row) - (row - 1) / 2) * dy
    xx, yy = np.meshgrid(x, y)  # Shape: (row, col)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((HOST, PORT))
        server_socket.listen()

        print(f"[RECEIVER] Listening on port {PORT}...")

        conn, addr = server_socket.accept()
        with conn:
            print(f"[RECEIVER] Connected by {addr}")
            time.sleep(1.5)

            # --- 3D sweep over reflection directions ---
            for theta_out_deg in range(0, 180, 1):  # Example: single elevation step (adjust as needed)
                for phi_out_deg in range(0, 360, 10):   # Sweep azimuth every 10°
                    try:
                        # Convert angles to radians
                        theta_in = np.deg2rad(theta_in_deg)
                        phi_in = np.deg2rad(phi_in_deg)
                        theta_out = np.deg2rad(theta_out_deg)
                        phi_out = np.deg2rad(phi_out_deg)

                        # Compute directional deltas (incident - outgoing)
                        delta_x = np.sin(theta_in) * np.cos(phi_in) - np.sin(theta_out) * np.cos(phi_out)
                        delta_y = np.sin(theta_in) * np.sin(phi_in) - np.sin(theta_out) * np.sin(phi_out)

                        # Compute phase profile across RIS
                        phase = -2 * np.pi / wavelength * (delta_x * xx + delta_y * yy)
                        phase_mod = np.mod(phase, 2 * np.pi)

                        # 1-bit quantization (threshold at π)
                        pattern = (phase_mod >= np.pi).astype(int).tolist()

                        result = service.setRISPattern(sn, pattern)
                        logger.info(f"Set RIS pattern for reflection (theta={theta_out_deg}, phi={phi_out_deg}): {result.RetCode}")

                        p = service.getRISPattern(sn, [mid]).RetData
                        logger.info(f"Get RIS pattern: {str(p)[:80]}")  # Truncated for readability

                        time.sleep(1)

                        # Send current reflection azimuth to client
                        conn.sendall(f"{phi_out_deg}".encode())

                        # Receive power value
                        data = conn.recv(1024)
                        try:
                            power = float(data.decode())
                            logger.info(f"[RECEIVER] Received power: {power} at (theta, phi): ({theta_out_deg}, {phi_out_deg})")
                            all_results.append((theta_out_deg, phi_out_deg, power))

                        except ValueError:
                            logger.warning(f"[RECEIVER] Invalid power value received: {data.decode()}")

                    except (KeyboardInterrupt, SystemExit):
                        print("Detected Ctrl+C")
                        break

    # Display top 3 received power values with corresponding reflection angles
    print("\nTop 3 Power Values and Corresponding (Theta, Phi):")
    if all_results:
        top3 = sorted(all_results, key=lambda x: x[2], reverse=True)[:3]
        for idx, (theta_ris_deg, phi_ris_deg, power) in enumerate(top3, 1):
            print(f"  #{idx}:")
            print(f"    Theta_ris: {theta_ris_deg}°")
            print(f"    Phi_ris: {phi_ris_deg}°")
            print(f"    Power: {power}")
    else:
        print("No valid power values received.")


def startDFU(sn, service, dfu_image:str):
    """A example to process DFU"""
    ver = service.queryFWVer(sn).RetData

    ret = service.processDFU(sn, dfu_image)
    if ret.RetCode is not RetCode.OK:
        logger.error("[DFU] DFU failed -> quit")
        return

    ver_new = service.queryFWVer(sn).RetData
    logger.info("[DFU] Done! FW ver: %s -> %s" %(ver, ver_new))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument("--dc", help="Direct connect device to skip scanning, must provide 3 parameters: SN IP dev_type", metavar=('SN','Address','DevType'), nargs=3)
    parser.add_argument("--dfu", help="DFU image path", type=str, default="")
    parser.add_argument("--root", help="The root path/directory of for log/ & files/", type=str, default=".")
    args = parser.parse_args()

    startService(args.root, args.dc, args.dfu)
    logger.info("========= end =========")