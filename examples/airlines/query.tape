Output examples/airlines/query.gif

Set TypingSpeed 75ms
Set FontSize 22
Set Width 1600
Set Height 900

Type "cd examples/airlines/"

Enter

Sleep 500ms

Type "cat conf/base/catalog.yml"

Enter

Sleep 5

Type "kedro ipython"

Enter

Sleep 5

Type 'flights = catalog.load("flights")'

Enter

Sleep 1

Type "from boring_semantic_layer.semantic_api.query import build_query"

Enter

Sleep 1

Type 'build_query('

Enter

Sleep 500ms

Type '    semantic_table=flights,'

Enter

Sleep 500ms

Type 'dimensions=["destination"],'

Enter

Sleep 500ms

Type 'measures=["flight_count", "avg_distance"],'

Enter

Sleep 500ms

Type 'order_by=[("flight_count", "desc")],'

Enter

Sleep 500ms

Type 'limit=10,'

Enter

Sleep 500ms

Backspace 4

Type ').execute()'

Enter

Sleep 10
