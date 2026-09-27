# Records the README demo GIF: `pixi run demo` from the repository root.
# Every command runs for real against the small project in docs/demo/project,
# so the GIF shows the current output of the working tree.
#
# VHS drives a headless Chromium (downloaded on first use). When running as
# root, e.g. in a container, Chromium needs `VHS_NO_SANDBOX=true`.

Output docs/demo/demo.gif

Require isar

Set Shell "bash"
Set FontSize 15
Set Width 1280
Set Height 560
Set Padding 20
Set Framerate 12
Set TypingSpeed 20ms
Set Theme "Catppuccin Mocha"
Set CursorBlink false

Hide
Type "cd docs/demo/project && export PS1='$ ' && clear"
Enter
Show

Type "isar stats"
Sleep 200ms
Enter
Sleep 2.5s

Hide
Type "clear"
Enter
Show

Type "isar check"
Sleep 200ms
Enter
Sleep 2.5s

Hide
Type "clear"
Enter
Show

Type "isar fmt --diff Lists.thy"
Sleep 200ms
Enter
Sleep 3s

Hide
Type "clear"
Enter
Show

Type "isar project graph --theories"
Sleep 200ms
Enter
Sleep 2s
