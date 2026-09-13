-- Modifier state and leased physical press/release events. No key history is saved.
-- Loaded by the user's bindings.lua; events use Hyprland's local IPC socket.
local modifiers = { [50] = 1, [62] = 1, [37] = 4, [105] = 4,
                    [64] = 8, [108] = 8, [133] = 64, [134] = 64 }
local pressed = {}
_omarchy_shortcuts_mods = 0
_omarchy_shortcuts_lease = 0
hl.on("input.keyboard.key", function(code, timestamp, state)
  if state == 2 then return end
  if os.time() < (_omarchy_shortcuts_lease or 0) then
    hl.dispatch(hl.dsp.event("omarchy-shortcuts-key," .. tostring(code) .. "," .. tostring(state)))
  end
  if not modifiers[code] then return end
  pressed[code] = state == 1 or nil
  local seen, mask = {}, 0
  for key in pairs(pressed) do
    local modifier = modifiers[key]
    if not seen[modifier] then mask = mask + modifier; seen[modifier] = true end
  end
  _omarchy_shortcuts_mods = mask
  hl.dispatch(hl.dsp.event("omarchy-shortcuts-mods," .. tostring(mask)))
end)
