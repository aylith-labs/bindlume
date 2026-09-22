---
name: Bindlume
tagline: Illuminate the shortcuts you need, when you need them
description: Find desktop and app shortcuts, see their keys on a keyboard, and use an optional agent companion to search and configure the app. Public alpha testing starts with Omarchy on Linux.
category: productivity
status: beta
features:
  - Live Omarchy shortcuts alongside app and custom shortcut sets
  - Search by action or key, keyboard illumination, bookmarks and hidden items
  - System colors with Square, Rounded and Neo appearances
  - Optional agent companion with live app control
  - Optional keyboard guide, mouse gestures and controller controls
targetUser: Omarchy users who want a searchable guide to their desktop and application shortcuts.
gradientFrom: '#C47A36'
gradientTo: '#9E5727'
onboarding:
  access: public-source
  url: https://bindlume.aylith.com
  releasesUrl: https://github.com/aylith-labs/bindlume/releases
  prerequisites:
    - A current Lua-based Omarchy installation on Linux
    - Python, GTK4, PyGObject and the system packages listed in the README
  limitations:
    - Early public alpha; expect bugs and incomplete translations
    - Windows, macOS and other Linux desktops are not supported testing targets yet
    - The optional companion needs your own authenticated harness or API connection
---

## Try the public testing preview

[Visit the Bindlume homepage →](https://bindlume.aylith.com)

Explore the keyboard demo and light/dark app previews, then follow the [installation instructions](https://github.com/aylith-labs/bindlume#install-on-omarchy). The [testing release](https://github.com/aylith-labs/bindlume/releases) contains the full source and known limitations.

## Find a shortcut, see its keys

Search for an action such as “theme,” inspect the highlighted key combination, and bookmark it for next time. Bindlume reads live Omarchy shortcuts and adds reference sets for installed apps and your own custom sets.

## An optional companion that can change the app

Use an installed agent or configure a direct model connection. The companion can find shortcuts, switch appearance, and update supported settings through Bindlume’s running-app API. Persistent memory is optional.

## Help improve it

This is working software offered for early testing, not a finished stable product. Try keyboard navigation, changing sources, resizing with chat open, and reopening the app. [Report reproducible bugs](https://github.com/aylith-labs/bindlume/issues/new/choose), including your app revision and environment.
