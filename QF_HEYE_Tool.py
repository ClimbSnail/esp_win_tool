# encoding: utf-8

# pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# pyinstaller --icon ./images/开源.ico -w -F QF_HEYE_Tool.py

# 环境搭建学习文旦 https://github.com/Jacob-xyb/PyQt_Notes/blob/master/PyQt5.md
# QT官网：https://doc.qt.io/qt-5/index.html
# QT教程  https://b23.tv/9R6dbDA
# QT项目学习课件 https://doc.itprojects.cn/0001.zhishi/python.0008.pyqt5rumen/index.html

import sys
import os
import time
import threading
import re
import yaml
import requests
import traceback

import serial  # pip install pyserial
import serial.tools.list_ports
# from PyQt5.Qt import *
from PyQt5.Qt import QWidget, QApplication
from PyQt5 import uic, QtCore
from PyQt5.QtWidgets import QMessageBox, QApplication, QMainWindow, QFileDialog
from PyQt5.QtCore import Qt

import massagehead as mh

import esptool  # sys.path.append("./esptool_v41") or pip install esptool==4.1
# 需要修改esptool源码loader.py中得一个文件路径
# STUBS_DIR = os.path.join(os.path.dirname(__file__), "targets", "stub_flasher")
# 修改为如下
# STUBS_DIR = os.path.join(os.getcwd(), "stub_flasher")

from download import Ui_SanilHeaterTool
import common

SH_SN = None
if SH_SN == None and os.path.exists("SnailHeater_SN.py"):
    import SnailHeater_SN as SH_SN

    print("激活模块已添加")

COLOR_RED = '<span style=\" color: #ff0000;\">%s</span>'
BAUD_RATE = 921600
INFO_BAUD_RATE = 115200

cur_dir = os.getcwd()  # 当前目录

# 读取配置信息
cfg_fp = open("config.yaml", "r", encoding="utf-8")

win_cfg = yaml.load(cfg_fp, Loader=yaml.SafeLoader)["windows_tool"]

tool_open_url = win_cfg["tool_open_url"] \
    if "tool_open_url" in win_cfg.keys() else "https://github.com/ClimbSnail"
tool_name = win_cfg["tool_name"] \
    if "tool_name" in win_cfg.keys() else "未命名工具"
info_url_0 = win_cfg["info_url_0"] \
    if "info_url_0" in win_cfg.keys() else ""
info_url_1 = win_cfg["info_url_1"] \
    if "info_url_1" in win_cfg.keys() else ""
qq_info = win_cfg["qq_info"].split(",") \
    if "qq_info" in win_cfg.keys() else ["", ""]
activate = win_cfg["activate"] \
    if "activate" in win_cfg.keys() else True
empty_burn_enable = win_cfg["empty_burn_enable"] \
    if "empty_burn_enable" in win_cfg.keys() else True
firmware_info_list = win_cfg["firmware_info_list"] \
    if "firmware_info_list" in win_cfg.keys() else []
main_app_addr = win_cfg["main_app_addr"] \
    if "main_app_addr" in win_cfg.keys() else ""
main_app_rules = win_cfg["main_app_rules"] \
    if "main_app_rules" in win_cfg.keys() else ""
temp_sn_recode_path = win_cfg["temp_sn_recode_path"] \
    if "temp_sn_recode_path" in win_cfg.keys() else cur_dir

cfg_fp.close()


"""
查询的关键字
get_id\r\n
get_id_ok DC5475F18C78\r\n
get_id_err errcode\r\n

get_sn\r\n
get_sn_ok B27FCD\r\n
get_sn_err errcode\r\n

set_sn B27FCD\r\n
set_sn_ok\r\n
set_sn_err errcode\r\n
"""

GET_ID_INFO = "get_id\r\n"
GET_ID_INFO_OK = r"get_id_ok \S*"
GET_SN_INFO = "get_sn\r\n"
GET_SN_INFO_OK = r"get_sn_ok \S*"
SET_SN_INFO = b"set_sn %s\r\n"
SET_SN_INFO_OK = r"set_sn_ok"

