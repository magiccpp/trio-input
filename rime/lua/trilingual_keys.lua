-- trilingual_keys.lua
-- RIME lua_processor:
--  1. Physical å/ä/ö keys (Swedish keyboard) are folded into a/a/o so the
--     composition keeps going, and a "sv_hint" property is raised so the
--     ranker prefers Swedish candidates.
--  2. Punctuation follows the language of the last commit: after Chinese
--     text the normal (full-width) punctuator runs; after Latin text the
--     ASCII punctuation is committed directly.

local P = {}

local kRejected, kAccepted, kNoop = 0, 1, 2

local nordic = {
  aring = "a", Aring = "a",
  adiaeresis = "a", Adiaeresis = "a",
  odiaeresis = "o", Odiaeresis = "o",
}

local ascii_punct = {
  comma = ",", period = ".", question = "?", exclam = "!",
  colon = ":", semicolon = ";", parenleft = "(", parenright = ")",
}

local function has_cjk(s)
  return s and s:find("[\228-\233][\128-\191][\128-\191]") ~= nil
end

function P.init(env) end

function P.func(key, env)
  if key:release() or key:ctrl() or key:alt() or key:super() then return kNoop end
  local ctx = env.engine.context
  local name = key:repr()
  -- strip modifier prefixes like "Shift+"
  name = name:gsub("^.*%+", "")

  -- when a new composition starts, forget the Swedish hint
  if not ctx:is_composing() then ctx:set_property("sv_hint", "0") end

  local fold = nordic[name]
  if fold then
    if ctx:get_option("ascii_mode") then return kNoop end
    ctx:set_property("sv_hint", "1")
    ctx:push_input(fold)
    return kAccepted
  end

  local punct = ascii_punct[name]
  if punct and not ctx:is_composing() and not ctx:get_option("ascii_mode") then
    local ok, last = pcall(function() return ctx.commit_history:latest_text() end)
    if ok and last and last ~= "" and not has_cjk(last) then
      env.engine:commit_text(punct)
      return kAccepted
    end
  end
  return kNoop
end

return P
