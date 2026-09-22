-- Read only the app-owned scalar preference; never execute config content.
local config_home = os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config")
local state_file = io.open(config_home .. "/bindlume/ui-state.json", "r")
local mode = "off"
if state_file then
  local contents = state_file:read("*a")
  state_file:close()
  mode = contents:match('"window_animations"%s*:%s*"([%a]+)"') or "off"
end
-- Following the system installs no animation override.
if mode == "on" or mode == "off" then
  o.window({ class = "^com[.]aylith[.]Bindlume$" }, { no_anim = mode == "off" })
end
-- Main shortcut browser: float and center like Omarchy utility windows.
o.window({ class = "^com[.]aylith[.]Bindlume$", title = "^Bindlume$" }, {
  tag = "-default-opacity",
  opacity = "1 1",
  float = true,
  center = true,
  -- GTK chooses the default size based on enabled features.
})

-- Layer surfaces stay on the active monitor across workspace changes.
if hl and hl.layer_rule then
  if mode == "off" then
    hl.layer_rule({ match = { namespace = "^bindlume-(overlay|backdrop)$" }, no_anim = true, animation = "none" })
  end
end
