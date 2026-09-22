import QtQuick

Item {
  id: root
  property bool eligible: false
  property int delayMs: 0
  property bool elapsed: false
  readonly property bool ready: eligible && (delayMs === 0 || elapsed)
  onEligibleChanged: elapsed = false
  Timer {
    interval: Math.max(1, root.delayMs)
    running: root.eligible && root.delayMs > 0 && !root.elapsed
    repeat: false
    onTriggered: root.elapsed = true
  }
}
