#####################################################
# Rally Timing v1.32                                #
#                                                   #
# Copyright wimdes & schlaubi77 30/05/2023          #
# Released under the terms of GPLv3                 #
# thx to Hecrer, PleaseStopThis, KubaV383, GPT-4    #
#                                                   #
# Find the AC Rally Wiki on Racedepartment:         #
# https://bit.ly/3HCELP3                            #
#                                                   #
# changelog:                                        #
# v1.32 fix for sim_info not loading                #
# v1.31 some small fixes                            #
# v1.3 added delta functionality                    #
# v1.2 settings configurable in ContentManager GUI  #
# v1.1 add multi language support                   #
#                                                   #
#####################################################
# TODO:                                             #
# cleanup code                                      #
# reset track data button                           #
# add replay detection                              #
# add linear bar                                    #
#                                                   #
# doDelta to binary search, interval for ref file creation
#####################################################

from datetime import datetime
import sys, ac, acsys, os, json, math, configparser
from libs.sim_info import info

config = configparser.ConfigParser(inline_comment_prefixes=';')
config.read("apps/python/RallyTiming/config/config.ini")

###### App settings
StartSpeedLimit = config.getint("RallyTiming", "startspeedlimit")
MaxStartLineDistance = config.getfloat("RallyTiming", "maxstartlinedistance")
ShowStartSpeed = config.getboolean("RallyTiming", "showstartspeed")
ShowRemainingDistance = config.getboolean("RallyTiming", "showremainingdistance")
ShowFuel = config.getboolean("RallyTiming", "showfuel")
DebugMode = config.getboolean("RallyTiming", "debugmode")
Language = config.get("RallyTiming", "language")
MaxRefFiles = config.getint("RallyTiming", "maximumreffiles")

with open("apps/python/RallyTiming/config/lang.json", "r", encoding="utf-8") as file:
    lang = json.load(file)
lang = lang[str(Language)]

###### Default variables 
AppName = "Rally Timing"
appWindow = 0
StartFinishJson = "apps/python/RallyTiming/StartFinishSplines.json"
SplineLength = ac.getTrackLength(0)
Status = 0  # 0 = Start Undefined, 1 = Start Found, 2 = Drive to start, 3 = in stage, 4 = over finish, 5 = invalidated, 6 = stopped at startline
StatusList = [lang["phase.detect"], lang["phase.linefound"], lang["phase.gotostart"], lang["phase.instage"], lang["phase.finished"], lang["phase.invalidated"], lang["phase.atstartline"]]
StartSpeed = 0
LapCountTracker = 0
StartPositionAccuracy = 0
Meter = 1 / SplineLength
SpeedTrapValue = 0
StartChecked = False
reference_stage_time_int = 0
CheckFastestTime = False

###### Determine track name & layout
if ac.getTrackConfiguration(0) != "":
    TrackName = (ac.getTrackName(0) + "/" + ac.getTrackConfiguration(0))
else:
    TrackName = ac.getTrackName(0)

###### Reference Laps
ReferenceFolder = "apps/python/RallyTiming/referenceLaps/" + TrackName

window_choose_reference = 0
window_timing = 0
reference_data = []
data_collected = []
last_ref_index = 0

if not os.path.exists(ReferenceFolder):
    os.makedirs(ReferenceFolder)

###### Determine if local game or on server - perhaps ac.isAcLive() can be used?
if ac.getServerName() == "":
    OnServer = False
else:
    OnServer = True
    StatusList[5] = lang["phase.invalidatedserver"]

###### Load start and finish positions from json file
with open(StartFinishJson, "r") as file:
    StartFinishSplines = json.load(file)
    try:
        StartSpline = (StartFinishSplines[TrackName]["StartSpline"])
        FinishSpline = (StartFinishSplines[TrackName]["FinishSpline"])
        Status = 1
    except KeyError:
        ac.console(AppName + ": No complete track info found in json")
        Status = 0
        StartSpline = 0
        FinishSpline = 0
        StartFinishSplines[TrackName] = {"StartSpline": 0, "FinishSpline": 0, "TrueLength": 0}

