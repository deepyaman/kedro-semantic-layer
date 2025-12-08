Output examples/airlines/query.webm

Set TypingSpeed 75ms
Set FontSize 22
Set Width 1600
Set Height 900

Require kedro

Hide
Type "export KEDRO_DISABLE_TELEMETRY=1"
Enter
Ctrl+L
Show

Type "cd examples/airlines/"
Enter
Sleep 1

Type "cat conf/base/catalog.yml"
Enter
Sleep 5

Type "clear"
Enter
Sleep 1

Type "kedro ipython"
Enter
Wait /In \[1\]:/
Sleep 1

Type 'flights = catalog.load("flights")'
Enter
Sleep 1

Type "from ibis import _"
Enter
Sleep 1

Type 'result = ('
Enter
Sleep 500ms
Type '    flights.group_by("destination")'
Enter
Sleep 500ms
Type '.aggregate("flight_count", "avg_distance")'
Enter
Sleep 500ms
Type '.order_by(_.flight_count.desc())'
Enter
Sleep 500ms
Type '.limit(10)'
Enter
Sleep 500ms
Backspace 4
Type ')'
Enter
Sleep 1

Type "result.execute()"
Enter
Sleep 10
