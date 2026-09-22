# Contributing to Bindlume

This is an early testing release for Omarchy. Bug reports with reproducible steps are especially useful. Search existing issues first, then use the bug-report template. Include the app revision and your environment; remove private data from logs.

For code changes, branch from main and open a pull request. Keep fixes focused, preserve saved shortcut identities, and add a regression test for bugs. Run `make test`; it uses a private GTK Broadway display and offscreen QML tests. Visually inspect changed UI using disposable settings. Do not inject automated input into a user's active desktop.

New application text belongs in `translations.json`. Keep user-authored titles and stable data IDs untranslated. Test installation and upgrades with a temporary `--home` and `--no-reload`, never with a test that rewrites your actual desktop configuration.
