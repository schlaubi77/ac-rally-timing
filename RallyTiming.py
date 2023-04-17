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
        write_reference_file(data_collected, ReferenceFolder, info.graphics.iLastTime)
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

    def __init__(self, name, path, x=154, y=120):
        self.name = name
        self.window = ac.newApp(name)
        ac.setSize(self.window, x, y)
        ac.setIconPosition(self.window, 16000, 16000)

        self.reffiles = os.listdir(path)
        self.reffile_index = 0
        self.currently_used_index = None

        self.activated = False
        ac.addOnAppActivatedListener(self.window, on_reference_activate)
        ac.addOnAppDismissedListener(self.window, on_reference_deactivate)

        self.down_button = ac.addButton(self.window, "-")
        ac.setPosition(self.down_button, 5, 25)
        ac.setSize(self.down_button, 22, 22)
        ac.addOnClickedListener(self.down_button, on_reference_minus)

        self.up_button = ac.addButton(self.window, "+")
        ac.setPosition(self.up_button, 127, 25)
        ac.setSize(self.up_button, 22, 22)
        ac.addOnClickedListener(self.up_button, on_reference_plus)

        self.label = ac.addLabel(self.window, lang["ref.nofiles"])  # max 13 chars per line
        ac.setPosition(self.label, 32, 25)
        ac.setSize(self.label, 90, 20)

        self.confirm_button = ac.addButton(self.window, lang["ref.choose"])
        ac.setPosition(self.confirm_button, 35, 90)
        ac.setSize(self.confirm_button, 84, 25)
        ac.addOnClickedListener(self.confirm_button, on_reference_select)

        self.change_reffile_index(0)

    def set_text(self, text):
        ac.setText(self.label, text)

    def set_color(self, r, g, b):
        ac.setFontColor(self.label, r, g, b, 1)

    def change_reffile_index(self, mode):
        if len(self.reffiles) == 0:
            self.set_text(lang["ref.nofiles"])
            return
        if mode == "+":
            self.reffile_index += 1
            if self.reffile_index >= len(self.reffiles):
                self.reffile_index = 0
        elif mode == "-":
            self.reffile_index -= 1
            if self.reffile_index < 0:
                self.reffile_index = len(self.reffiles) - 1
        elif mode == 0:
            self.reffile_index = 0
        else:
            ac.log("[" + AppName + "]" + "SEVERE: No change mode set")
            return

        filename = self.reffiles[self.reffile_index]
        self.set_text(filename.split("_")[0] + "\n" + filename.split("_")[1] + "\n" + filename.split("_")[2].replace(".refl", "")[:16])

        if self.reffile_index == self.currently_used_index:
            self.set_color(0, 1, 0)
        else:
            self.set_color(1, 1, 1)


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
    window_choose_reference.reffiles.append(filename)
    on_reference_plus()
    on_reference_minus()


def on_open_delta_page(*args):
    if window_choose_reference.activated:
        window_choose_reference.activated = False
        ac.setVisible(window_choose_reference.window, 0)
    else:
        window_choose_reference.activated = True
        ac.setVisible(window_choose_reference.window, 1)


def on_reference_plus(*args):
    window_choose_reference.change_reffile_index("+")


def on_reference_minus(*args):
    window_choose_reference.change_reffile_index("-")


def on_reference_activate(*args):
    window_choose_reference.activated = True


def on_reference_deactivate(*args):
    window_choose_reference.activated = False


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
