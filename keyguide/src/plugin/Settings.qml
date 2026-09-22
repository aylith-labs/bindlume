// All settings use the shortcut app's shared GTK components.
import QtQuick
import Quickshell.Io

Item {
    id: root
    property var shell: null
    property var manifest: null
    property var service: null
    property bool opened: false
    Process {
        id: launch
        command: ["bindlume", "--guide"]
    }
    function open(payloadJson) {
        let payload = ({})
        try { payload = JSON.parse(payloadJson || "{}") || ({}) } catch (error) {}
        if (payload.mode !== undefined && payload.mode !== "settings") return false
        if (!launch.running) launch.running = true
        Qt.callLater(function() {
            if (root.shell && typeof root.shell.hide === "function")
                root.shell.hide((root.manifest && root.manifest.id) || "mrai.keyguide")
        })
        return true
    }
    function close() { opened = false }
}
