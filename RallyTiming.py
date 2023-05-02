#####################################################
# Rally Timing v1.0                                 #
# by wimdes 4/04/2023                               #
# thx to Hecrer, schlaubi77, PleaseStopThis, GPT-4  #
#                                                   #
# Find the AC Rally Wiki on Racedepartment:         #
# https://bit.ly/3HCELP3                            #
#                                                   #
# changelog:                                        #
#                                                   #
#####################################################
# TODO:                                             #
# cleanup code                                      #
# reset track data button                           #
# access options through GUI                        #
# add replay detection                              #
# add delta timing, linear bar
#
#####################################################
from datetime import datetime
import sys, ac, acsys, os, json, math, configparser
from sim_info import info

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

###### Determine track name & layout
if ac.getTrackConfiguration(0) != "": 
    TrackName = (ac.getTrackName(0) + "/" + ac.getTrackConfiguration(0))
else: 
    TrackName = ac.getTrackName(0)

###### Reference Laps
ReferenceFolder = "apps/python/RallyTiming/referenceLaps/" + TrackName

window_choose_reference = 0
reference_data = []
data_collected = []
last_ref_index = 0
line_delta = 0

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

###### write some stuff into log and console
ac.console (AppName + ": Track Name: " + TrackName)
#ac.console (AppName + ": Start Spline: {:.10f}".format(StartSpline))
#ac.console (AppName + ": Finish Spline: {:.10f}".format(FinishSpline))
#ac.console (AppName + ": Meter: {:.10f}".format(Meter))
#ac.console (AppName + ": Centimeter: {:.10f}".format(Meter / 100))
#ac.log(AppName + " test entry")


def acMain(ac_version):
    global line1, line2, line3, line4, line5, line6, line7, line_delta, window_choose_reference, appWindow

    appWindow = ac.newApp(AppName)

    if not DebugMode:
        if not ShowFuel:
            ac.setSize(appWindow, 373, 112)    #default is 373,92
        else:
            ac.setSize(appWindow, 373, 132)
    else:
        ac.setSize(appWindow, 580, 192)
    ac.setTitle(appWindow, "")
    ac.drawBorder(appWindow, 0)
    ac.setIconPosition(appWindow, 0, -10000)
    ac.setBackgroundOpacity(appWindow, 0.1)

    window_choose_reference = ChooseReferenceWindow("Reference Laps", "apps/python/RallyTiming/referenceLaps/" + TrackName)

    lines = []
    for i in range(7):
        line = ac.addLabel(appWindow, "")
        lines.append(line)
        ac.setPosition(line, 10, 5 + 25*i)
        ac.setFontSize(line, 20)
    line1, line2, line3, line4, line5, line6, line7 = lines

    line_delta = ac.addLabel(appWindow, "+0.000")
    ac.setPosition(line_delta, 160, 80)
    ac.setFontSize(line_delta, 20)

    return AppName


