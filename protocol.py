import logging
import math
import struct
import threading
import time
import typing

import pymodbus.exceptions
import serial
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget
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
        self.humidity_sensor = HumiditySensor(unit_num=28)

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
            module_logger.info(self.rrg.read_flow(self.ser))

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
            try:
                time.sleep(1)
                module_logger.info(self.rrg.read_flow(self.ser))
                time.sleep(1)
                module_logger.info(str(self.humidity_sensor.read_absolute_humidity(self.ser)))
            except:
                pass

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

    def open_valves(self, valves_trues_falses: typing.Collection[int], ser: ModbusSerialClient):
        if len(valves_trues_falses) != 8:
            raise Exception("Explicitly 8 valves must be presented")
        ser.write_coils(0x0000, valves_trues_falses, unit=self.rele_unit)


class HumiditySensor:
    def __init__(self, unit_num: int):
        self.unit_num = unit_num

    def read_temperature_and_humidity(self, ser: ModbusSerialClient):
        temperature, humidity = struct.unpack("<ff", struct.pack("<HHHH", *ser.read_input_registers(0, 4,
                                                                                                    unit=self.unit_num).registers))
        return temperature, humidity

    def read_absolute_humidity(self, ser: ModbusSerialClient):
        temperature, humidity = self.read_temperature_and_humidity(ser)

        ew_t = 6.112 * math.exp(17.62 * temperature / (243.12 + temperature))
        p = 101325 / 100  # in gPa
        ew_tp = (1.0016 + 3.15e-6 * p - 0.074 / p) * ew_t  # in gPa

        e = humidity / 100 * ew_tp  # in gPa
        return e * 100 / 461.5 / (temperature + 273.15)  # in kg/m3


class QtProtocol(QWidget, Protocol):
    stats = Signal(str)
    emit_stats_format = "{:3.3f} {:3.3f} {:3.3f} {:2.3e}"

    def __init__(self, port=None):
        QWidget.__init__(self)
        Protocol.__init__(self, port=port)

        self.rrg1 = RRG(rrg_number=1, max_flow=60)
        self.rrg3 = RRG(rrg_number=3, max_flow=60)
        self.rrg5 = RRG(rrg_number=5, max_flow=1500)

        self.conc = 0
        self.humidity = 0

        self.first_stage_sent = False
        self.second_stage_sent = False
        self.second_start_time = 0

    def run_thread(self):
        self.is_stoped = False
        start_time = time.time()
        self.set_h2s_flow(conc=self.conc)
        while not self.is_stoped:
            self.read_and_emit()
            now_time = time.time()
            if (now_time - start_time) > 1800:
                if not self.first_stage_sent:
                    self.set_h2s_flow(conc=0)
                    self.first_stage_sent = True
                if (self.humidity > 0.01672) and not self.second_stage_sent:
                    self.set_h2s_flow(conc=self.conc)
                    self.second_stage_sent = True
                    self.second_start_time = time.time()
                if self.second_stage_sent:
                    if (now_time - self.second_start_time) > 1800:
                        self.stop()
            time.sleep(0.8)

    def read_and_emit(self):
        try:
            flow1 = self.rrg1.read_flow(self.ser)
            time.sleep(0.05)
            flow3 = self.rrg3.read_flow(self.ser)
            time.sleep(0.05)
            flow5 = self.rrg5.read_flow(self.ser)
            time.sleep(0.05)
            self.humidity = self.humidity_sensor.read_absolute_humidity(self.ser)
            string = self.emit_stats_format.format(flow1, flow3, flow5, self.humidity)
            self.stats.emit(string)
            module_logger.info(string)
        except:
            pass

    def set_flow(self, flow: str):
        self.conc = int(flow)

    def set_h2s_flow(self, conc):
        if conc == 0:
            self.rrg1.change_flow(0, self.ser)
            time.sleep(0.05)
            self.rrg3.change_flow(0, self.ser)
            time.sleep(0.05)
            self.rrg5.change_flow(1000, self.ser)
            time.sleep(0.05)
            self.valve.open_valves((0, 1, 0, 0, 0, 1, 1, 0), self.ser)
            time.sleep(0.05)
        if conc == 1:
            self.rrg1.change_flow(0, self.ser)
            time.sleep(0.05)
            self.rrg3.change_flow(5, self.ser)
            time.sleep(0.05)
            self.rrg5.change_flow(995, self.ser)
            time.sleep(0.05)
            self.valve.open_valves((0, 1, 0, 0, 1, 1, 1, 0), self.ser)
            time.sleep(0.05)
        if conc == 50:
            self.rrg1.change_flow(25, self.ser)
            time.sleep(0.05)
            self.rrg3.change_flow(0, self.ser)
            time.sleep(0.05)
            self.rrg5.change_flow(975, self.ser)
            time.sleep(0.05)
            self.valve.open_valves((0, 1, 0, 1, 0, 1, 1, 0), self.ser)
            time.sleep(0.05)

    def close_event(self):
        if self.ser.is_socket_open():
            self.rrg1.change_flow(0, self.ser)
            time.sleep(0.05)
            self.rrg3.change_flow(0, self.ser)
            time.sleep(0.05)
            self.rrg5.change_flow(0, self.ser)
            time.sleep(0.05)
            self.valve.close_valve(self.ser)
            time.sleep(0.05)
