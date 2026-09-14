-- bt-buds service: headset connection + codec, tiny state.

local HOME = os.getenv("HOME") or ""
local PLUGIN_DIR = HOME .. "/.local/share/noctalia/plugins/bt-buds"
local STATE_DIR = HOME .. "/.local/state/bt-buds"
local SVC_STATE = "btbuds.status"
local CODECS = { "sbc", "sbc_xq", "aac" }
local PROFILES = {
    sbc = "a2dp-sink-sbc",
    sbc_xq = "a2dp-sink-sbc_xq",
    aac = "a2dp-sink",
}
local EQ_PRESETS = { "normal", "more_bass", "boost_vocals", "more_highs" }
local eq_index = 1

local function play_sound(name)
    os.execute("ffplay -nodisp -autoexit -v 0 /usr/share/sounds/freedesktop/stereo/" .. name .. ".oga >/dev/null 2>&1 &")
end

local snap = { connected = false, codec = "", mac = "", mode = "off", bat = "", bat_l = -1, bat_r = -1, bat_c = -1, lang = "auto" }

local function publish()
    noctalia.state.set(SVC_STATE, {
        connected = snap.connected,
        codec = snap.codec,
        mac = snap.mac,
        mode = snap.mode,
        bat = snap.bat,
        bat_l = snap.bat_l,
        bat_r = snap.bat_r,
        bat_c = snap.bat_c,
        lang = snap.lang,
        eq_preset = snap.eq_preset,
    })
end

local function read_lang()
    local okf, content = pcall(noctalia.readFile, STATE_DIR .. "/lang")
    if okf and type(content) == "string" then
        local v = content:match("(%w+)")
        if v == "ru" or v == "en" or v == "auto" then return v end
    end
    return "auto"
end

local function next_eq()
    eq_index = (eq_index % #EQ_PRESETS) + 1
    local preset = EQ_PRESETS[eq_index]
    snap.eq_preset = preset
    publish()
    return preset
end

local function refresh_battery()
    noctalia.runAsync("python3 " .. PLUGIN_DIR .. "/battery.py 2>/dev/null",
        function(result)
            local out = (result and result.stdout) or ""
            local l, r, c = out:match("(%d+)%s+(%d+)%s+(-?%d+)")
            if result and result.exitCode == 0 and l then
                snap.bat_l = tonumber(l) or -1
                snap.bat_r = tonumber(r) or -1
                snap.bat_c = tonumber(c) or -1
                local cs = snap.bat_c >= 0 and ("Case " .. c .. "%") or "Case Closed"
                snap.bat = "L " .. l .. "% · R " .. r .. "% · " .. cs
                publish()
            end
            -- on failure keep last known values instead of blanking
        end
    )
end

local function refresh()
    noctalia.runAsync(
        "card=$(pactl list cards short 2>/dev/null | grep bluez_card | head -n1 | cut -f2);"
        .. " if [ -z \"$card\" ]; then echo connected=0;"
        .. " else codec=$(pactl list sinks 2>/dev/null | grep -m1 'api.bluez5.codec' | sed 's/.*= //;s/\"//g');"
        .. " echo connected=1; echo \"card=$card\"; echo \"codec=$codec\"; fi",
        function(result)
            local out = (result and result.stdout) or ""
            local connected, card, codec = false, "", ""
            for line in out:gmatch("[^\r\n]+") do
                local k, v = line:match("^(%w+)=(.*)$")
                if k == "connected" and v == "1" then connected = true end
                if k == "card" then card = v end
                if k == "codec" then codec = v end
            end
            snap.connected = connected
            snap.codec = codec
            if card ~= "" then
                local mac = card:match("^bluez_card%.(.*)$") or ""
                snap.mac = mac:gsub("_", ":")
            end
            local okf, content = pcall(noctalia.readFile, STATE_DIR .. "/mode.json")
            if okf and type(content) == "string" then
                local v = content:match('"mode":%s*"(%w+)"')
                if v == "anc" or v == "transparency" or v == "off" then snap.mode = v end
            end
            snap.lang = read_lang()
            publish()
            refresh_battery()
        end
    )
end

local function next_codec(cur)
    for i, c in ipairs(CODECS) do
        if c == cur then
            return CODECS[(i % #CODECS) + 1]
        end
    end
    return CODECS[1]
end

function onIpc(event, _payload)
    if event == "refresh" then
        refresh()
    elseif event == "hold" then
        refresh()
    elseif event == "toggle" then
        if snap.mac == "" then
            refresh()
            return
        end
        local action = snap.connected and "disconnect" or "connect"
        noctalia.runAsync("bluetoothctl " .. action .. " " .. snap.mac, function()
            refresh()
        end)
    elseif event == "cycle_codec" then
        if not snap.connected or snap.mac == "" then return end
        local target = next_codec(snap.codec)
        local card = "bluez_card." .. snap.mac:gsub(":", "_")
        noctalia.runAsync("pactl set-card-profile " .. card .. " " .. PROFILES[target], function()
            refresh()
        end)
    elseif event == "cycle_eq" then
        if not snap.connected then return end
        local preset = next_eq()
    elseif event == "set_mode" then
        if not snap.connected then return end
        local want = (_payload == "anc" or _payload == "transparency") and _payload or "off"
        noctalia.runAsync("python3 " .. PLUGIN_DIR .. "/mode.py " .. want, function(result)
            local out = (result and result.stdout) or ""
            local v = out:match("(%w+)")
            if result and result.exitCode == 0 and (v == "anc" or v == "transparency" or v == "off") then
                snap.mode = v
                publish()
            end
        end)
elseif event == "cycle_mode" then
        if not snap.connected then return end
        local order = { off = "anc", anc = "transparency", transparency = "off" }
        local want = order[snap.mode] or "anc"
        noctalia.runAsync("python3 " .. PLUGIN_DIR .. "/mode.py " .. want, function(result)
            local out = (result and result.stdout) or ""
            local v = out:match("(%w+)")
            if result and result.exitCode == 0 and (v == "anc" or v == "transparency" or v == "off") then
                snap.mode = v
                publish()
                play_sound("complete")
            end
        end)
    elseif event == "cycle_lang" then
        local cur = read_lang()
        local nxt = (cur == "auto") and "ru" or ((cur == "ru") and "en" or "auto")
        pcall(noctalia.writeFile, STATE_DIR .. "/lang", nxt)
        snap.lang = nxt
        publish()
        play_sound("message-new-instant")
        sound.mode_off()
    elseif event == "set_codec" then
        if not snap.connected or snap.mac == "" then return end
        local want = (_payload == "sbc_xq" or _payload == "aac" or _payload == "sbc") and _payload or "sbc"
        local card = "bluez_card." .. snap.mac:gsub(":", "_")
        noctalia.runAsync("pactl set-card-profile " .. card .. " " .. PROFILES[want], function()
            refresh()
        end)
    end
end

function onOpen()
    publish()
    refresh()
end

function onExit() end

onOpen()
