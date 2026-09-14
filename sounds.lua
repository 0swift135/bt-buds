local M = {}
local pipewire = false

function M.init()
    pipewire = true
end

function M.play(name)
    if not pipewire then return end
    local path = "/usr/share/sounds/freedesktop/stereo/" .. name .. ".oga"
    os.execute("ffplay -nodisp -autoexit -v 0 " .. string.format("%q", path) .. " >/dev/null 2>&1 &")
end

function M.mode_on() M.play("complete") end
function M.mode_off() M.play("bell") end
function M.connect() M.play("message-new-instant") end
function M.disconnect() M.play("bell") end

return M