def acUpdate(deltaT):
    global line1, line2, line3, line4, line5, line6, line7
    global Status, ActualSpline, ActualSpeed, StartSpline, FinishSpline, StartSpeed, StartDistance, LastSessionTime, StartPositionAccuracy, LapCountTracker
    global SpeedTrapValue, StartChecked, data_collected, last_ref_index

    ActualSpline = ac.getCarState(0, acsys.CS.NormalizedSplinePosition)
    ActualSpeed = ac.getCarState(0, acsys.CS.SpeedKMH) 
    StartDistance = (StartSpline - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength
    FinishDistance = (FinishSpline - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength
    LapTime = ac.getCarState(0, acsys.CS.LapTime) 
    LapCount = ac.getCarState(0, acsys.CS.LapCount)
    ac.addOnChatMessageListener(appWindow, chat_message_listener)

    if Status == 0 and LapTime > 0:
        StartSpline = ActualSpline
        Status = 1 # Start Found
        StartFinishSplines[TrackName]["StartSpline"] = ActualSpline
        with open(StartFinishJson, "w") as file:
            json.dump(StartFinishSplines, file, indent=4)

    if Status == 1 and ActualSpline < StartSpline:
        Status = 2 # Drive to start

    if Status == 2 and 0 < StartDistance < MaxStartLineDistance and ActualSpeed < 0.05:
        Status = 6 # stopped at startline
        ac.setFontColor(line1, 0, 1, 0, 1)

    if Status == 6 and StartDistance > MaxStartLineDistance:
        ac.setFontColor(line1, 1, 1, 1, 1)
        Status = 2 # Drive back to start

    if (Status == 2 or Status == 6) and ActualSpline > StartSpline:
        StartSpeed = ActualSpeed
        StartPositionAccuracy = abs((StartSpline - ActualSpline) * SplineLength)
        ac.setFontColor(line1, 1, 1, 1, 1)
        Status = 3 # In stage

    if (Status == 3 or Status == 5) and LapCount > LapCountTracker:
        write_reference_file(data_collected, ReferenceFolder, info.graphics.iLastTime if info.graphics.iLastTime > 0 else info.graphics.iCurrentTime)
        Status = 4 # Over finish
        if FinishSpline == 0:
            FinishSpline = ActualSpline
            TrueLength = (FinishSpline-StartSpline) * SplineLength
            StartFinishSplines[TrackName]["FinishSpline"] = ActualSpline
            StartFinishSplines[TrackName]["TrueLength"] = TrueLength
            with open(StartFinishJson, "w") as file:
                json.dump(StartFinishSplines, file, indent=4)

    if OnServer:
        if Status == 3 and SpeedTrapValue > StartSpeedLimit:
            Status = 5 # START FAIL - ONLINE LAP WILL BE INVALIDATED
            StatusList[4] = lang["phase.invalidatedserver"]
            ac.setFontColor(line1, 1, 0, 0, 1)
            ac.console (AppName + ": Local StartSpeed: {:.2f}".format(StartSpeed) + " / Server StartSpeed: {:.2f}".format(SpeedTrapValue))
            StartChecked = True
        if Status == 3 and SpeedTrapValue <= StartSpeedLimit and not StartChecked:
            if SpeedTrapValue != 0:
                ac.console (AppName + ": Local StartSpeed: {:.2f}".format(StartSpeed) + " / Server StartSpeed: {:.2f}".format(SpeedTrapValue))
                StartChecked = True
    else:
        if Status == 3 and StartSpeed > StartSpeedLimit:
            Status = 5 # START FAIL
            ac.setFontColor(line1, 1, 0, 0, 1)

    if (Status == 3 or Status == 4 or Status == 5) and ActualSpline < StartSpline:
        data_collected = []
        last_ref_index = 0
        Status = 2 # Drive to start
        LapCountTracker = LapCount
        ac.setFontColor(line1, 1, 1, 1, 1)
        StartSpeed = 0
        SpeedTrapValue = 0
        StartChecked = False
        StatusList[4] = lang["phase.finished"]

    if (Status == 2 or Status == 6):
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

    if (Status == 3 or Status == 5):
            if ShowStartSpeed:
                if OnServer:
                    ac.setText(line2, lang["startspeed"] + "{:.2f}".format(SpeedTrapValue) + " km/h " + lang["inbrack.server"])
                else:
                    ac.setText(line2, lang["startspeed"] + "{:.2f}".format(StartSpeed) + " km/h")
            if ShowRemainingDistance:
                if FinishSpline != 0:
                    ac.setText(line3, lang["startdist"] + ": {:.0f}".format(FinishDistance) + " m")
                else:
                    ac.setText(line3, lang["startdist"] + ": {:.0f}".format((1 - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength) + " m " + lang["inbrack.estimated"])
            else:
                ac.setText(line3, "")
            data_collected.append((ActualSpline, time))

    # SCH time print

    ac.setText(line4,  lang["time"] + str(int(time // 60000)).zfill(2) + ":" + str(int((time % 60000) // 1000)).zfill(2) + "." + str(int(time % 1000)).zfill(3))
    do_delta(time)

    ac.setText(line1, StatusList[Status])

    if ShowFuel:
        ac.setText(line5, lang["fuel"] + "{:.1f}".format(info.physics.fuel) + " l")

    if DebugMode:
        ac.setText(line5, "StartPositionAccuracy: {:.2f}".format(StartPositionAccuracy))
        ac.setText(line6, "ActualSpline: {:.5f}".format(ActualSpline) + "  StartSpline: {:.5f}".format(StartSpline) + "  FinishSpline: {:.5f}".format(FinishSpline))
        ac.setText(line7, "XYStartDistance: {:.2f}".format(XYStartDistance()) + "  LapCount: {}".format(LapCount) + "  SpeedTrapValue: {}".format(SpeedTrapValue))


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
        self.window = ac.newApp(name)
        ac.setSize(self.window, x, y)
        ac.setIconPosition(self.window, 16000, 16000)

        self.list = SelectionList(1, 20, 35, [str(p).replace(".refl", "") for p in os.listdir(path)], self.window, height=300, width=450)  #### procede


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

        reference_data = read_reference_file(ReferenceFolder + "/" + ac.getText(self.selection_button) + ".refl")
        last_ref_index = 0
        ac.log(str(reference_data))
        # collapse list
        self.list_handler.dropListDown(0, 0)


class SelectionList:
    def __init__(self, list_id, pos_x, pos_y, data, window, height=200, width=150):
        self.parent_window = window

        self.list_id = list_id
        self.btn_size = round(20)
        self.width = width
        self.row_height = self.btn_size
        self.height = height
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.rows_nbr = 0
        self.elements = data
        self.list_elements = []
        self.scroll_indx = 0
        self.selection_indx = -999
        self.state_down = False
        self.scrollable = True
        self.handler_drop_down = self.dropListDown
        self.handler_scroll_up = self.scrollListUp
        self.handler_scroll_down = self.scrollListDown

        # header
        self.list_head = ac.addButton(self.parent_window , "")
        ac.log("Test" + str(self.list_head))
        ac.setSize(self.list_head, self.width, self.row_height)
        ac.setPosition(self.list_head, self.pos_x, self.pos_y)
        ac.setFontSize(self.list_head, round(15))
        ac.setFontAlignment(self.list_head, "center")
        ac.drawBorder(self.list_head, 1)
        ac.setBackgroundOpacity(self.list_head, 0.0)
        ac.setVisible(self.list_head, 1)

        self.head_button = ac.addButton(self.parent_window , "v")
        ac.setSize(self.head_button, self.btn_size, self.btn_size)
        ac.setPosition(self.head_button, self.pos_x + self.width, self.pos_y)
        ac.setFontSize(self.head_button, round(15))
        ac.setFontAlignment(self.head_button, "center")
        ac.drawBorder(self.head_button, 1)
        ac.setBackgroundOpacity(self.head_button, 0.0)
        ac.addOnClickedListener(self.head_button, self.handler_drop_down)
        ac.setVisible(self.head_button, 1)

        # labels with setups
        self.createSelectionButtons()

    def createSelectionButtons(self):
        # calculate max number of list rows that will fit app window (minus 1 for some space below it)
        self.rows_nbr = ((self.height - self.pos_y - self.row_height) // self.row_height) - 1

        for i in range(self.rows_nbr):
            pos_y = ((i + 1) * self.row_height) + self.pos_y
            ac.log("called with i=" + str(i))

            self.list_elements.append(
                SelectionListElement(i, self, ac.addButton(self.parent_window , ""), ac.addButton(self.parent_window , "")))

            # define element part
            ac.setVisible(self.list_elements[i].selection_button, 0)
            ac.setSize(self.list_elements[i].selection_button, self.width, self.row_height)
            ac.setPosition(self.list_elements[i].selection_button, self.pos_x, pos_y)
            ac.setFontSize(self.list_elements[i].selection_button, round(15))
            ac.setFontAlignment(self.list_elements[i].selection_button, "center")
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
                ac.log("Added 1")
                ac.addOnClickedListener(self.list_elements[i].scroll_button, self.handler_scroll_up)
                ac.setText(self.list_elements[i].scroll_button, "^")
                ac.log(str(ac.drawBorder(self.list_elements[i].scroll_button, 1)))
                ac.setBackgroundOpacity(self.list_elements[i].scroll_button, 0.9)
            else:
                if i == (self.rows_nbr - 1):
                    ac.log("Added 2")
                    ac.addOnClickedListener(self.list_elements[i].scroll_button, self.handler_scroll_down)
                    ac.setText(self.list_elements[i].scroll_button, "v")
                    ac.drawBorder(self.list_elements[i].scroll_button, 1)
                    ac.setBackgroundOpacity(self.list_elements[i].scroll_button, 0.9)

    def updateElement(self, indx, value=None, colour=None):
        if 0 <= indx < self.rows_nbr:
            if value is not None:
                ac.setText(self.list_elements[indx].selection_button, value)
                if indx == self.selection_indx and colour is None:
                    ac.setFontColor(self.list_elements[indx].selection_button, *white)
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

    def dropListDown(self, dummy, variable):
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
        self.elements.append(element)
        self.list_elements = []
        self.createSelectionButtons()


def read_reference_file(path):
    with open(path, "r") as file:
        data = file.readlines()

    ret = []

    for line in data:
        if line.startswith("Car:") or line.startswith("Date:") or line.startswith("Driver:") or line.startswith("Time:"):
            continue
        spline, tim = line.split(";")
        ret.append((float(spline), int(tim)))

    return ret


def write_reference_file(origin_data, path, time):
    filename = str(int(time // 60000)).zfill(2) + "." + str(time // 1000 % 60).zfill(2) + "." + str(int(time % 1000)).zfill(3) + "_" + ac.getDriverName(0) + "_" + ac.getCarName(0).replace("_", "-") + ".refl"
    write = ["Car: " + ac.getCarName(0),
             "\nDate: " + datetime.now().strftime("%d-%m-%Y, %H:%M:%S"),
             "\nDriver: " + ac.getDriverName(0),
             "\nTime: " + str(int(time // 60000)).zfill(2) + "." + str(time // 1000 % 60).zfill(2) + "." + str(int(time % 1000)).zfill(3) + "\n"]
    for data in origin_data:
        write.append(str(data[0]) + ";" + str(data[1]) + "\n")
    with open(path + "/" + filename, "w") as file:
        ac.log("[" + AppName + "]" + "INFO: Writing to" + file.name)
        file.writelines(write)
        file.close()
    window_choose_reference.list.addElement(filename.replace(".refl", ""))


def on_reference_select(*args):
    global reference_data
    if len(window_choose_reference.reffiles) == 0:
        return
    filename = window_choose_reference.reffiles[window_choose_reference.reffile_index]
    reference_data = read_reference_file(ReferenceFolder + "/" + filename)
    window_choose_reference.currently_used_index = window_choose_reference.reffile_index
    window_choose_reference.set_color(0, 1, 0)
    ac.log("[" + AppName + "]" + "INFO: Loaded " + filename + " with index " + str(window_choose_reference.reffile_index))


def do_delta(time):
    global last_ref_index
    if last_ref_index >= len(reference_data):
        last_ref_index = len(reference_data) - 1

    if len(reference_data) == 0:
        ac.setFontColor(line_delta, 1, 1, 1, 1)
        ac.setText(line_delta, "+0.000")
        return

    while reference_data[last_ref_index][0] < ac.getCarState(0, acsys.CS.NormalizedSplinePosition):
        if len(reference_data) > last_ref_index + 1:
            last_ref_index += 1
        else:
            break

    delta = time - reference_data[last_ref_index][1]
    if delta > 0:
        ac.setFontColor(line_delta, 1, 0, 0, 1)
        ac.setText(line_delta, "+" + str(int(delta // 1000)) + "." + str(int(delta % 1000)))
    else:
        ac.setFontColor(line_delta, 0, 1, 0, 1)
        ac.setText(line_delta, "-" + str(int(abs(delta) // 1000)) + "." + str(int(abs(delta) % 1000)))