white = (1.0, 1.0, 1.0, 1.0)
gray = (0.75, 0.75, 0.75, 1.0)

line1, line2, line3, line4, line5, line6 = [0 for i in range(6)]

###### write some stuff into log and console
ac.console(AppName + ": Track Name: " + TrackName)
# ac.console (AppName + ": Start Spline: {:.10f}".format(StartSpline))
# ac.console (AppName + ": Finish Spline: {:.10f}".format(FinishSpline))
# ac.console (AppName + ": Meter: {:.10f}".format(Meter))
# ac.console (AppName + ": Centimeter: {:.10f}".format(Meter / 100))
# ac.log(AppName + " test entry")


def acMain(ac_version):
    global line1, line2, line3, line4, line5, line6, window_choose_reference, window_timing, appWindow

    appWindow = ac.newApp(AppName + " - Main")

    if not DebugMode:
        if not ShowFuel:
            ac.setSize(appWindow, 373, 92)   # default is 373,92
        else:
            ac.setSize(appWindow, 373, 112)
    else:
        ac.setSize(appWindow, 580, 172)
    ac.setTitle(appWindow, "")
    ac.drawBorder(appWindow, 0)
    ac.setIconPosition(appWindow, 0, -10000)
    ac.setBackgroundOpacity(appWindow, 0.1)

    window_choose_reference = ChooseReferenceWindow("Rally Timing - Reference Laps", "apps/python/RallyTiming/referenceLaps/" + TrackName)
    window_timing = TimingWindow()

    lines = []
    for i in range(6):
        line = ac.addLabel(appWindow, "")
        lines.append(line)
        ac.setPosition(line, 10, 5 + 25*i)
        ac.setFontSize(line, 20)
    line1, line2, line3, line4, line5, line6 = lines

    fix_reffile_amount_and_choose_fastest()

    return AppName


