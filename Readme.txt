AC Rally timing app

The initial aim of this app is to help in finding proper starting position,
and alerting if a lap will be invalidated by AC Server Manager when a speed trap is set on the startline.
Speed traps are a new feature in ACSM version v2.3.4 (in beta as of 4/4/2023)

For rallying (or hillclimbs) the feature works in combination with "Time Attack", invalid laps are filtered out after each practice session ends/loops.
So in live results there's no visible difference between good an bad laps, only in Time Attack results!

Default start speed limit is set to 15km/h on ACSM, for most 4WD cars this corresponds to a starting position of max 0.5m before the startline.
So by default the app wil indicate starting position as OK when stopped at < 0.5m, but the detected speed on the line is what counts!

The server sends the speed trap measurement in a chat message, this is picked up by the client to indicate when lap will be invalidated.

App features:

- Start & finish AI line (spline) positions are detected by driving across.  
- Positions are written into the StartFinishSplines.json file, also the calculated distance (in meters) between start & stop lines.
- Startline position can then be entered in ACSM track config to position a speed trap on the startline (from ACSM v2.3.4)
- The app will indicate distances:
  * to start line: as "estimated" when car is not on the AI line yet (showing distance as the crow flies)
  * to finish line: as "estimated" when finish AI line position is unknown (showing distance until the end of the AI line)
- Status will turn green when the car is stopped within 0.5m in front of the start line (which is often not clearly visible)
- Shows the speed on the startline when offline, speed trap value as reported by the server when online (this can deviate 1-2 km/h)
- Warning when startline speed is above set threshold - changing this value in the app does not influence the value on the server!
- Optionally show remaining fuel level

Prerequisites:
- Point-to-point tracks only
- The track must have an AI line
- CSP must be installated and active

Being new to Python I basically learned while creating this app so there's much room for improvement, but it seems to be working for now.


Settings (direcly in Content Managers App settings)

StartSpeedLimit = 15            # in km/h - default value in ACSM is set to 15kmh
MaxStartLineDistance = 0.5      # in meters, within what distance start status will turn green/ready to start
ShowStartSpeed = 1              # show speed on startline crossing (as measured by ACSM in speed trap when online)
ShowRemainingDistance= 1        # show remaining distance to finish (in meters)
ShowFuel = 1                    # show fuel remaining
DebugMode = 0                   # show some additional values (overwriting fuel status)
