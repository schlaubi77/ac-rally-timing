#######################################################################
# Rally Timing v1.60                                                  #
#                                                                     #
# Copyright wimdes & schlaubi77 04/07/2023                            #
# Released under the terms of GPLv3                                   #
# thx to Hecrer, PleaseStopThis, NightEye87, KubaV383, wmialil, GPT-4 #
#                                                                     #
# Find the AC Rally Wiki on Racedepartment: https://bit.ly/3HCELP3    #
#                                                                     #
# changelog:                                                          #
# v1.60 add auto save replay with reference files                     #
# v1.55 fix start/finish registration (new bug introduced in 1.54)    #
# v1.54 adjustable interval for refl file creation                    #
#       fix YN buttons not disappearing & truelength registration     #
#       clear reference data & chooser window after deleting reffiles #
# v1.53 several fixes and improvements for timings with replays       #
#       close reference chooser when collapsing main window           #
#       don't try showing delta & splits without target time          #
# v1.52 correct 'show splits' in config file, some metadata in .refl  #
#       add buttons to reset start/finish data & delete .refl files   #
#       fix for FinishSpline = 0 resulting in car position not shown  #
#       create new StartFinishSplines.json if none                    #
#       include ctypes, write startposition accuracy in logs          #
#       use triangles instead of quad for car position                #
# v1.51 add another window, containing section delta pop-ups          #
# v1.50 add linear map display showing split timing & progress        #
#       fix replay messing up reference files                         #
# v1.42 added buttons to toggle the sub-apps                          #
# v1.41 add wheel button option for car reset                         #
#       reorganized app settings in CM                                #
#       add in-game time & weather values check                       #
# v1.40 smoothen delta timing by time interpolation                   #
#       make delta time digits configurable                           #
#       add car reset key, config in CM                               #
# v1.33 updated delta algorithm                                       #
#       fix weather information when online                           #
#       some code cleanup                                             #
# v1.32 fix for sim_info not loading                                  #
# v1.31 some small fixes                                              #
# v1.3 added delta functionality                                      #
# v1.2 settings configurable in ContentManager GUI                    #
# v1.1 add multi language support                                     #
#                                                                     #
#######################################################################
# TODO:                                                               #
# cleanup code                                                        #
# add icons, add invalidate option (wheels off track)                 #
#######################################################################
from datetime import datetime
import sys, ac, acsys, os, json, math, configparser, time
sysdir='apps/python/RallyTiming/libs'
sys.path.insert(0, sysdir)
os.environ['PATH'] = os.environ['PATH'] + ";."
import ctypes, shutil
from ctypes import wintypes, windll
from libs.sim_info import info

config = configparser.ConfigParser(inline_comment_prefixes=';')
config.optionxform = str

###### App settings from config file
config.read("apps/python/RallyTiming/config/config.ini")
StartSpeedLimit = config.getint("STARTVERIFICATION", "startspeedlimit")
MaxStartLineDistance = config.getfloat("STARTVERIFICATION", "maxstartlinedistance")
ShowStartSpeed = config.getboolean("STARTVERIFICATION", "showstartspeed")
ShowRemainingDistance = config.getboolean("GUIOPTIONS", "showremainingdistance")
ShowFuel = config.getboolean("GUIOPTIONS", "showfuel")
Language = config.get("GUIOPTIONS", "language")
DebugMode = config.getboolean("OTHERSETTINGS", "debugmode")
MaxRefFiles = config.getint("OTHERSETTINGS", "maximumreffiles")
RefFileRefreshInterval = round(1000 / config.getint("OTHERSETTINGS", "reffilerefreshrate"))
DeltaDecimalDigits = config.getint("OTHERSETTINGS", "deltadecimals")
ResetKey = config.getint("RESETKEY", "resetkey")
EnableWheelButton = config.getboolean("RESETWHEEL", "enablewheelbutton")
WheelID = config.getint("RESETWHEEL", "wheelid") - 1
ButtonID = config.getint("RESETWHEEL", "buttonid") - 1
save_replay = config.getboolean("REPLAY", "replaysave")
ReplayIntro = config.getint("REPLAY", "replayintro")
ReplayOutro = config.getint("REPLAY", "replayoutro")


with open("apps/python/RallyTiming/config/lang.json", "r", encoding="utf-8") as file:
    lang = json.load(file)
lang = lang[str(Language)]

###### Default variables
AppName = "Rally Timing"
appWindow = 0
StartFinishJson = "apps/python/RallyTiming/StartFinishSplines.json"
SplineLength = ac.getTrackLength(0)
Status = 0  # 0 = Start Undefined, 1 = Start Found, 2 = Drive to start, 3 = in stage, 4 = over finish, 5 = invalidated, 6 = stopped at startline
StatusList = [lang["phase.detect"], lang["phase.linefound"], lang["phase.gotostart"], lang["phase.instage"],
              lang["phase.finished"], lang["phase.invalidated"], lang["phase.atstartline"]]

LapCountTracker = 0
StartPositionAccuracy = 0
Meter = 1 / SplineLength
StartSpeed = 0
SpeedTrapValue = 0
StartChecked = False
reference_stage_time_int = 0
CheckFastestTime = False
SavedReplayMode = False
LastGraphicsStatus = 0

###### Determine track name & layout
if ac.getTrackConfiguration(0) != "":
    TrackName = (ac.getTrackName(0) + "/" + ac.getTrackConfiguration(0))
else:
    TrackName = ac.getTrackName(0)

###### Reference Laps
ReferenceFolder = "apps/python/RallyTiming/referenceLaps/" + TrackName

window_choose_reference = 0
window_timing = 0
window_progress_bar = 0
window_split_notification = 0
reference_data = []
data_collected = []
num_splits = config.getint("SPLITS", "splitnumber")
split_times = [-1 for _ in range(num_splits + 1)]
button_open_timing = 0
button_open_map = 0
button_expand_main = 0
main_expanded = False
appWindowSize = (0, 0)

if not os.path.exists(ReferenceFolder):
    os.makedirs(ReferenceFolder)

