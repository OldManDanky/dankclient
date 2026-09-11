# Your files, updates and trouble

## Where things are

Your map, characters, triggers, sounds and logs are in `%LOCALAPPDATA%\dankclient`, or `%LOCALAPPDATA%\3k` if you had the client before it had this name. [Options → About](options:about) shows the paths. Copy that folder to back up.

The program is in `%LOCALAPPDATA%\Programs\Dank Mud Client`. Updating or reinstalling it never touches your things.

## Updates

- **The client**: [Options → About](options:about) says when a new version is out. Run the new installer; you do not need to close the client first.
- **The map and routes**: [Options → Updates](options:updates) takes what has changed in 3kdb. It only adds.
- **Fresh copy**, on the same screen, is the other way round: it drops your copy of what you tick and takes 3kdb's as it stands. Use it when the map is wrong rather than out of date. It costs room names you set, visit counts, exits you learned by walking, and 3kdb's own routes as you have edited them. Your own routes and your whole session log are kept. It takes two presses, and the button says what it will do before the second one.

## When something is wrong

- `client.log`, in your data folder, is where the client writes down anything that went wrong.
- `installer.log`, beside it, says what the installer did about a running client.
- Bug reports: <https://github.com/OldManDanky/dankclient/issues>, with `client.log` if you can.