# 默认壁纸
default_wallpaper_280 = os.path.join(cur_dir, "./base_data/Wallpaper_280x240.lsw")


class DownloadController(object):

    def __init__(self):
        self.progress_bar_time_cnt = 0
        self.ser = None  # 串口
        self.progress_bar_timer = QtCore.QTimer()
        self.progress_bar_timer.timeout.connect(self.schedule_display_time)

        self.download_thread = None

    def run(self):
        """
        下载页面的主界面生成函数
        :return:
        """
        self.app = QApplication(sys.argv)
        self.win_main = QWidget()
        self.form = Ui_SanilHeaterTool()
        self.form.setupUi(self.win_main)

        _translate = QtCore.QCoreApplication.translate
        self.win_main.setWindowTitle(_translate("SanilHeaterTool",
                                                tool_name + common.VERSION))

        # 设置文本可复制
        self.form.Infolabel_0.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.Infolabel_1.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.QQInfolabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.QQInfolabel_2.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.OpenUrl.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.form.ComComboBox.clicked.connect(self.scan_com)  # 信号与槽函数的绑定
        self.form.FirmwareComboBox.clicked.connect(self.scan_firmware)
        self.form.QueryPushButton.clicked.connect(self.query_button_click)
        self.form.ActivatePushButton.clicked.connect(self.act_button_click)
        self.form.UpdatePushButton.clicked.connect(self.update_button_click)
        # self.form.UpdatePushButton.clicked.connect(self.UpdatePushButton_show_message)
        # self.form.WriteWallpaperButton.clicked.connect(self.writeWallpaper)
        self.form.CanclePushButton.clicked.connect(self.cancle_button_click)

        # 设置提示信息
        self.form.VerInfolabel.setStyleSheet('color: red')
        self.form.QQInfolabel.setText(_translate("SanilHeaterTool", qq_info[0]))
        self.form.QQInfolabel_2.setText(_translate("SanilHeaterTool", qq_info[1]))
        self.form.Infolabel_0.setText(_translate("SanilHeaterTool", info_url_0))
        self.form.Infolabel_1.setText(_translate("SanilHeaterTool", info_url_1))
        self.form.OpenUrl.setText(_translate("SanilHeaterTool", tool_open_url))
        
        # self.form.autoScaleBox.setChecked(True)

        #
        self.form.UICLineEdit.setReadOnly(True)

        print("activate", activate)
        # if not activate:
        self.form.QueryPushButton.setEnabled(activate)
        self.form.ActivatePushButton.setEnabled(activate)

        # self.form.MethodGroupBox.setEnabled(empty_burn_enable)
        self.form.ClearModeMethodRadioButton.setEnabled(empty_burn_enable)
        

        # self.win_main.move(self.win_main)
        self.win_main.show()
        sys.exit(self.app.exec_())

    def scan_com(self):
        """
        搜索串口
        """
        self.print_log("搜索串口号...")
        self.form.ComComboBox.clear()
        com_obj_list = list(serial.tools.list_ports.comports())
        com_list = []
        for com_obj in com_obj_list:
            com_num = com_obj[0]
            info = com_obj[1].split("(")
            com_info = com_obj[1].split("(")[0].strip()
            com_list.append(com_num + " -> " + com_info)

        # print(com_obj_list[0][1])
        if com_list == []:
            com_list = ["未识别到"]
        self.form.ComComboBox.addItems(com_list)

    def scan_firmware(self):
        """
        搜索固件
        """
        global main_app_rules
        # 目前无服务器
        # ver = self.get_firmware_version()
        self.print_log("搜索同目录下的可用固件...")
        self.form.FirmwareComboBox.clear()
        # 列出文件夹下所有的目录与文件
        list_file = os.listdir("./")
        firmware_path_list = []
        for file_name in list_file:
            if main_app_rules in file_name:
                firmware_path_list.append(file_name.strip())

        if len(firmware_path_list) == 0:
            firmware_path_list = ["未找到固件"]
        self.form.FirmwareComboBox.addItems(firmware_path_list)

    def getSafeCom(self):
        """
        获取安全的串口
        :return: Com / None
        """
        if self.ser != None:  # 串口打开标志
            return None

        select_com = self.form.ComComboBox.currentText().split(" -> ")[0].strip()

        com_list = [com_obj[0] for com_obj in list(serial.tools.list_ports.comports())]
        if select_com not in com_list:
            self.print_log((COLOR_RED % "错误提示：") +
                           "无法检测到指定串口设备，先确认 CH340 驱动是否正常或尝试 typec 调换方向。\n")
            return None
        return select_com

    def act_button_click(self):

        self.print_log("正在激活设备...")

        select_com = self.getSafeCom()
        if select_com == None:
            self.print_log(COLOR_RED % "激活操作异常，激活中止...")
            return None

        self.ser = serial.Serial(select_com, INFO_BAUD_RATE, timeout=10)

        act_ret = False

        # 判断是否打开成功
        if self.ser.is_open:
            # self.machine_code_thread = threading.Thread(target=self.read_data,
            #                                         args=(self.ser,))
            # self.machine_code_thread.start()

            search_info = SET_SN_INFO % bytes(self.form.SNLineEdit.text().strip(), encoding='utf8')
            SET_SN_INFO
            print(search_info)
            self.ser.write(search_info)

            time.sleep(1)
            if self.ser.in_waiting:
                try:
                    STRGLO = self.ser.read(self.ser.in_waiting)
                    print("\nSTRGLO = ", STRGLO)
                    match_info = re.findall(SET_SN_INFO_OK, STRGLO.decode("utf8"))
                    if match_info != []:
                        act_ret = True
                except Exception as err:
                    print(str(traceback.format_exc()))

            if act_ret == True:
                # sn_record = open(temp_sn_recode_path, 'a', encoding="utf-8")
                # sn_record.write(value+"\n")
                # sn_record.close()
                self.print_log("激活成功")
            else:
                self.print_log("激活失败")
        self.ser.close()  # 关闭串口
        del self.ser
        self.ser = None

    def query_button_click(self):
        """
        获取用户识别码 显示在用户识别码的信息框里
        获取激活码 显示在激活码的信息框里
        :return: None
        """
    
        self.print_log("获取机器码（用户识别码）...")
        machine_code = self.get_machine_code()
        self.form.UICLineEdit.setText(machine_code)

        self.print_log("\n获取本地激活码（SN）...")
        sn = self.get_sn()
        # # 尝试联网查询
        # if sn == "":
        #     try:
        #         if activate_sn_url != None and activate_sn_url != "":
        #             self.print_log("联网查询激活码（管理员模式）...")
        #             response = requests.get(activate_sn_url + machine_code, timeout=3)  # , verify=False
        #         else:
        #             self.print_log("联网查询激活码...")
        #             response = requests.get(search_sn_url + machine_code, timeout=3)  # , verify=False
        #         # sn = re.findall(r'\d+', response.text)
        #         sn = response.text.strip()
        #         self.print_log("sn " + str(sn))
        #     except Exception as err:
        #         print(str(traceback.format_exc()))
        #         self.print_log("联网异常")

        self.form.SNLineEdit.setText(sn)

        try:
            if sn != "":
                sn_record = open(temp_sn_recode_path, 'a', encoding="utf-8")
                sn_record.write(machine_code + "\t" + sn + "\n")
                sn_record.close()
        except Exception as err:
            print(str(traceback.format_exc()))
            self.print_log("获取异常异常")

    def update_button_click(self):
        """
        按下 刷机 按键后触发的检查、刷机操作
        :return: None
        """
        self.print_log("准备更新固件...")
        self.form.UpdateModeMethodRadioButton.setEnabled(False)
        self.form.ClearModeMethodRadioButton.setEnabled(False)
        self.form.UpdatePushButton.setEnabled(False)

        firmware_path = self.form.FirmwareComboBox.currentText().strip()
        mode = "更新式" if self.form.UpdateModeMethodRadioButton.isChecked() else "清空式"

        select_com = self.getSafeCom()
        if select_com == None or firmware_path == "":
            if firmware_path == "":
                self.print_log((COLOR_RED % "错误提示：") + "未查询到固件文件！")
            self.form.UpdatePushButton.setEnabled(True)
            self.form.UpdateModeMethodRadioButton.setEnabled(True)
            self.form.ClearModeMethodRadioButton.setEnabled(empty_burn_enable and True)
            return False

        self.print_log("串口号：" + (COLOR_RED % select_com))
        self.print_log("固件文件：" + (COLOR_RED % firmware_path))
        self.print_log("刷机模式：" + (COLOR_RED % mode))


        all_time = 0  # 粗略认为连接并复位芯片需要0.5s钟
        if mode == "清空式":
            all_time += 24
        else:
            all_time += 5
        
        # 辅助bin文件
        if firmware_info_list != None and firmware_info_list != []:
            file_list = [bin_obj["filepath"] for bin_obj in firmware_info_list]
            file_list.append(firmware_path)
        
            for filepath in file_list:
                all_time = all_time + os.path.getsize(filepath) * 10 / BAUD_RATE


        self.print_log("刷机预计需要：" + (COLOR_RED % (str(all_time)[0:5] + "s")))

        # 进度条进程要在下载进程之前启动（为了在下载失败时可以立即查杀进度条进程）
        self.download_thread = threading.Thread(target=self.down_action,
                                                args=(mode, select_com, firmware_path))
        self.progress_bar_timer.start(int(all_time / 0.1))

        self.download_thread.setDaemon(True)  # 设置守护线程目的尽量防止意外中断掉主线程程序
        self.download_thread.start()

    def down_action(self, mode, select_com, firmware_path):
        """
        下载操作主体
        :param mode:下载模式
        :param select_com:串口号
        :param firmware_path:固件文件路径
        :return:None
        """
        
        try:
            if self.ser != None:
                return

            self.ser = 1
            self.progress_bar_time_cnt = 1  # 间接启动进度条更新

            if mode == "清空式":
                self.print_log("正在清空主机数据...")
                # esptool.py erase_region 0x20000 0x4000
                # esptool.py erase_flash
                cmd = ['--port', select_com, 'erase_flash']
                try:
                    esptool.main(cmd)
                    self.print_log("完成清空！")
                except Exception as e:
                    self.print_log(COLOR_RED % "错误：通讯异常。")
                    pass
            
            #  --port COM7 --baud 921600 write_flash -fm dio -fs 4MB 0x1000 bootloader_dio_40m.bin 0x00008000 partitions.bin 0x0000e000 boot_app0.bin 0x00010000
            cmd = ['--port', select_com,
                   '--baud', str(BAUD_RATE),
                   '--after', 'hard_reset',
                   'write_flash', main_app_addr, firmware_path
                   ]
            # 辅助bin文件
            if firmware_info_list != None and firmware_info_list != []:
                for bin_obj in firmware_info_list:
                    cmd.append(bin_obj["addr"])
                    cmd.append(bin_obj["filepath"])
            
            print("cmd = "+ str(cmd))

            self.print_log("开始刷写固件...")
            try:
                esptool.main(cmd)
            except Exception as e:
                self.print_log(COLOR_RED % "错误：通讯异常。")
                return False
            self.ser = None

            # self.esp_reboot()  # 手动复位芯片
            self.print_log(COLOR_RED % "刷机结束！")

        except Exception as err:
            self.ser = None
            self.print_log(COLOR_RED % "未释放资源，请15s后再试。如无法触发下载，拔插type-c接口再试。")
            print(err)

        # global SH_SN
        # if SH_SN != None:
        #     # 自动激活
        #     time.sleep(22)
        #     self.print_log("获取机器码（用户识别码）...")
        #     machine_code = self.get_machine_code()
        #     self.form.UICLineEdit.setText(machine_code)

        #     ecdata = SH_SN.getSnForMachineCode(machine_code)
        #     self.print_log("\n生成的序列号为: " + ecdata)
        #     self.form.SNLineEdit.setText(ecdata)
        #     self.act_button_click()

        self.progress_bar_time_cnt = 0  # 复位进度条

        self.form.UpdatePushButton.setEnabled(True)
        self.form.UpdateModeMethodRadioButton.setEnabled(True)
        self.form.ClearModeMethodRadioButton.setEnabled(empty_burn_enable and True)

    def cancle_button_click(self):
        """
        取消下载固件
        :return: None
        """

        self.print_log("手动停止更新固件...")

        if self.download_thread != None:
            try:
                # 杀线程
                # common.kill_thread(self.download_thread, self.down_action)
                common._async_raise(self.download_thread)
                self.download_thread = None
            except Exception as err:
                print(err)

        self.scan_com()

        # 复位进度条
        self.progress_bar_time_cnt = 0
        self.form.progressBar.setValue(0)

        self.form.UpdatePushButton.setEnabled(True)
        self.form.UpdateModeMethodRadioButton.setEnabled(True)
        self.form.ClearModeMethodRadioButton.setEnabled(empty_burn_enable and True)

    def get_firmware_version(self):
        """
        获取最新版
        """
        global get_firmware_new_ver_url
        new_ver = None
        try:
            self.print_log("联网查询最新固件版本...")
            response = requests.get(get_firmware_new_ver_url, timeout=3)  # , verify=False
            # sn = re.findall(r'\d+', response.text)
            if 'SnailHeater_v' in response.text.strip() or 'SH_SW_v' in response.text.strip():
                new_ver = response.text.strip()
                self.form.VerInfolabel.setText("最新固件版本 " + str(new_ver))
                self.print_log("最新固件版本 " + (COLOR_RED % str(new_ver)))
            else:
                self.print_log((COLOR_RED % "最新固件版本查询异常"))

        except Exception as err:
            print(str(traceback.format_exc()))
            self.print_log((COLOR_RED % "联网异常"))
        
        return new_ver

    def get_machine_code(self):
        '''
        查询机器码
        '''
        select_com = self.getSafeCom()
        if select_com == None:
            return None

        self.ser = serial.Serial(select_com, INFO_BAUD_RATE, timeout=10)
        machine_code = "查询失败"

        # 判断是否打开成功
        if self.ser.is_open:
            # self.machine_code_thread = threading.Thread(target=self.read_data,
            #                                         args=(self.ser,))
            # self.machine_code_thread.start()

            search_info = bytes(GET_ID_INFO, encoding='utf8')
            print(search_info)
            self.print_log("write start")
            self.ser.write(search_info)
            self.print_log("write OK")

            time.sleep(1)
            if self.ser.in_waiting:
                try:
                    STRGLO = self.ser.read(self.ser.in_waiting).decode("utf8")
                    print(STRGLO)
                    machine_code = re.findall(GET_ID_INFO_OK, STRGLO)[0] \
                        .split(" ")[-1]
                except Exception as err:
                    machine_code = "查询失败"
                print(machine_code)

            if machine_code == "查询失败":
                self.print_log((COLOR_RED % "机器码查询失败"))
            else:
                self.print_log("机器码查询成功")

        self.ser.close()  # 关闭串口
        del self.ser
        self.ser = None
        return machine_code

    def get_sn(self):
        '''
        查询SN
        '''
        select_com = self.getSafeCom()
        if select_com == None:
            return None

        self.ser = serial.Serial(select_com, INFO_BAUD_RATE, timeout=10)
        sn = ""

        # 判断是否打开成功
        if self.ser.is_open:
            # self.sn_thread = threading.Thread(target=self.read_data,
            #                                         args=(self.ser,))
            # self.sn_thread.start()

            search_info = bytes(GET_SN_INFO, encoding='utf8')
            print(search_info)
            self.ser.write(search_info)

            time.sleep(1)
            if self.ser.in_waiting:
                try:
                    STRGLO = self.ser.read(self.ser.in_waiting).decode("utf8")
                    print(STRGLO)
                    sn = re.findall(GET_SN_INFO_OK, STRGLO)[0] \
                        .split(" ")[-1]
                except Exception as err:
                    sn = ""
                print(sn)

            if sn == "":
                self.print_log((COLOR_RED % "SN查询失败"))
            else:
                self.print_log("SN查询成功")
        self.ser.close()  # 关闭串口
        del self.ser
        self.ser = None
        return sn

    def print_log(self, info):
        self.form.LogInfoTextBrowser.append(info + '\n')
        QApplication.processEvents()
        # self.form.LogInfoTextBrowser.

    def esp_reboot(self):
        """
        重启芯片(控制USB-TLL的rst dst引脚)
        :return:
        """

        time.sleep(0.1)
        select_com = self.getSafeCom()
        if select_com == None:
            return None
        self.ser = serial.Serial(select_com, BAUD_RATE, timeout=10)

        # self.ser.setRTS(True)  # EN->LOW
        # self.ser.setDTR(self.ser.dtr)
        # time.sleep(0.2)
        # self.ser.setRTS(False)
        # self.ser.setDTR(self.ser.dtr) 

        self._setDTR(False)  # IO0=HIGH
        self._setRTS(True)  # EN=LOW, chip in reset
        time.sleep(0.1)
        self._setDTR(True)  # IO0=LOW
        self._setRTS(False)  # EN=HIGH, chip out of reset
        # 0.5 needed for ESP32 rev0 and rev1
        time.sleep(0.05)  # 0.5 / 0.05
        self._setDTR(False)  # IO0=HIGH, done

        self.ser.close()  # 关闭串口
        del self.ser
        self.ser = None

    def schedule_display_time(self):
        if self.progress_bar_time_cnt > 0 and self.progress_bar_time_cnt < 99:
            self.progress_bar_time_cnt += 1
        self.form.progressBar.setValue(self.progress_bar_time_cnt)

    def UpdatePushButton_show_message(self):
        """
        警告拔掉AC220V消息框
        :return: None
        """
        # # 最后的Yes表示弹框的按钮显示为Yes，默认按钮显示为OK,不填QMessageBox.Yes即为默认
        # reply = QMessageBox.warning(self.win_main, "重要提示",
        #                                COLOR_RED % "刷机一定要拔掉220V电源线！",
        #                                QMessageBox.Yes | QMessageBox.Cancel,
        #                                QMessageBox.Cancel)

        # 创建自定义消息框
        self.mbox = QMessageBox(QMessageBox.Warning, "重要提示",
                                COLOR_RED % "刷机一定要拔掉220V电源线！")
        # 添加自定义按钮
        do = self.mbox.addButton('确定', QMessageBox.YesRole)
        cancle = self.mbox.addButton('取消', QMessageBox.NoRole)
        # 设置消息框中内容前面的图标
        self.mbox.setIcon(2)
        do.clicked.connect(self.update_button_click)
        self.mbox.show()



def main():
    # app = QApplication([])
    app = QApplication(sys.argv)
    download_ui = uic.loadUi("download.ui")
    # download_ui.ComComboBox.
    download_ui.show()
    app.exec_()


if __name__ == '__main__':
    # 解决不同电脑不同缩放比例问题
    # QGuiApplication.setAttribute(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # 和designer设计的窗口比例一致
    QtCore.QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    # 适应高DPI设备
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    # 解决图片在不同分辨率显示模糊问题
    # QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    # main()

    downloader = DownloadController()
    downloader.run()
