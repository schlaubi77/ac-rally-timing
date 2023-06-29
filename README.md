# AC Rally timing app (by schlaubi77 & wimdes)

## Version 1.54 (29/06/2023)

***

The app has 3 main functions:
- start position verification
- delta timing 
- stage progress bar indicator
- split timing 
- car reset key

There's 5 windows/sub-apps: Main, Delta timing, Progress Bar, Split Notifications Reference file selector (opened separately by extending main window, or in app menu bar)

**Start position:** The app wil help in finding proper starting position, and alert if a lap will be invalidated by AC Server Manager when a speed trap is set on the startline. Speed traps were introduced in ACSM version v2.3.4.

**Delta timing:** any registered run can be selected as a reference, also runs with other cars, or runs from other players.
Other players: copy reference files from/to assettocorsa\apps\python\RallyTiming\referenceLaps\(trackname) folder

***

## Start position verification in ACSM:

For rallying (or hillclimbs) this feature works in combination with "Time Attack", invalid laps are filtered out after each practice session ends/loops. In live results there's no visible difference between good an bad laps, only in Time Attack results! The filtering is done by a results.lua script that has to be enabled on the server (included in ACSM download - beware there it's in m/s)

The start speed limit is by default set to 15km/h in the results processing script, for most 4WD cars this corresponds to a starting position of max 0.5m before the startline. By default the app will indicate starting position as OK when stopped at < 0.5m, but the detected speed on the line is what counts! This distance can be adjusted in the client settings.

The server sends the speed trap measurement in a chat message, this is picked up by the client to alert if a lap will be invalidated.
Speed Traps - Send Chat Messages must be "On" in the server, otherwise there will be no messages sent.

***

## App features:

- Start & Finish AI line (spline) positions are detected by driving across.  
- Positions are written into the StartFinishSplines.json file, also the calculated distance (in meters) between start & finish lines.
- Startline (spline) position can be entered in ACSM track config to position a speed trap on the startline (from ACSM v2.3.4)
- The app will indicate distances:
  - **To the start line:** as "estimated" when car is not on the AI line yet (showing distance as the crow flies)
  - **To finish line (optionally):** as "estimated" when finish AI line position is unknown (showing distance until the end of the AI line)
- Status will turn green when the car is stopped within 0.5m in front of the start line (which is often not clearly visible)
- Show the speed on the startline when offline, speed trap value as reported by the server when online (this can deviate 1-2 km/h)
- Alert when startline speed is above set threshold - changing this value in the app does not influence the value on the server!
  The speed threshold on the server is set in the results.lua file (in m/s)
- Most settings can be configured in Python app settings in Content manager
  * Optionally show remaining fuel level
  * Interface language can be set to English, Spanish, French or German
- Reset car to track button - configurable in CM app settings (keyboard or wheel)

- Delta timing: 
  * Reference file can be chosen (from same car, other cars, or other driver/car combos)
  * Works during replays (last lap only, reference file has to be re-loaded after finishing)
  * Weather conditions, startline speed are registered in the reference files
  * By default all runs are saved. In settings the number of times kept per driver/car combo can be limited
  * Number of reference files kept per player/car combo can be limited (default = unlimited)
  * Comments field is available in reference file (add manually directly in file)

***

### Prerequisites:
- Point-to-point tracks only
- The track must have an AI line
- CSP must be installated and activated

***

## Settings (to be configured in CM -> Settings -> Apps)

- StartSpeedLimit = 15 &emsp;&emsp;&emsp;&emsp;&emsp; in km/h - default value in results script is set to 15kmh
- MaxStartLineDistance = 0.5 &emsp;&emsp;&ensp;in meters, within what distance start status will turn green/ready to start
- ShowStartSpeed = true &emsp;&emsp;&emsp;&emsp; show speed on startline crossing (as measured by ACSM in speed trap when online)
- ShowRemainingDistance= true&emsp; show remaining distance to finish (in meters)
- ShowFuel = true &emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp; show fuel remaining
- DebugMode = false &emsp;&emsp;&emsp;&emsp;&emsp;&ensp; show some additional values (overwriting fuel status)
- Language = "English"&emsp;&emsp;&emsp;&emsp;&emsp; "English", "Spanish", "French", "German"
- MaximumRefFiles = 10 &emsp;&emsp;&emsp;&emsp;&emsp; number of times kept per driver/car combo (the fastest times. 0 = unlimited)
- DeltaDecimals=2 &emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp; Decimal Digits for the Delta (tenths/hundredths/thousandths of a second)
- ResetCar=82 &emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&nbsp; reset Car (keybord button)
