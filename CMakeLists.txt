# MS-CAN sniffer for the 2011 Ford Fusion (ESP32-S3)
#
# Listen-only CAN sniffer for reverse-engineering the body bus (MS-CAN,
# 125 kbps, OBD2 pins 3/11) — the bus that carries climate control, locks,
# windows, etc. It never transmits, so it cannot disturb the car.
#
# Workflow: flash -> open serial monitor at 115200 -> ignition ON ->
# capture a baseline log -> press a climate button -> capture again -> diff.
#
# Board: Elecrow CrowPanel 5.0" (ESP32-S3-WROOM-1-N4R8), ESP-IDF v5.4.4.
# The S3's single TWAI controller is used in LISTEN ONLY mode on IO19/IO20
# (J4 header pads 7/8). GPIO43 stays free so the USB serial console works.

cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ms_can_sniffer)