###### Determine if local game or on server
if ac.getServerName() == "":
    OnServer = False
else:
    OnServer = True
    StatusList[5] = lang["phase.invalidatedserver"]

###### Load start and finish positions from json file
try:
    with open(StartFinishJson, "r") as file:
        StartFinishSplines = json.load(file)
except FileNotFoundError:
    StartFinishSplines = {}
    StartSpline = 0
    FinishSpline = 1.0001   # add slight offset that can be detected
    TrueLength = (FinishSpline - StartSpline) * SplineLength
    StartFinishSplines[TrackName] = {"StartSpline": StartSpline, "FinishSpline": FinishSpline, "TrueLength": round(TrueLength)}
else:
    StartSpline = StartFinishSplines.get(TrackName, {}).get("StartSpline", 0)
    FinishSpline = StartFinishSplines.get(TrackName, {}).get("FinishSpline", 1.0001)
    TrueLength = StartFinishSplines.get(TrackName, {}).get("TrueLength", 0)
    if TrueLength == 0:
        TrueLength = (FinishSpline - StartSpline) * SplineLength
    Status = 1 if StartSpline else 0
    if FinishSpline == 0:    # fix for bad finishspline data in old files
        FinishSpline = 1.0001
    if FinishSpline == 1.0001:
        TrueLength = (FinishSpline - StartSpline) * SplineLength
    if TrueLength == 0:
        TrueLength = (FinishSpline - StartSpline) * SplineLength
    StartFinishSplines[TrackName] = {"StartSpline": StartSpline, "FinishSpline": FinishSpline, "TrueLength": round(TrueLength)}
with open(StartFinishJson, "w") as file:
    json.dump(StartFinishSplines, file, indent=4)

##### Save replay init
replay_length_ini_path = ""
try:
    document_path_buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, document_path_buf)
    assetto_corsa_folder_path = document_path_buf.value + "/Assetto Corsa/"
    if not os.path.exists(assetto_corsa_folder_path + "cfg/extension/general.ini"):
        os.makedirs(assetto_corsa_folder_path + "cfg/extension/", exist_ok=True)
        open(assetto_corsa_folder_path + "cfg/extension/general.ini", 'w').close()
        ac.log(AppName + ": general.ini not found in cfg/extension folder, created new one")
    else:
        ac.log(AppName + ": Replay saving initialised")
except OSError:
    save_replay = False
    ac.log(AppName + ": Windows dlls not found. Replays will not be saved automatically")

replay_worker = 0

white = (1, 1, 1, 1)
gray = (0.75, 0.75, 0.75, 1)
green = (0, 1, 0, 1)
red = (1, 0, 0, 1)

line1, line2, line3, line4, line5, line6 = [0 for i in range(6)]

###### write some stuff into log and console
ac.console(AppName + ": Track Name: " + TrackName)
# ac.console (AppName + ": Meter: {:.10f}".format(Meter))
# ac.console (AppName + ": Centimeter: {:.10f}".format(Meter / 100))
# ac.log(AppName + " test entry")


def acMain(ac_version):
    global line1, line2, line3, line4, line5, line6, appWindow, appWindowSize
    global window_timing, window_progress_bar, window_split_notification, window_choose_reference
    global button_open_timing, button_open_map, button_open_reference, button_open_notifications, button_expand_main, button_delete_reffiles, button_reset_start_stop
    global button_delete_reffiles_y, button_delete_reffiles_n, button_reset_start_stop_y,  button_reset_start_stop_n, replay_worker

    appWindow = ac.newApp(AppName + " - Main")

    if not DebugMode:
        if not ShowFuel:
            appWindowSize = (378, 100)
        else:
            appWindowSize = (378, 120)
    else:
        appWindowSize = (580, 180)

    ac.setSize(appWindow, *appWindowSize)

    ac.setTitle(appWindow, "")
    ac.drawBorder(appWindow, 0)
    ac.setIconPosition(appWindow, 0, -10000)
    ac.setBackgroundOpacity(appWindow, 0.1)

    button_open_timing = create_button(lang["button.opentiming"], 10, appWindowSize[1], 150, 25, listener=toggle_timing_window)
    button_open_map    = create_button(lang["button.openmap"],   170, appWindowSize[1], 150, 25, listener=toggle_map)
    button_open_reference =     create_button(lang["button.openreference"],     10, appWindowSize[1] + 34, 310, 25, listener=toggle_reference)
    button_open_notifications = create_button(lang["button.opennotifications"], 10, appWindowSize[1] + 68, 310, 25, listener=toggle_notifications)

    button_delete_reffiles =  create_button(lang["button.deletereffiles"], 10, appWindowSize[1] + 102, 310, 25, color=(0.8,0,0), listener=show_delete_yn)
    button_delete_reffiles_y = create_button("Y", 320, appWindowSize[1] + 102, 25, 25, listener=delete_reffiles)
    button_delete_reffiles_n = create_button("N", 345, appWindowSize[1] + 102, 25, 25, listener=hide_delete_yn)

    button_reset_start_stop = create_button(lang["button.resetstartstop"], 10, appWindowSize[1] + 136, 310, 25, color=(0.8,0,0), listener=show_reset_yn)
    button_reset_start_stop_y = create_button("Y", 320, appWindowSize[1] + 136, 25, 25, listener=reset_start_stop)
    button_reset_start_stop_n = create_button("N", 345, appWindowSize[1] + 136, 25, 25, listener=hide_reset_yn)

    button_expand_main = create_button("", 0, 0, 40, 100, visible=1, listener=toggle_button_display)
    ac.drawBorder(button_expand_main, 0)
    ac.setBackgroundOpacity(button_expand_main, 0)

    window_choose_reference = ChooseReferenceWindow("Rally Timing - Reference Laps", "apps/python/RallyTiming/referenceLaps/" + TrackName)
    window_split_notification = SplitNotificationWindow()
    window_timing = TimingWindow()
    window_progress_bar = ProgressBarWindow()

    replay_worker = SaveReplayWorker(assetto_corsa_folder_path, "apps/python/RallyTiming/replays/" + TrackName + "/", save_replay)

    lines = []
    for i in range(6):
        line = ac.addLabel(appWindow, "")
        lines.append(line)
        ac.setPosition(line, 10, 5 + 25 * i)
        ac.setFontSize(line, 20)
    line1, line2, line3, line4, line5, line6 = lines

    fix_reffile_amount_and_choose_fastest()

    return AppName


