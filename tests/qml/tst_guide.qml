import QtQuick
import QtTest
import "../../keyguide/src/plugin/components" as Guide

TestCase {
  name: "GuidePresentation"
  visible: true
  when: windowShown
  width: 720
  height: 480
  Guide.RevealDelay { id: delay }
  Guide.HudPreview {
    id: preview
    width: 700
    height: 420
    bindings: [
      {id:"action", key:"W", description:"Close window", modifiers:["SUPER"], displayKind:"action"},
      {id:"app", key:"B", description:"Browser", modifiers:["SUPER"], displayKind:"desktopApp"}
    ]
  }
  Guide.BindingRow {
    id: webRow
    width: 650
    bindingData: ({id:"web-test", key:"B", modifiers:["SUPER"], description:"Example web app", displayKind:"webapp", icon: String(Qt.resolvedUrl("test-icon.svg")).replace("file://", "")})
  }
  function test_web_favicon_uses_local_file_and_decodes() {
    const icon = findChild(webRow, "bindingPresentationIcon")
    verify(String(icon.source).startsWith("file://"))
    tryCompare(icon, "status", Image.Ready)
    verify(!findChild(webRow, "bindingPresentationIconFallback").visible)
  }
  function test_delay_cancels_short_press() {
    delay.delayMs = 200
    delay.eligible = true
    compare(delay.ready, false)
    wait(60)
    delay.eligible = false
    wait(230)
    compare(delay.ready, false)
    delay.eligible = true
    compare(delay.ready, false)
    tryCompare(delay, "ready", true, 500)
    delay.eligible = false
    compare(delay.ready, false)
    delay.delayMs = 0
    delay.eligible = true
    compare(delay.ready, true)
    delay.eligible = false
  }
  function test_independent_density_badges_and_hidden_items() {
    preview.bindings = [
      {id:"action", key:"W", description:"Close window", modifiers:["SUPER"], displayKind:"action", appHidden:true, bookmarked:true},
      {id:"app", key:"B", description:"Browser", modifiers:["SUPER"], displayKind:"desktopApp"}
    ]
    preview.settings = {enabled:true, compactView:true, badgeMode:"badges", showHiddenItems:false}
    wait(30)
    compare(preview.renderedRowCount, 1)
    verify(findChild(preview, "hudPreviewTypeBadge-app").visible)
    preview.settings = {enabled:true, compactView:false, badgeMode:"icons", showHiddenItems:true, showSavedIndicators:true}
    wait(30)
    compare(preview.renderedRowCount, 2)
    verify(findChild(preview, "hudPreviewTypeIcon-app").visible)
    verify(findChild(preview, "hudPreviewDescription-action").text.indexOf("★") !== -1)
    preview.settings = {enabled:true, compactView:true, badgeMode:"none", showHiddenItems:true}
    wait(30)
    verify(!findChild(preview, "hudPreviewTypeIcon-app").visible)
    verify(!findChild(preview, "hudPreviewTypeBadge-app").visible)
    preview.bindings = [
      {id:"action", key:"W", description:"Close window", modifiers:["SUPER"], displayKind:"action"},
      {id:"app", key:"B", description:"Browser", modifiers:["SUPER"], displayKind:"desktopApp"}
    ]
  }
  function test_preview_layout_and_action_toggle() {
    preview.settings = {enabled:true, compactIcons:false, showActionIndicators:true}
    wait(80)
    var badge = findChild(preview, "hudPreviewTypeBadge-action")
    var icon = findChild(preview, "hudPreviewTypeIcon-action")
    var legend = findChild(preview, "hudPreviewLegend")
    verify(badge !== null)
    verify(badge.visible)
    verify(!icon.visible)
    verify(!legend.visible)
    preview.settings = {enabled:true, compactIcons:true, showActionIndicators:true}
    wait(20)
    verify(!badge.visible)
    verify(icon.visible)
    verify(legend.visible)
    preview.settings = {enabled:true, compactIcons:true, showActionIndicators:false}
    wait(20)
    verify(!icon.visible)
    verify(findChild(preview, "hudPreviewTypeIcon-app").visible)
    preview.settings = {enabled:true, compactIcons:false, showActionIndicators:false}
    wait(20)
    verify(!badge.visible)
    verify(findChild(preview, "hudPreviewTypeBadge-app").visible)
  }
}
