AC Rally timing app (schlaubi77 & wimdes)
Version 1.33 (01/06/2023)

#####################################################################################################################################

The app has 2 main functions: start position verification and delta timing.
There's 3 windows/sub-apps: Main, Delta timing, Reference file selector.

Start position: The app wil help in finding proper starting position, and alert if a lap will be invalidated by AC Server Manager when a speed trap is set on the startline. Speed traps were introduced in ACSM version v2.3.4.

Delta timing: any registered run can be selected as a reference, also runs with other cars, or runs from other players.
Other players: copy reference files from/to assettocorsa\apps\python\RallyTiming\referenceLaps\(trackname) folder

#####################################################################################################################################

Start position verification in ACSM:

For rallying (or hillclimbs) this feature works in combination with "Time Attack", invalid laps are filtered out after each practice session ends/loops. In live results there's no visible difference between good an bad laps, only in Time Attack results! The filtering is done by a results.lua script that has to be enabled on the server (included in ACSM download - beware there it's in m/s)

The start speed limit is by default set to 15km/h in the results processing script, for most 4WD cars this corresponds to a starting position of max 0.5m before the startline. By default the app will indicate starting position as OK when stopped at < 0.5m, but the detected speed on the line is what counts! This distance can be adjusted in the client settings.

The server sends the speed trap measurement in a chat message, this is picked up by the client to alert if a lap will be invalidated.
Speed Traps - Send Chat Messages must be "On" in the server, otherwise there will be no messages sent.

#####################################################################################################################################

App features:

- Start & finish AI line (spline) positions are detected by driving across.  
- Positions are written into the StartFinishSplines.json file, also the calculated distance (in meters) between start & stop lines.
- Startline (spline) position can be entered in ACSM track config to position a speed trap on the startline (from ACSM v2.3.4)
- The app will indicate distances:
  * to start line: as "estimated" when car is not on the AI line yet (showing distance as the crow flies)
  * to finish line (optionally): as "estimated" when finish AI line position is unknown (showing distance until the end of the AI line)
- Status will turn green when the car is stopped within 0.5m in front of the start line (which is often not clearly visible)
- Show the speed on the startline when offline, speed trap value as reported by the server when online (this can deviate 1-2 km/h)
- Alert when startline speed is above set threshold - changing this value in the app does not influence the value on the server!
  The speed threshold on the server is set in the results.lua file (in m/s)
- Most settings can be configuerd in Python app settings in Content manager
  * Optionally show remaining fuel level
  * Interface language can be set to English, Spanish, French or German

- Delta timing: 
  * Reference file can be chosen (from same car, other cars, or other driver/car combos)
  * Works during replays (last lap only, reference file has to be re-loaded after finish)
  * Weather conditions, startline speed are registered in the reference files
  * By default all runs are saved. In settings the number of times kept per driver/car combo can be limited
  * Number of reference files kept per player/car combo can be limited (default = unlimited)
  * Comments field is available in reference file (add manually directly in file)

Prerequisites:
- Point-to-point tracks only
- The track must have an AI line
- CSP must be installated and activated

#####################################################################################################################################

Settings (to be configured in CM -> Settings -> Apps)

StartSpeedLimit = 15            # in km/h - default value in results script is set to 15kmh
MaxStartLineDistance = 0.5      # in meters, within what distance start status will turn green/ready to start
ShowStartSpeed = true           # show speed on startline crossing (as measured by ACSM in speed trap when online)
ShowRemainingDistance= true     # show remaining distance to finish (in meters)
ShowFuel = true                 # show fuel remaining
DebugMode = false               # show some additional values (overwriting fuel status)
Language = "English"            # "English", "Spanish", "French", "German"
MaximumRefFiles = 0             # number of times kept per driver/car combo (the fastest times. 0 = unlimited)
