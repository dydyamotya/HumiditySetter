import logging
import struct
import threading
import time

import pymodbus.exceptions
import serial
from pymodbus.client.sync import ModbusSerialClient
from serial.tools.list_ports import comports

module_logger = logging.getLogger(__name__)


def get_comports_names():
    avaliable_comports = tuple(map(lambda x: x.device, comports()))
    return avaliable_comports


class Protocol:
    def __init__(self, port=None):
        self.ser = ModbusSerialClient(method='rtu',
                                      port=port,
                                      baudrate=19200,
                                      bytesize=serial.EIGHTBITS,
                                      parity=serial.PARITY_NONE,
                                      stopbits=serial.STOPBITS_ONE)
        self.is_stoped = False

        self.rrg: RRG = RRG(max_flow=1500, rrg_number=5)
        self.valve: Valve = Valve(rele_unit=6)

    def set_flow(self, flow: str):
        flow = float(flow)
        try:
            self.rrg.change_flow(flow, self.ser)
        except pymodbus.exceptions.ConnectionException:
            module_logger.info("Cannot init flow")
        else:
            if flow == 0:
                self.valve.close_valve(self.ser)
            else:
                self.valve.open_valve(self.ser)

    def set_port(self, port):
        self.ser.port = port
        if not self.ser.connect():
            module_logger.info("try another port")
        else:
            self.start_thread()

    def close(self):
        self.ser.close()

    def close_event(self):
        self.set_flow("0")
        self.close()

    def stop(self):
        self.is_stoped = True

    def start_thread(self):
        thread = self.create_thread()
        thread.start()

    def run_thread(self):
        self.is_stoped = False
        while not self.is_stoped:
            time.sleep(1)
            module_logger.info(self.rrg.read_flow(self.ser))

    def create_thread(self):
        thread = threading.Thread(target=self.run_thread)
        thread.daemon = True
        return thread


class RRG12:
    AD_NET_ADDRESS = 0x0000
    AD_RRG_NUMBER = 0x0001
    AD_FLAGS1_REGISTER = 0x0002
    AD_FLAGS2_REGISTER = 0x0003
    AD_GASFLOWSET = 0x0004
    AD_GASFLOWREAD = 0x0005
    AD_COMPORT_SPEED = 0x0006
    CLOSE_VALVE_FLAG = 0b00001011
    OPEN_VALVE_FLAG = 0b00001111
    REGULATION_VALVE_FLAG = 0b00000011
    convert_struct_from_word = struct.Struct(">H")
    convert_struct_to_int = struct.Struct(">h")

    @classmethod
    def convert_from_word_to_int(cls, value: int):
        return cls.convert_struct_to_int.unpack(cls.convert_struct_from_word.pack(value))[0]


class RRG:
    def __init__(self, rrg_number: int, max_flow: int):
        self.max_flow = max_flow
        self.rrg_number = rrg_number

    def change_flow(self, value: float, rrg_ser: ModbusSerialClient):
        module_logger.info(f"Change flow to {value}")
        rrg_ser.write_register(RRG12.AD_GASFLOWSET, int(value / self.max_flow * 10000), unit=self.rrg_number)

    def read_flow(self, rrg_ser: ModbusSerialClient):
        try:
            value = RRG12.convert_from_word_to_int(
                rrg_ser.read_holding_registers(RRG12.AD_GASFLOWREAD, unit=self.rrg_number).registers[0])
        except pymodbus.exceptions.ConnectionException:
            value = 0

        return value / 10000 * self.max_flow


class Valve:
    def __init__(self, rele_unit: int):
        self.rele_unit = rele_unit

    def open_valve(self, ser: ModbusSerialClient):
        ser.write_coils(0x0000, (False,) * 8, unit=self.rele_unit)
        ser.write_coil(5, 0x00FF, unit=self.rele_unit)

    def close_valve(self, ser: ModbusSerialClient):
        ser.write_coils(0x0000, (False,) * 8, unit=self.rele_unit)