def acUpdate(deltaT):
    global line1, line2, line3, line4, line5, line6
    global Status, ActualSpline, ActualSpeed, StartSpline, FinishSpline, StartSpeed, StartDistance, LastSessionTime, StartPositionAccuracy, LapCountTracker
    global SpeedTrapValue, StartChecked, data_collected, last_ref_index, CheckFastestTime

    ActualSpline = ac.getCarState(0, acsys.CS.NormalizedSplinePosition)
    ActualSpeed = ac.getCarState(0, acsys.CS.SpeedKMH)
    StartDistance = (StartSpline - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength
    FinishDistance = (FinishSpline - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength
    LapTime = ac.getCarState(0, acsys.CS.LapTime)
    LapCount = ac.getCarState(0, acsys.CS.LapCount)
    ac.addOnChatMessageListener(appWindow, chat_message_listener)

    if Status == 0 and LapTime > 0:
        StartSpline = ActualSpline
        Status = 1  # Start Found
        StartFinishSplines[TrackName]["StartSpline"] = ActualSpline
        with open(StartFinishJson, "w") as file:
            json.dump(StartFinishSplines, file, indent=4)

    if Status == 1 and ActualSpline < StartSpline:
        Status = 2  # Drive to start

    if Status == 2 and 0 < StartDistance < MaxStartLineDistance and ActualSpeed < 0.05:
        Status = 6  # stopped at startline
        ac.setFontColor(line1, 0, 1, 0, 1)

    if Status == 6 and StartDistance > MaxStartLineDistance:
        ac.setFontColor(line1, 1, 1, 1, 1)
        Status = 2  # Drive back to start

    if (Status == 2 or Status == 6) and ActualSpline > StartSpline:
        StartSpeed = ActualSpeed
        StartPositionAccuracy = abs((StartSpline - ActualSpline) * SplineLength)
        ac.setFontColor(line1, 1, 1, 1, 1)
        Status = 3  # In stage

    if (Status == 3 or Status == 5) and LapCount > LapCountTracker:
        write_reference_file(data_collected, ReferenceFolder, info.graphics.iLastTime if info.graphics.iLastTime > 0 else info.graphics.iCurrentTime)
        CheckFastestTime = True
        Status = 4  # Over finish
        if FinishSpline == 0:
            FinishSpline = ActualSpline
            TrueLength = (FinishSpline-StartSpline) * SplineLength
            StartFinishSplines[TrackName]["FinishSpline"] = ActualSpline
            StartFinishSplines[TrackName]["TrueLength"] = TrueLength
            with open(StartFinishJson, "w") as file:
                json.dump(StartFinishSplines, file, indent=4)

    if OnServer:
        if Status == 3 and SpeedTrapValue > StartSpeedLimit:
            Status = 5  # START FAIL - ONLINE LAP WILL BE INVALIDATED
            StatusList[4] = lang["phase.invalidatedserver"]
            ac.setFontColor(line1, 1, 0, 0, 1)
            ac.console(AppName + ": Local StartSpeed: {:.2f}".format(StartSpeed) + " / Server StartSpeed: {:.2f}".format(SpeedTrapValue))
            StartChecked = True
        if Status == 3 and SpeedTrapValue <= StartSpeedLimit and not StartChecked:
            if SpeedTrapValue != 0:
                ac.console(AppName + ": Local StartSpeed: {:.2f}".format(StartSpeed) + " / Server StartSpeed: {:.2f}".format(SpeedTrapValue))
                StartChecked = True
    else:
        if Status == 3 and StartSpeed > StartSpeedLimit:
            Status = 5  # START FAIL
            ac.setFontColor(line1, 1, 0, 0, 1)

    if (Status == 3 or Status == 4 or Status == 5) and ActualSpline < StartSpline:
        data_collected = []
        last_ref_index = 0
        Status = 2  # Drive to start
        LapCountTracker = LapCount
        ac.setFontColor(line1, 1, 1, 1, 1)
        StartSpeed = 0
        SpeedTrapValue = 0
        StartChecked = False
        StatusList[4] = lang["phase.finished"]

    if Status == 2 or Status == 6:
        if CheckFastestTime:
            fix_reffile_amount_and_choose_fastest()
            CheckFastestTime = False
        if ActualSpline == 0:
            ac.setText(line3, lang["startdist"] + "{:.2f}".format(XYStartDistance()) + " m " + lang["inbrack.estimated"])
        else:
            ac.setText(line3, lang["startdist"] + "{:.2f}".format(StartDistance) + " m")
        if ShowStartSpeed:
            ac.setText(line2, lang["startspeedlimit"] + "{}".format(StartSpeedLimit) + " km/h")

    if Status == 4:
        ac.setText(line3, "")
        time = info.graphics.iLastTime
    else:
        time = info.graphics.iCurrentTime

    if Status == 3 or Status == 5:
        if ShowStartSpeed:
            if OnServer:
                ac.setText(line2, lang["startspeed"] + "{:.2f}".format(SpeedTrapValue) + " km/h " + lang["inbrack.server"])
            else:
                ac.setText(line2, lang["startspeed"] + "{:.2f}".format(StartSpeed) + " km/h")
        if ShowRemainingDistance:
            if FinishSpline != 0:
                ac.setText(line3, lang["finishdist"] + "{:.0f}".format(FinishDistance) + " m")
            else:
                ac.setText(line3, lang["finishdist"] + "{:.0f}".format((1 - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength) + " m " + lang["inbrack.estimated"])
        else:
            ac.setText(line3, "")

        data_collected.append((ActualSpline, time))

    ac.setText(line1, StatusList[Status])

    window_timing.update()

    if ShowFuel:
        ac.setText(line4, lang["fuel"] + "{:.1f}".format(info.physics.fuel) + " l")

    if DebugMode:
        ac.setText(line4, "StartPositionAccuracy: {:.2f}".format(StartPositionAccuracy) + "  Status: {}".format(Status) + "  StageTimeRef: {}".format(reference_stage_time_int))
        ac.setText(line5, "ActualSpline: {:.5f}".format(ActualSpline) + "  StartSpline: {:.5f}".format(StartSpline) + "  FinishSpline: {:.5f}".format(FinishSpline))
        ac.setText(line6, "XYStartDistance: {:.2f}".format(XYStartDistance()) + "  LapCount: {}".format(LapCount) + "  SpeedTrapValue: {}".format(SpeedTrapValue))


def XYStartDistance():
    x1, y1, z1 = ac.ext_splineToWorld(0, StartSpline)
    x2, y2, z2 = ac.getCarState(0, acsys.CS.WorldPosition)
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def chat_message_listener(message, sender):
    global SpeedTrapValue
    if message.startswith("Speed Trap #0"):
        speed_start = message.find("Speed: ") + len("Speed: ")
        speed_end = message.find("km/h", speed_start)
        SpeedTrapValue = float(message[speed_start:speed_end])


class ChooseReferenceWindow:

    def __init__(self, name, path, x=510, y=350):
        self.name = name
        self.path = path
        self.window = ac.newApp(name)
        ac.setSize(self.window, x, y)
        ac.setIconPosition(self.window, 16000, 16000)

        self.otherCarsBox = ac.addCheckBox(self.window, lang["othercars"])
        self.carStateChangedFunction = self.carStateChanged
        self.showOtherCars = True
        ac.setPosition(self.otherCarsBox, 20, 35)
        ac.setSize(self.otherCarsBox, 15, 15)
        ac.setValue(self.otherCarsBox, True)
        ac.addOnCheckBoxChanged(self.otherCarsBox, self.carStateChangedFunction)

        self.otherDriversBox = ac.addCheckBox(self.window, lang["otherdrivers"])
        self.driverStateChangedFunction = self.driverStateChanged
        self.showOtherDrivers = True
        ac.setPosition(self.otherDriversBox, 255, 35)
        ac.setSize(self.otherDriversBox, 15, 15)
        ac.setValue(self.otherDriversBox, True)
        ac.addOnCheckBoxChanged(self.otherDriversBox, self.driverStateChangedFunction)

        self.list = SelectionList(1, 20, 65, [str(p) for p in os.listdir(self.path)], self.window, height=300, width=450)

    def carStateChanged(self, *args):
        self.showOtherCars = bool(args[1])
        self.refilterList()

    def driverStateChanged(self, *args):
        self.showOtherDrivers = bool(args[1])
        self.refilterList()

    def refilterList(self):
        elements = [str(p).replace(".refl", "") for p in os.listdir(self.path)]
        show = []
        car = ac.getCarName(0).replace("_", "-")
        driver = ac.getDriverName(0)
        for e in elements:
            if (self.showOtherDrivers or "_".join(e.split("_")[1:-1]) == driver) and (self.showOtherCars or e.split("_")[-1] == car):
                show.append(e)
        self.list.setElements(show)


class TimingWindow:

    def __init__(self, name="Rally Timing - Delta", x=200, y=90):
        self.name = name
        self.window = ac.newApp(name)
        ac.setTitle(self.window, "")
        ac.setSize(self.window, x, y)
        ac.drawBorder(self.window, 0)
        ac.setBackgroundOpacity(self.window, 0.1)
        ac.setIconPosition(self.window, 16000, 16000)

        self.label_ref = ac.addLabel(self.window, "Target:    (none)")
        ac.setPosition(self.label_ref, 20, 5)
        ac.setFontSize(self.label_ref, 20)

        self.label_time = ac.addLabel(self.window, "Current:  00:00.000")
        ac.setPosition(self.label_time, 20, 30)
        ac.setFontSize(self.label_time, 20)

        self.label_delta = ac.addLabel(self.window, "Delta:   +0.000")
        ac.setPosition(self.label_delta, 20, 55)
        ac.setFontSize(self.label_delta, 20)

    def update(self):
        if Status == 0 or Status == 1 or Status == 2 or Status == 6:
            ac.setText(self.label_time, "Current:  00:00.000")
            ac.setFontColor(self.label_delta, 1, 1, 1, 1)
            ac.setText(self.label_delta, "Delta:    +0.000")

        if Status == 3 or Status == 5:
            time = info.graphics.iCurrentTime
            self._do_delta(time)
            ac.setText(self.label_time, "Current: " + str(int(time // 60000)).zfill(2) + ":" + str(int((time % 60000) // 1000)).zfill(2) + "." + str(int(time % 1000)).zfill(3))

        if Status == 4:
            time = info.graphics.iLastTime
            delta = time - reference_stage_time_int
            ac.setText(self.label_time, "Current: " + str(int(time // 60000)).zfill(2) + ":" + str(int((time % 60000) // 1000)).zfill(2) + "." + str(int(time % 1000)).zfill(3))
            if delta > 0:
                ac.setFontColor(self.label_delta, 1, 0, 0, 1)
                ac.setText(self.label_delta, "Delta:     " + "+" + str(int(delta // 1000)) + "." + str(int(delta % 1000)))
            else:
                ac.setFontColor(self.label_delta, 0, 1, 0, 1)
                ac.setText(self.label_delta, "Delta:     " + "-" + str(int(abs(delta) // 1000)) + "." + str(int(abs(delta) % 1000)))

    def _do_delta(self, time):
        global last_ref_index
        if last_ref_index >= len(reference_data):
            last_ref_index = len(reference_data) - 1

        if len(reference_data) == 0:
            ac.setFontColor(self.label_delta, 1, 1, 1, 1)
            ac.setText(self.label_delta, "Delta:   +0.000")
            return

        while reference_data[last_ref_index][0] < ac.getCarState(0, acsys.CS.NormalizedSplinePosition):
            if len(reference_data) > last_ref_index + 1:
                last_ref_index += 1
            else:
                break

        delta = time - reference_data[last_ref_index][1]
        if delta > 0:
            ac.setFontColor(self.label_delta, 1, 0, 0, 1)
            ac.setText(self.label_delta, "Delta:     " + "+" + str(int(delta // 1000)) + "." + str(int(delta % 1000)))
        else:
            ac.setFontColor(self.label_delta, 0, 1, 0, 1)
            ac.setText(self.label_delta, "Delta:     " + "-" + str(int(abs(delta) // 1000)) + "." + str(int(abs(delta) % 1000)))


class SelectionListElement:
    def __init__(self, element_id, list_handler, selection_button, scroll_button):
        self.element_id = element_id
        self.list_handler = list_handler
        self.selection_button = selection_button
        self.scroll_button = scroll_button
        self.click_event = self.clickEvent

        ac.addOnClickedListener(self.selection_button, self.click_event)

    def clickEvent(self, dummy, variable):
        global reference_data, last_ref_index

        if 0 <= self.list_handler.selection_indx < self.list_handler.rows_nbr:
            # if any previous selection present, clear it
            self.list_handler.updateElement(self.list_handler.selection_indx, colour=white)

        # set new index and mark selection with gray
        sel_indx = self.element_id
        self.list_handler.selection_indx = sel_indx
        ac.setText(self.list_handler.list_head, ac.getText(self.selection_button))
        ac.setFontColor(self.list_handler.list_head, *white)
        ac.setFontColor(self.selection_button, *gray)

        disassembled_file_name = ac.getText(self.selection_button)
        reassembled = disassembled_file_name[4:13] + "_"  # time
        reassembled += disassembled_file_name[15:33].strip() + "_"  # driver
        reassembled += disassembled_file_name[33:].replace(" ", "-")

        reference_data = read_reference_file(ReferenceFolder + "/" + reassembled + ".refl")
        last_ref_index = 0
        # collapse list
        self.list_handler.dropListDown()


class SelectionList:
    def __init__(self, list_id, pos_x, pos_y, data, window, height=280, width=150):
        self.parent_window = window

        self.list_id = list_id
        self.btn_size = round(20)
        self.width = width
        self.row_height = self.btn_size
        self.height = height
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.rows_nbr = 0
        self.elements = []
        self.list_elements = []
        self.scroll_indx = 0
        self.selection_indx = -999
        self.state_down = False
        self.scrollable = True
        self.handler_drop_down = self.dropListDown
        self.handler_scroll_up = self.scrollListUp
        self.handler_scroll_down = self.scrollListDown

        # header
        self.list_head = ac.addButton(self.parent_window, "")
        ac.setSize(self.list_head, self.width, self.row_height)
        ac.setPosition(self.list_head, self.pos_x, self.pos_y)
        ac.setFontSize(self.list_head, round(15))
        ac.setFontAlignment(self.list_head, "left")
        ac.drawBorder(self.list_head, 1)
        ac.setBackgroundOpacity(self.list_head, 0.0)
        ac.setVisible(self.list_head, 1)

        self.head_button = ac.addButton(self.parent_window, "v")
        ac.setSize(self.head_button, self.btn_size, self.btn_size)
        ac.setPosition(self.head_button, self.pos_x + self.width, self.pos_y)
        ac.setFontSize(self.head_button, round(15))
        ac.setFontAlignment(self.head_button, "center")
        ac.drawBorder(self.head_button, 1)
        ac.setBackgroundOpacity(self.head_button, 0.0)
        ac.addOnClickedListener(self.head_button, self.handler_drop_down)
        ac.setVisible(self.head_button, 1)

        for e in data:
            self.addElement(e)

        # labels with setups
        self.createSelectionButtons()

    def createSelectionButtons(self):
        # calculate max number of list rows that will fit app window (minus 1 for some space below it)
        self.rows_nbr = ((self.height - self.pos_y - self.row_height) // self.row_height) - 1

        for i in range(self.rows_nbr):
            pos_y = ((i + 1) * self.row_height) + self.pos_y

            self.list_elements.append(
                SelectionListElement(i, self, ac.addButton(self.parent_window, ""), ac.addButton(self.parent_window, "")))

            # define element part
            ac.setVisible(self.list_elements[i].selection_button, 0)
            ac.setSize(self.list_elements[i].selection_button, self.width, self.row_height)
            ac.setPosition(self.list_elements[i].selection_button, self.pos_x, pos_y)
            ac.setFontSize(self.list_elements[i].selection_button, round(15))
            ac.setFontAlignment(self.list_elements[i].selection_button, "left")
            ac.drawBorder(self.list_elements[i].selection_button, 0)
            ac.setBackgroundOpacity(self.list_elements[i].selection_button, 0.9)

            # define scroll bar part
            ac.setVisible(self.list_elements[i].scroll_button, 0)
            ac.setSize(self.list_elements[i].scroll_button, self.btn_size, self.btn_size)
            ac.setPosition(self.list_elements[i].scroll_button, self.pos_x + self.width, pos_y)
            ac.setFontSize(self.list_elements[i].scroll_button, round(15))
            ac.setFontAlignment(self.list_elements[i].scroll_button, "center")
            ac.drawBorder(self.list_elements[i].scroll_button, 0)
            ac.setBackgroundOpacity(self.list_elements[i].scroll_button, 0.2)

            if i == 0:
                ac.addOnClickedListener(self.list_elements[i].scroll_button, self.handler_scroll_up)
                ac.setText(self.list_elements[i].scroll_button, "^")
                ac.setBackgroundOpacity(self.list_elements[i].scroll_button, 0.9)
            else:
                if i == (self.rows_nbr - 1):
                    ac.addOnClickedListener(self.list_elements[i].scroll_button, self.handler_scroll_down)
                    ac.setText(self.list_elements[i].scroll_button, "v")
                    ac.drawBorder(self.list_elements[i].scroll_button, 1)
                    ac.setBackgroundOpacity(self.list_elements[i].scroll_button, 0.9)

    def updateElement(self, indx, value=None, colour=None):
        if 0 <= indx < self.rows_nbr:
            if value is not None:
                ac.setText(self.list_elements[indx].selection_button, value)
                if indx == self.selection_indx and colour is None:
                    ac.setFontColor(self.list_elements[indx].selection_button, 0, 1, 0, 1)
                else:
                    if colour is None:
                        ac.setFontColor(self.list_elements[indx].selection_button, *white)

            if colour is not None:
                ac.setFontColor(self.list_elements[indx].selection_button, *colour)

    def displayElement(self, indx, visible):
        if 0 <= indx < self.rows_nbr:
            ac.setVisible(self.list_elements[indx].selection_button, visible)
            if self.scrollable:
                ac.setVisible(self.list_elements[indx].scroll_button, visible)
            else:
                ac.setVisible(self.list_elements[indx].scroll_button, 0)

    def clearElement(self, indx):
        if 0 <= indx < self.rows_nbr:
            # reset value part
            ac.setVisible(self.list_elements[indx].selection_button, 0)
            ac.setText(self.list_elements[indx].selection_button, "")
            ac.setFontColor(self.list_elements[indx].selection_button, *white)
            # reset scroll part
            ac.setVisible(self.list_elements[indx].scroll_button, 0)

    def scrollListUp(self, dummy, variable):

        self.scroll_indx -= 1
        if self.scroll_indx < 0:
            self.scroll_indx = 0
            return

        if self.selection_indx != -999:
            self.selection_indx += 1

        offset = self.scroll_indx
        for indx in range(0, self.rows_nbr):
            if indx + offset < len(self.elements):
                self.updateElement(indx, value=self.elements[indx + offset].rstrip('.ini'))

    def scrollListDown(self, dummy, variable):
        self.scroll_indx += 1
        if self.scroll_indx + self.rows_nbr > len(self.elements):
            self.scroll_indx = len(self.elements) - self.rows_nbr
            return

        if self.selection_indx != -999:
            self.selection_indx -= 1

        offset = self.scroll_indx
        for indx in range(0, self.rows_nbr):
            if indx + offset < len(self.elements):
                self.updateElement(indx, value=self.elements[indx + offset].rstrip('.ini'))
            else:
                self.updateElement(indx, value="")

    def dropListDown(self, *args):
        target_state_down = not self.state_down

        if not target_state_down:
            if self.selection_indx != -999:
                # in case of list collapsing, calculate new selection index
                self.selection_indx = self.scroll_indx + self.selection_indx
            self.scroll_indx = 0

        for indx in range(self.rows_nbr):
            # reset list when collapsing
            if not target_state_down:
                if indx < len(self.elements):
                    self.updateElement(indx, value=self.elements[indx])
                    self.displayElement(indx, int(target_state_down))
                else:
                    self.clearElement(indx)
            else:
                # display only rows with content
                if indx < len(self.elements):
                    self.updateElement(indx, value=self.elements[indx])
                    self.displayElement(indx, int(target_state_down))

        self.state_down = target_state_down

    def addElement(self, element):
        if self.state_down:
            self.dropListDown()
        self.elements.append(format_filename_for_list(element))

    def setElements(self, elements):
        if self.state_down:
            self.dropListDown()
        self.elements = []
        for e in elements:
            self.addElement(e)
        try:
            self.selection_indx = self.elements.index(ac.getText(self.list_head))
        except ValueError:
            self.selection_indx = -999

    def select(self, element):
        if self.state_down:
            self.dropListDown()
        self.selection_indx = self.elements.index(element)
        ac.setText(self.list_head, element)


def read_reference_file(path):
    global reference_stage_time_int
    with open(path, "r") as file:
        data = file.readlines()

    ret = []

    for line in data:
        if line.startswith("Car:") or line.startswith("Date:") or line.startswith("Driver:") or line.startswith("Time:") or line.startswith("#"):
            continue
        spline, tim = line.split(";")
        ret.append((float(spline), int(tim)))

    # get stage time from filename
    filename = os.path.basename(path)  # get filename from path
    basename, ext = os.path.splitext(filename)  # split filename into basename and extension
    stage_time_str, driver, car = basename.split("_")  # split basename into stage time, driver and car
    reference_stage_time_int = int(stage_time_str[:2]) * 60000 + int(stage_time_str[3:5]) * 1000 + int(stage_time_str[6:])  # convert stage time string to integer

    ac.setText(window_timing.label_ref, "Target:   " + str(int(reference_stage_time_int // 60000)).zfill(2) + ":" + str(int((reference_stage_time_int % 60000) // 1000)).zfill(2) + "." + str(int(reference_stage_time_int % 1000)).zfill(3))

    return ret


def write_reference_file(origin_data, path, time):
    filename = str(int(time // 60000)).zfill(2) + "." + str(time // 1000 % 60).zfill(2) + "." + str(int(time % 1000)).zfill(3) + "_" + ac.getDriverName(0) + "_" + ac.getCarName(0).replace("_", "-") + ".refl"
    weather = get_weather()
    write = ["#Car: " + ac.getCarName(0),
             "\n#Date: " + datetime.now().strftime("%d-%m-%Y, %H:%M:%S"),
             "\n#Driver: " + ac.getDriverName(0),
             "\n#Stage time: " + str(int(time // 60000)).zfill(2) + "." + str(time // 1000 % 60).zfill(2) + "." + str(int(time % 1000)).zfill(3),
             "\n#Speed on startline: {:.2f}".format(StartSpeed) + " km/h",
             "\n#Comments: ",
             "\n#Weather: " + weather["WEATHER"]["NAME"],
             "\n#Temperature Road: " + weather["TEMPERATURE"]["ROAD"],
             "\n#Temperature Air: " + weather["TEMPERATURE"]["AMBIENT"],
             "\n#Wind: " + weather["WIND"]["SPEED_KMH_MAX"] + "km/h from " + weather["WIND"]["DIRECTION_DEG"] + "deg\n"]
    for data in origin_data:
        write.append(str(data[0]) + ";" + str(data[1]) + "\n")
    with open(path + "/" + filename, "w") as file:
        ac.log("[" + AppName + "]" + "INFO: Writing to" + file.name)
        file.writelines(write)
        file.close()
    window_choose_reference.list.addElement(filename.replace(".refl", ""))


def format_filename_for_list(name):
    splitted = name.split("_")
    concated = " " * 4 + splitted[0] + " " * 2  # time
    concated += "_".join(splitted[1:-1]).ljust(18)  # padded name
    concated += splitted[-1].replace(".refl", "").replace("-", " ")  # car name
    return concated


def get_weather():
    data = {}
    log_path = os.path.join(os.environ['USERPROFILE'], 'documents', 'Assetto Corsa', 'logs', 'log.txt')
    with open(log_path, 'r') as file:
        stop = False
        for line in file:
            if stop and line.startswith('['):
                break
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                key = line[1:-1]
                if key in ['TEMPERATURE', 'WEATHER', 'WIND']:
                    data[key] = {}
                    if len(data) == 3:
                        stop = True
            elif '=' in line and key in ['TEMPERATURE', 'WEATHER', 'WIND']:
                sub_key, value = line.split('=')
                data[key][sub_key] = value
    return data


def fix_reffile_amount_and_choose_fastest():
    global reference_data

    fastest_time = 2000000000
    fastest_file = 0
    num_files = 0
    slowest_time = 0
    slowest_file = ""
    car = ac.getCarName(0).replace("_", "-")  # get current car name
    driver = ac.getDriverName(0)  # get current driver name
    for e in window_choose_reference.list.elements:
        time = 60000 * int(e[4:6]) + 1000 * int(e[7:9]) + int(e[10:13])
        # slowest
        if MaxRefFiles != 0 and e[15:33].strip() == driver and e[33:].replace(" ", "-") == car:
            if time > slowest_time:
                slowest_time = time
                slowest_file = e[4:13] + "_" + e[15:33].strip() + "_" + e[33:].replace(" ", "-")
                num_files += 1
        # fastest
        if time < fastest_time and e[15:33].strip() == driver and e[33:].replace(" ", "-") == car:  # add condition to match current car and player name
            fastest_time = time
            fastest_file = e[4:13] + "_" + e[15:33].strip() + "_" + e[33:].replace(" ", "-")

    if num_files > MaxRefFiles and MaxRefFiles != 0:
        os.remove(ReferenceFolder + "/" + slowest_file + ".refl")
        window_choose_reference.refilterList()

        # delete more if there are too many
        if num_files - 1 > MaxRefFiles:
            fix_reffile_amount_and_choose_fastest()

    if fastest_file != 0:
        reference_data = read_reference_file(ReferenceFolder + "/" + fastest_file + ".refl")
        window_choose_reference.list.select(format_filename_for_list(fastest_file))