def acUpdate(deltaT):
    global line1, line2, line3, line4, line5, line6
    global Status, ActualSpline, ActualSpeed, StartSpline, FinishSpline, TrueLength, StartSpeed, StartDistance, LastSessionTime, StartPositionAccuracy, LapCountTracker
    global SpeedTrapValue, StartChecked, data_collected, CheckFastestTime, SavedReplayMode, LastGraphicsStatus, replay_worker

    ActualSpline = ac.getCarState(0, acsys.CS.NormalizedSplinePosition)
    ActualSpeed = ac.getCarState(0, acsys.CS.SpeedKMH)
    StartDistance = (StartSpline - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength
    FinishDistance = (FinishSpline - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength
    LapTime = ac.getCarState(0, acsys.CS.LapTime)
    LapCount = ac.getCarState(0, acsys.CS.LapCount)
    ac.addOnChatMessageListener(appWindow, chat_message_listener)


    # detect when a replay from disk is playing (game starting straight into replay mode)
    if LastGraphicsStatus == 0:
        if info.graphics.status == 1:
            SavedReplayMode = True
            LastGraphicsStatus = 1
            ac.log(AppName + ": Saved replay mode detected")
            ac.console(AppName + ": Saved replay mode detected")
        if info.graphics.status == 2:
            LastGraphicsStatus = 2

    # reset key or button pressed
    if ac.ext_isButtonPressed(ResetKey):
        ac.ext_resetCar()
    if EnableWheelButton:
        if ac.ext_isJoystickButtonPressed(WheelID, ButtonID):
            ac.ext_resetCar()

    # searching startline, but now crossed => save position
    if Status == 0 and LapTime > 0:
        StartSpline = ActualSpline
        Status = 1  # Start Found
        StartFinishSplines[TrackName]["StartSpline"] = ActualSpline
        with open(StartFinishJson, "w") as file:
            json.dump(StartFinishSplines, file, indent=4)

    # start found and ahead of start => drive to start
    if Status == 1 and ActualSpline < StartSpline:
        Status = 2  # Drive to start

    # driving to start, but close and standing => stopped at line
    if Status == 2 and 0 < StartDistance < MaxStartLineDistance and ActualSpeed < 0.05:
        Status = 6  # stopped at startline
        ac.setFontColor(line1, *green)

    # at startline, but now to far away
    if Status == 6 and StartDistance > MaxStartLineDistance:
        ac.setFontColor(line1, *white)
        Status = 2  # Drive back to start

    # in front of start, but now crossed startline => into stage
    if Status in (2, 6) and ActualSpline > StartSpline and info.graphics.status == 2:
        StartSpeed = ActualSpeed
        StartPositionAccuracy = abs((StartSpline - ActualSpline) * SplineLength)
        ac.console(AppName + ": StartPositionAccuracy: " + str(round(StartPositionAccuracy * 100)) + "cm - Startspeed: " + "{:.2f}".format(StartSpeed) + "km/h")
        ac.log(AppName + ": StartPositionAccuracy: " + str(round(StartPositionAccuracy * 100)) + "cm - Startspeed: " + "{:.2f}".format(StartSpeed) + "km/h")
        ac.setFontColor(line1, *white)
        Status = 3  # In stage

    # in stage, but lap done => finished
    if Status in (3, 5) and LapCount > LapCountTracker and info.graphics.status == 2:  # 0=off, 1=replay, 2=driving, 3=pause
        write_reference_file(data_collected, ReferenceFolder, info.graphics.iLastTime if info.graphics.iLastTime > 0 else info.graphics.iCurrentTime)
        replay_worker.save_replay(info.graphics.iLastTime if info.graphics.iLastTime > 0 else info.graphics.iCurrentTime)
        CheckFastestTime = True
        Status = 4  # Over finish
        if FinishSpline == 1.0001 or TrueLength == 0:
            FinishSpline = ActualSpline
            TrueLength = (FinishSpline - StartSpline) * SplineLength
            StartFinishSplines[TrackName]["FinishSpline"] = ActualSpline
            StartFinishSplines[TrackName]["TrueLength"] = round(TrueLength)
            with open(StartFinishJson, "w") as file:
                json.dump(StartFinishSplines, file, indent=4)

    # fixes for status during replays
    if info.graphics.status == 1:
        if FinishSpline == 1:
            FinishSpline = 0.9999999
        if StartSpline < ActualSpline < FinishSpline:
            Status = 3  # in stage
        if Status in (3, 5) and ActualSpline > FinishSpline:
            Status = 4  # over finish
        if Status in (3, 4, 5) and ActualSpline < StartSpline:
            Status = 2  # drive to start

    if OnServer and info.graphics.status == 2:
        if Status == 3 and SpeedTrapValue > StartSpeedLimit:
            Status = 5  # START FAIL - ONLINE LAP WILL BE INVALIDATED
            StatusList[4] = lang["phase.invalidatedserver"]
            ac.setFontColor(line1, *red)
            ac.console(AppName + ": Local StartSpeed: {:.2f}".format(StartSpeed) + " / Server StartSpeed: {:.2f}".format(SpeedTrapValue))
            StartChecked = True
        if Status == 3 and SpeedTrapValue <= StartSpeedLimit and not StartChecked:
            if SpeedTrapValue != 0:
                ac.console(AppName + ": Local StartSpeed: {:.2f}".format(StartSpeed) + " / Server StartSpeed: {:.2f}".format(SpeedTrapValue))
                StartChecked = True
    else:
        if Status == 3 and StartSpeed > StartSpeedLimit:
            Status = 5  # START FAIL
            ac.setFontColor(line1, *red)

    # reset to before start line => reset
    if Status in (3, 4, 5) and ActualSpline < StartSpline and info.graphics.status == 2:
        LapCountTracker = ac.getCarState(0, acsys.CS.LapCount)
        Status = 2  # Drive to start
        StatusList[4] = lang["phase.finished"]
        reset_variables()
        if CheckFastestTime:
            fix_reffile_amount_and_choose_fastest()
            CheckFastestTime = False

    # driving to start or at start
    if Status in (2, 6):
        if CheckFastestTime:
            fix_reffile_amount_and_choose_fastest()
            CheckFastestTime = False
        if ActualSpline == 0:
            ac.setText(line3,
                       lang["startdist"] + "{:.2f}".format(XYStartDistance()) + " m " + lang["inbrack.estimated"])
        else:
            ac.setText(line3, lang["startdist"] + "{:.2f}".format(StartDistance) + " m")
        if ShowStartSpeed:
            ac.setText(line2, lang["startspeedlimit"] + "{}".format(StartSpeedLimit) + " km/h")

    # finished?
    if Status == 4:
        ac.setText(line3, "")
        time = info.graphics.iLastTime
    else:
        time = info.graphics.iCurrentTime

    # driving in stage
    if Status in (3, 5):
        if ShowStartSpeed:
            if OnServer:
                ac.setText(line2,
                           lang["startspeed"] + "{:.2f}".format(SpeedTrapValue) + " km/h " + lang["inbrack.server"])
            else:
                ac.setText(line2, lang["startspeed"] + "{:.2f}".format(StartSpeed) + " km/h")
        if ShowRemainingDistance:
            if FinishSpline != 1.0001:
                ac.setText(line3, lang["finishdist"] + "{:.0f}".format(FinishDistance) + " m")
            else:
                ac.setText(line3, lang["finishdist"] + "{:.0f}".format(
                    (1 - ac.getCarState(0, acsys.CS.NormalizedSplinePosition)) * SplineLength) + " m " + lang[
                               "inbrack.estimated"])
        else:
            ac.setText(line3, "")

        if info.graphics.status == 2 or SavedReplayMode:
            if len(data_collected) == 0:
                data_collected.append((ActualSpline, time))
            nextfiltertime =  data_collected[-1][-1] + RefFileRefreshInterval
            nextframetime = time + round(deltaT*1000)
            if nextframetime - nextfiltertime > (round(deltaT*1000))/2:
                data_collected.append((ActualSpline, time))

    ac.setText(line1, StatusList[Status])
    window_timing.update()
    replay_worker.update()

    if ShowFuel:
        ac.setText(line4, lang["fuel"] + "{:.1f}".format(info.physics.fuel) + " l")
    if DebugMode:
        ac.setText(line4, "StartPositionAccuracy: {:.2f}".format(StartPositionAccuracy) + "  Status: {}".format(
            Status) + "  StageTimeRef: {}".format(reference_stage_time_int))
        ac.setText(line5, "ActualSpline: {:.5f}".format(ActualSpline) + "  StartSpline: {:.5f}".format(
            StartSpline) + "  FinishSpline: {:.5f}".format(FinishSpline))
        ac.setText(line6, "XYStartDistance: {:.2f}".format(XYStartDistance()) + "  LapCount: {}".format(
            LapCount) + "  SpeedTrapValue: {}".format(SpeedTrapValue))


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

        self.isActivated = False
        self.onActivate = self.on_activate
        self.onDeactivate = self.on_deactivate
        ac.addOnAppActivatedListener(self.window, self.onActivate)
        ac.addOnAppDismissedListener(self.window, self.onDeactivate)

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

        self.list = SelectionList(1, 20, 65, [str(p) for p in os.listdir(self.path)], self.window, height=300,
                                  width=450)

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
            if (self.showOtherDrivers or "_".join(e.split("_")[1:-1]) == driver) and (
                    self.showOtherCars or e.split("_")[-1] == car):
                show.append(e)
        self.list.setElements(show)

    def on_activate(self, *args):
        self.isActivated = True

    def on_deactivate(self, *args):
        self.isActivated = False

    def toggleVisibility(self):
        self.isActivated = not self.isActivated
        ac.setVisible(self.window, int(self.isActivated))


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

        self.isActivated = False
        self.onActivate = self.on_activate
        self.onDeactivate = self.on_deactivate
        ac.addOnAppActivatedListener(self.window, self.onActivate)
        ac.addOnAppDismissedListener(self.window, self.onDeactivate)

    def update(self):
        if Status in (0, 1, 2, 6):
            ac.setText(self.label_time, "Current:  00:00.000")
            ac.setFontColor(self.label_delta, *white)
            ac.setText(self.label_delta, "Delta:    +0.000")

        if Status in (3, 5):
            time = info.graphics.iCurrentTime
            self._do_delta(time)
            ac.setText(self.label_time, "Current: " + str(int(time // 60000)).zfill(2) + ":" + str(int((time % 60000) // 1000)).zfill(2) + "." + str(int(time % 1000)).zfill(3))

        if Status == 4:
            time = info.graphics.iLastTime
            ac.setText(self.label_time, "Current: " + str(int(time // 60000)).zfill(2) + ":" + str(int((time % 60000) // 1000)).zfill(2) + "." + str(int(time % 1000)).zfill(3))
            delta = time - reference_stage_time_int
            decimals = str(round(((abs(delta) % 1000)/1000), 3))[2:].zfill(3)
            seconds = str(int(abs(delta) // 1000))

            if len(reference_data) == 0:
                return

            if delta > 0:
                separator = '+'
                ac.setFontColor(self.label_delta, *red)
            else:
                separator = '-'
                ac.setFontColor(self.label_delta, *green)
            ac.setText(self.label_delta, "Delta:     " + separator + seconds + "." + decimals)

    def _do_delta(self, time):
        if len(reference_data) == 0:
            ac.setFontColor(self.label_delta, 1, 1, 1, 1)
            ac.setText(self.label_delta, "Delta:   +0.000")
            return
        ref_timepoints = searchNearest(reference_data, ac.getCarState(0, acsys.CS.NormalizedSplinePosition), 0, len(reference_data) - 1)

        try:                                    # interpolate between the two known timepoints
            ref_time = ((ac.getCarState(0, acsys.CS.NormalizedSplinePosition) - ref_timepoints[0][0]) / (ref_timepoints[1][0] - ref_timepoints[0][0])) * (ref_timepoints[1][1] - ref_timepoints[0][1]) + ref_timepoints[0][1]
        except ZeroDivisionError:               # fallback when only one point is found
            ref_time = ref_timepoints[0][1]

        delta = int(time - ref_time)
        seconds = str(abs(delta) // 1000)
        decimals = str(round(abs(delta) % 1000, -3 + DeltaDecimalDigits)).zfill(3)[:DeltaDecimalDigits]

        if delta >= 0:
            ac.setFontColor(self.label_delta, *red)
            indicator = "+"
        else:
            ac.setFontColor(self.label_delta, *green)
            indicator = "-"
        ac.setText(self.label_delta, "Delta:     " + indicator + seconds + "." + decimals)

    def on_activate(self, *args):
        self.isActivated = True

    def on_deactivate(self, *args):
        self.isActivated = False

    def toggleVisibility(self):
        self.isActivated = not self.isActivated
        ac.setVisible(self.window, int(self.isActivated))


def searchNearest(list, searched, left, right):
    if left == right:
        if list[left][0] > searched:
            return list[max(left - 1, 0)], list[left]
        else:
            return list[left], list[min(left + 1, len(list) - 1)]
    if left > right:
        return list[right], list[min(left, len(list) - 1)]
    middle = (left + right) // 2
    if list[middle][0] <= searched:
        return searchNearest(list, searched, middle + 1, right)
    else:
        return searchNearest(list, searched, left, middle - 1)


class ProgressBarWindow:
    def __init__(self, name="Rally Timing - Progress Bar"):
        self.name = name
        self.window = ac.newApp(name)
        ac.setIconPosition(self.window, 16000, 16000)

        self.isActivated = False
        self.onActivate = self.on_activate
        self.onDeactivate = self.on_deactivate
        ac.addOnAppActivatedListener(self.window, self.onActivate)
        ac.addOnAppDismissedListener(self.window, self.onDeactivate)

        ac.setTitle(self.window, "")
        ac.drawBorder(self.window, 0)
        ac.setBackgroundOpacity(self.window, 0)

        self.barWidth = config.getint("PROGRESSBAR", "progressbarwidth")
        self.barHeight = config.getint("PROGRESSBAR", "progressbarheight")
        self.windowWidth = self.barWidth + 40
        self.padding_top = 20
        self.windowHeight = self.barHeight + 2 * self.padding_top

        self.splits = config.getint("SPLITS", "splitnumber")
        self.transparency = config.getint("PROGRESSBAR", "progresstransparency") / 100
        self.show_splits = config.getboolean("PROGRESSBAR", "progresssplits")

        self.finishLine = ac.addLabel(self.window, "")
        ac.setPosition(self.finishLine, int(self.windowWidth / 2 - 15 * self.barWidth / 6),
                       self.padding_top - int(self.barWidth / 3))
        ac.setSize(self.finishLine, int(self.barWidth * 5), int(5 * self.barWidth / 6))
        ac.setBackgroundTexture(self.finishLine, "apps/python/RallyTiming/gui/finish.png")

        self.renderFunction = self.render
        ac.addRenderCallback(self.window, self.renderFunction)

        ac.setSize(self.window, self.windowWidth, self.windowHeight)

    def render(self, *args):
        ac.glColor4f(*(white[:3] + (self.transparency,)))
        ac.glQuad(self.windowWidth / 2 - self.barWidth / 2, 20, self.barWidth, self.barHeight)  # X, Y, width, height

        splinePos = ac.getCarState(0, acsys.CS.NormalizedSplinePosition)
        last_delta = 0
        split_delta_values = []

        if self.show_splits:
            current_sector = int((splinePos - StartSpline) / (FinishSpline - StartSpline) * (self.splits + 1)) + 1
            if len(reference_data) != 0:
                for i in range(1, current_sector):
                    # find if split was faster or slower
                    searchPos = (FinishSpline - StartSpline) * i / (self.splits + 1) + StartSpline
                    ref_timepoints = searchNearest(data_collected, searchPos, 0, len(data_collected) - 1)
                    try:    # interpolate between the two known timepoints
                        split_i = int(((searchPos - ref_timepoints[0][0]) / (ref_timepoints[1][0] - ref_timepoints[0][0])) * (ref_timepoints[1][1] - ref_timepoints[0][1]) + ref_timepoints[0][1])
                    except ZeroDivisionError:   # fallback when only one point is found
                        split_i = ref_timepoints[0][1]

                    ac.glColor4f(*(green[:3] + (self.transparency,)))               # color splits

#                    ac.console(str(split_i - split_times[i - 1] - last_delta))
                    if split_i - split_times[i - 1] - last_delta > 0:
                        ac.glColor4f(*(red[:3] + (self.transparency,)))
                    last_delta = split_i - split_times[i - 1]
#                    split_delta_values.append("{:.3f}".format(last_delta/1000))
#                    ac.console(str(split_delta_values))

                    ac.glBegin(1)
                    ac.glQuad(self.windowWidth / 2 - self.barWidth / 2, int(self.barHeight * (self.splits + 1 - i) / (self.splits + 1)) + 20, self.barWidth, self.barHeight / (self.splits + 1))
                    ac.glEnd()

            # draw split positions
            for i in range(1, (self.splits + 1)):
                ac.glColor4f(*(white[:3] + (self.transparency,)))
                ac.glBegin(1)
                ac.glQuad(self.windowWidth / 2 - (self.barWidth * 3) / 2, self.padding_top + self.barHeight - (i * self.barHeight / (self.splits + 1)) - self.barWidth / 6, self.barWidth * 3, self.barWidth / 3)
                ac.glEnd()

            window_split_notification.update(last_delta, current_sector)

        # draw car position
        MapPosition = self.padding_top + self.barHeight - (self.barHeight * ((splinePos - StartSpline) / (FinishSpline - StartSpline)))
        left = [self.windowWidth/2 - self.barWidth, MapPosition]
        bottom = [self.windowWidth/2, MapPosition + self.barWidth]
        right = [self.windowWidth/2 + self.barWidth, MapPosition]
        top = [self.windowWidth/2, MapPosition - self.barWidth]
        ac.glColor4f(*(red[:3] + (min(self.transparency + 0.2, 1),)))
        ac.glBegin(2)   # use 2 triangles instead of 1 quad
        ac.glVertex2f(*left)
        ac.glVertex2f(*bottom)
        ac.glVertex2f(*right)
        ac.glVertex2f(*right)
        ac.glVertex2f(*top)
        ac.glVertex2f(*left)
        ac.glEnd()

    def on_activate(self, *args):
        self.isActivated = True

    def on_deactivate(self, *args):
        self.isActivated = False

    def toggleVisibility(self):
        self.isActivated = not self.isActivated
        ac.setVisible(self.window, int(self.isActivated))


class SplitNotificationWindow:
    def __init__(self, name="Rally Timing - Split Notifications"):
        self.name = name
        self.window = ac.newApp(name)
        ac.setIconPosition(self.window, 16000, 16000)

        self.isActivated = False
        self.onActivate = self.on_activate
        self.onDeactivate = self.on_deactivate
        ac.addOnAppActivatedListener(self.window, self.onActivate)
        ac.addOnAppDismissedListener(self.window, self.onDeactivate)

        self.split_notification_duration = config.getint("SPLITS", "splitnotificationduration")
        self.split_notification_size = config.getint("SPLITS", "splitnotificationsize") / 100
        self.split_notification_transparency = config.getint("SPLITS", "splitnotificationtransparency") / 100
        
        self.default_fontsize = 20
        self.padding = 12
        self.windowWidth = self.split_notification_size * 120 + 2 * self.padding
        self.windowHeight = self.split_notification_size * self.default_fontsize + 2 * self.padding

        ac.setTitle(self.window, "")
        ac.setSize(self.window, self.windowWidth, self.windowHeight)
        ac.drawBorder(self.window, 0)
        ac.setBackgroundOpacity(self.window, self.split_notification_transparency)

        self.last_current_sector = 1
        self.last_time_shown = 2000000000

        self.label_split = ac.addLabel(self.window, "")
        ac.setPosition(self.label_split, self.padding, self.padding/2)
        ac.setFontSize(self.label_split, self.default_fontsize * self.split_notification_size)

    def update(self, delta, current_sector):
        if len(reference_data) == 0:
            return

        if current_sector > self.last_current_sector:
            if Status == 4:
                delta = int(info.graphics.iLastTime - reference_stage_time_int)
    
            decimals = str(round(abs(int(delta)) % 1000, -3 + DeltaDecimalDigits)).zfill(3)[:DeltaDecimalDigits]
            seconds = str(abs(int(delta)) // 1000)
            if delta > 0:
                separator = '+'
                ac.setFontColor(self.label_split, *red)
            else:
                separator = '-'
                ac.setFontColor(self.label_split, *green)

            ac.setText(self.label_split, "DIFF: " + separator + seconds + "." + decimals)
            self.last_time_shown = info.graphics.sessionTimeLeft
            self.last_current_sector = current_sector

        if Status != 4:
            if self.split_notification_duration * 2000 > self.last_time_shown - info.graphics.sessionTimeLeft > self.split_notification_duration * 1000:
                ac.setText(self.label_split, "")
            if current_sector == 1:
                ac.setText(self.label_split, "")

        if Status in (0, 1, 2):
            ac.setFontColor(self.label_split, *gray)
            ac.setText(self.label_split, "DIFF: --.---")

    def on_activate(self, *args):
        self.isActivated = True

    def on_deactivate(self, *args):
        self.isActivated = False

    def toggleVisibility(self):
        self.isActivated = not self.isActivated
        ac.setVisible(self.window, int(self.isActivated))


class SelectionListElement:
    def __init__(self, element_id, list_handler, selection_button, scroll_button):
        self.element_id = element_id
        self.list_handler = list_handler
        self.selection_button = selection_button
        self.scroll_button = scroll_button
        self.click_event = self.clickEvent

        ac.addOnClickedListener(self.selection_button, self.click_event)

    def clickEvent(self, dummy, variable):
        global reference_data

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
                SelectionListElement(i, self, ac.addButton(self.parent_window, ""),
                                     ac.addButton(self.parent_window, "")))

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
    global reference_stage_time_int, split_times
    with open(path, "r") as file:
        data = file.readlines()

    ret = []

    for line in data:
        if line.startswith("Car:") or line.startswith("Date:") or line.startswith("Driver:") or line.startswith(
                "Time:") or line.startswith("#"):
            continue
        spline, tim = line.split(";")
        ret.append((float(spline), int(tim)))

    # get stage time from filename
    filename = os.path.basename(path)  # get filename from path
    basename, ext = os.path.splitext(filename)  # split filename into basename and extension
    stage_time_str, driver, car = basename.split("_")  # split basename into stage time, driver and car
    reference_stage_time_int = int(stage_time_str[:2]) * 60000 + int(stage_time_str[3:5]) * 1000 + int(
        stage_time_str[6:])  # convert stage time string to integer

    ac.setText(window_timing.label_ref, "Target:   " + str(int(reference_stage_time_int // 60000)).zfill(2) + ":" + str(
        int((reference_stage_time_int % 60000) // 1000)).zfill(2) + "." + str(
        int(reference_stage_time_int % 1000)).zfill(3))

    # add split times
    for i in range(num_splits):
        searchPos = (FinishSpline - StartSpline) * (i + 1) / (num_splits + 1) + StartSpline
        ref_timepoints = searchNearest(ret, searchPos, 0, len(ret) - 1)

        # interpolate between the two known timepoints
        try:
            split_i = ((searchPos - ref_timepoints[0][0]) / (ref_timepoints[1][0] - ref_timepoints[0][0])) * (
                        ref_timepoints[1][1] - ref_timepoints[0][1]) + ref_timepoints[0][1]
        except ZeroDivisionError:
            # fallback when only one point is found
            split_i = ref_timepoints[0][1]

        split_times[i] = split_i
    split_times[num_splits] = reference_stage_time_int

    return ret


def write_reference_file(origin_data, path, time):
    filename = str(int(time // 60000)).zfill(2) + "." + str(time // 1000 % 60).zfill(2) + "." + str(
        int(time % 1000)).zfill(3) + "_" + ac.getDriverName(0) + "_" + ac.getCarName(0).replace("_", "-") + ".refl"
    weather = get_weather()
    write = ["#Car: " + ac.getCarName(0),
             "\n#Track: " + TrackName,
             "\n#Driver: " + ac.getDriverName(0),
             "\n#Local date & time: " + datetime.now().strftime("%d-%m-%Y, %H:%M"),
             "\n#In-game time: " + weather["GAMETIME"]["HOUR"],
             "\n#Stage time: " + str(int(time // 60000)).zfill(2) + ":" + str(time // 1000 % 60).zfill(2) + "." + str(int(time % 1000)).zfill(3),
             "\n#Speed on startline: {:.2f}".format(StartSpeed) + " km/h",
             "\n#Comments: ",
             "\n#Weather: " + weather["WEATHER"]["NAME"],
             "\n#Temperature Road: " + weather["TEMPERATURE"]["ROAD"],
             "\n#Temperature Air: " + weather["TEMPERATURE"]["AMBIENT"],
             "\n#Wind: " + weather["WIND"]["SPEED_KMH_MAX"] + " km/h from " + weather["WIND"]["DIRECTION_DEG"] + " deg\n"]
    if OnServer:
        write.append("#Game mode: Online\n")
        write.append("#Speed trap value on startline: " + str(SpeedTrapValue) + " km/h\n")
    else:
        write.append("#Game mode: Offline\n")

    for data in origin_data:
        write.append(str(data[0]) + ";" + str(data[1]) + "\n")
    with open(path + "/" + filename, "w") as file:
        ac.log(AppName + ": Writing to: " + file.name)
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

    if OnServer:
        with open(log_path, "r") as file:
            for line in file:
                if "setting wind" in line.lower():
                    try:
                        wind_speed = str(int(float(line.split()[2])))
                        wind_direction = str(int(float(line.split()[5])))
                        data["WIND"] = {"SPEED_KMH_MAX": wind_speed, "DIRECTION_DEG": wind_direction}
                    except IndexError:
                        pass
                elif "ACP_WEATHER_UPDATE" in line:
                    try:
                        ambient = str(int(float(line.split()[1].split("=")[1])))
                        road = str(int(float(line.split()[2].split("=")[1])))
                        graphics = line.split()[3].split("=")[1]
                        data["WEATHER"] = {"NAME": graphics}
                        data["TEMPERATURE"] = {"AMBIENT": ambient, "ROAD": road}
                    except IndexError:
                        pass
    else:
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

    lines = (ac.ext_weatherDebugText()).strip().split('\n')
    for line in lines:
        if 'current day' in line:
            data["GAMETIME"] = {"HOUR": line[-8:-3]}

    keys = ["WEATHER", "TEMPERATURE", "WIND", "GAMETIME"]
    sub_keys = {"WEATHER": ["NAME"], "TEMPERATURE": ["AMBIENT", "ROAD"], "WIND": ["SPEED_KMH_MAX", "DIRECTION_DEG"],
                "GAMETIME": ["HOUR"]}
    for key in keys:
        if key not in data:
            data[key] = {sub_key: "unknown" for sub_key in sub_keys[key]}
        else:
            for sub_key in sub_keys[key]:
                if sub_key not in data[key]:
                    data[key][sub_key] = "unknown"
                elif not data[key][sub_key]:
                    data[key][sub_key] = "unknown"
    return data


def fix_reffile_amount_and_choose_fastest():
    global reference_data

    fastest_time = 2000000000
    fastest_file = ""
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
        # remove corresponding replay
        ac.log(AppName + ": Deleted " + slowest_file + ".refl")
        try:
            os.remove("apps/python/RallyTiming/replays/" + TrackName + "/" + slowest_file + ".acreplay")
            ac.log(AppName + ": Deleted " + slowest_file + ".acreplay")
        except FileNotFoundError:
            ac.log(AppName + ": Tried to delete " + slowest_file + ".acreplay but the file didn't exist")

        window_choose_reference.refilterList()

        # delete more if there are too many
        if num_files - 1 > MaxRefFiles:
            fix_reffile_amount_and_choose_fastest()

    if fastest_file != "":
        reference_data = read_reference_file(ReferenceFolder + "/" + fastest_file + ".refl")
        window_choose_reference.list.select(format_filename_for_list(fastest_file))


def toggle_timing_window(*args):
    window_timing.toggleVisibility()


def toggle_map(*args):
    window_progress_bar.toggleVisibility()


def toggle_reference(*args):
    window_choose_reference.toggleVisibility()


def toggle_notifications(*args):
    window_split_notification.toggleVisibility()


def create_button(text, x, y, width, height, visible=0, color=None, listener=None):
    button = ac.addButton(appWindow, text)
    ac.setPosition(button, x, y)
    ac.setSize(button, width, height)
    ac.setVisible(button, visible)
    if color:
        ac.setBackgroundColor(button, *color)
    if listener:
        ac.addOnClickedListener(button, listener)
    return button


def toggle_button_display(*args):
    global main_expanded
    main_buttons = [button_open_map, button_open_timing, button_open_reference, button_open_notifications, button_delete_reffiles, button_reset_start_stop]
    for button in main_buttons:
        ac.setVisible(button, int(not main_expanded)) 		# int() converts True to 1 and False to 0
                                                            # Use a ternary operator to set the app window size based on the main_expanded flag
    if main_expanded:
        ac.setVisible(window_choose_reference.window, 0)
        hide_reset_yn()
        hide_delete_yn()
    ac.setSize(appWindow, appWindowSize[0], appWindowSize[1] + 170 if not main_expanded else appWindowSize[1])
    main_expanded = not main_expanded                       # Flip the main_expanded flag at the end


def show_delete_yn(*args):
    ac.setVisible(button_delete_reffiles_y, 1)
    ac.setVisible(button_delete_reffiles_n, 1)


def hide_delete_yn(*args):
    ac.setVisible(button_delete_reffiles_y, 0)
    ac.setVisible(button_delete_reffiles_n, 0)


def delete_reffiles(*args):
    global reference_data
    for file in os.listdir(ReferenceFolder):
        if file.endswith(".refl"):
            os.remove(ReferenceFolder + "/" + file)
    window_choose_reference.refilterList()
    reference_data = []
    ac.setText(window_timing.label_ref, "Target:    (none)")
    ac.setBackgroundColor(button_delete_reffiles, 0,0,0)
    hide_delete_yn()


def show_reset_yn(*args):
    ac.setVisible(button_reset_start_stop_y, 1)
    ac.setVisible(button_reset_start_stop_n, 1)


def hide_reset_yn(*args):
    ac.setVisible(button_reset_start_stop_y, 0)
    ac.setVisible(button_reset_start_stop_n, 0)


def reset_start_stop(*args):
    global Status, FinishSpline
    if ac.getCarState(0, acsys.CS.LapTime) == 0:
        Status = 0
        ac.setBackgroundColor(button_reset_start_stop, 0, 0, 0)
        hide_reset_yn()
        StartFinishSplines[TrackName] = {"StartSpline": 0, "FinishSpline": 1.0001, "TrueLength": 0}
        FinishSpline = 1.0001
        with open(StartFinishJson, "w") as f:
            json.dump(StartFinishSplines, f, indent=4)


def reset_variables():
    global data_collected, Status, LapCountTracker, StartSpeed, SpeedTrapValue, StartChecked, StatusList
    data_collected = []
    ac.setFontColor(line1, *white)
    StartSpeed = 0
    SpeedTrapValue = 0
    StartChecked = False
    window_split_notification.last_current_sector = 1
    window_split_notification.last_time_shown = 200000000000


class SaveReplayWorker:
    def __init__(self, ac_path, replay_path, active=True):
        self.active = active
        self.ac_path = ac_path
        self.replay_path = replay_path
        self.general_cfg = configparser.ConfigParser(inline_comment_prefixes=";")
        self.general_cfg.optionxform = str
        self.general_cfg.read(ac_path + "cfg/extension/general.ini")
        self.save_replay_on = 200000000000
        self.move_file_on = 200000000000
        self.old_clip_duration = self.general_cfg.getint("REPLAY", "CLIP_DURATION", fallback=30)
        self.file_name = ""
        self.unpress_keys = False

    def update(self):
        if self.active:
            if self.unpress_keys:
                ac.log(AppName + ": Replay file saving finished")
                ctypes.windll.user32.keybd_event(0x10, 0, 0x0002, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 0x0002, 0)
                ctypes.windll.user32.keybd_event(0x53, 0, 0x0002, 0)
                self.unpress_keys = False

            if self.save_replay_on - time.time() < 0:
                ac.log(AppName + ": Replay file saving in progress")
                ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x53, 0, 0, 0)
                self.unpress_keys = True
                self.save_replay_on = 200000000000

            if self.move_file_on - time.time() < 0:
                # check if clip present and no older than 10 seconds
                try:
                    replayclip_file = (self.ac_path + "replay/clips/" + os.listdir(self.ac_path + "replay/clips")[-1])
                    file_time = os.path.getmtime(replayclip_file)
                    if time.time() - file_time < 10:
                        # move file to replay save div and set name
                        os.makedirs(self.replay_path, exist_ok=True)
                        shutil.move(replayclip_file , self.replay_path + self.file_name)
                        with open(self.ac_path + "cfg/extension/general.ini", "w") as f:
                            self.general_cfg.set("REPLAY", "CLIP_DURATION", str(self.old_clip_duration))
                            self.general_cfg.write(f, space_around_delimiters=False)
                    else:
                        ac.log(AppName + ": Replay clip not found!")
                except IndexError:
                        ac.log(AppName + ": Replay clip not found!")
                self.move_file_on = 200000000000

    def save_replay(self, stage_time):
        if self.active:
            ac.log(AppName + ": Replay saving started")
            self.file_name = str(int(stage_time // 60000)).zfill(2) + "." + str(stage_time // 1000 % 60).zfill(2) + "." + str(int(stage_time % 1000)).zfill(3) + "_" + ac.getDriverName(0) + "_" + ac.getCarName(0).replace("_", "-") + ".acreplay"
            # put stage time from millis to int seconds
            stage_time = round(stage_time / 1000)
            with open(self.ac_path + "cfg/extension/general.ini", "w") as f:
                try:
                    self.general_cfg.set("REPLAY", "CLIP_DURATION", str(stage_time + ReplayIntro + ReplayOutro))
                except configparser.NoSectionError:
                    self.general_cfg.add_section("REPLAY")
                    self.general_cfg.set("REPLAY", "CLIP_DURATION", str(stage_time + ReplayIntro + ReplayOutro))
                self.general_cfg.write(f, space_around_delimiters=False)
            self.save_replay_on = time.time() + ReplayOutro
            self.move_file_on = time.time() + ReplayOutro + 1
            
            replay_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replays')
            with open("apps/python/RallyTiming/config/config.ini","w") as configfile:
                config.set("REPLAY", "replaylocation", str(replay_folder))
                config.write(configfile, space_around_delimiters=False)
