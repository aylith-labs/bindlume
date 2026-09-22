import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
    id: root
    property var preferences: ({})
    property var looks: ({rounded: {radius:10, font:"sans-serif"}, square: {radius:0, font:"monospace"}})
    readonly property string requestedLook: preferences.resolved_look || (preferences.features && preferences.features.appearance ? preferences.look : "square") || "square"
    readonly property string resolvedLook: requestedLook === "omarchy" || requestedLook === "system" ? "square" : requestedLook
    readonly property var tokens: looks[resolvedLook] || looks.square
    readonly property bool square: tokens.radius === 0
    readonly property int radius: tokens.radius
    readonly property int borderWidth: tokens.border || 1
    readonly property int shadowOffset: tokens.shadow || 0
    readonly property string fontFamily: resolvedLook === "square" ? Style.font.menuFamily : tokens.font
    readonly property string theme: preferences.preferences && preferences.preferences.theme || "system"
    readonly property color background: theme === "light" ? "#eff1f5" : theme === "dark" ? "#1e1e2e" : Color.menu.background
    readonly property color foreground: theme === "light" ? "#303446" : theme === "dark" ? "#cdd6f4" : Color.menu.text
    FileView {
        path: Qt.resolvedUrl("../../../../looks.json")
        printErrors: false
        onLoaded: { try { root.looks = JSON.parse(text()) } catch (error) {} }
    }
    FileView {
        path: (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/bindlume/ui-state.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { root.preferences = JSON.parse(text()) }
            catch (error) { root.preferences = ({}) }
        }
    }
}
