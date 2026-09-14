-- trilingual_rank.lua
-- RIME lua_filter: re-ranks candidates so the language you are most likely
-- typing (Chinese pinyin / English / Swedish) comes first. Uses a tiny
-- character n-gram naive-Bayes model (langid_model.lua, generated offline)
-- plus the previous commit as context.

local model = require("langid_model")
local words = require("langid_words")

local F = {}

-- ---------------------------------------------------------------- utf8 helpers
local function chars(s)
  local out = {}
  if utf8 and utf8.codes then
    for _, cp in utf8.codes(s) do out[#out + 1] = utf8.char(cp) end
  else
    for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do out[#out + 1] = ch end
  end
  return out
end

local function has_cjk(s)
  -- CJK Unified Ideographs are 3-byte UTF-8 starting with E4..E9
  return s:find("[\228-\233][\128-\191][\128-\191]") ~= nil
end

local function has_nordic(s)
  return s:find("å") or s:find("ä") or s:find("ö") or s:find("Å") or s:find("Ä") or s:find("Ö")
end

-- ------------------------------------------------------------- classification
local idx = {}
for i, c in ipairs(model.classes) do idx[c] = i end

local function classify(text)
  text = text:lower()
  local cs = chars(text)
  table.insert(cs, 1, "^")
  cs[#cs + 1] = "$"
  local n = #model.classes
  local s = {}
  for i = 1, n do s[i] = 0 end
  for len = model.min_n, model.max_n do
    for i = 1, #cs - len + 1 do
      local g = table.concat(cs, "", i, i + len - 1)
      local row = model.p[g]
      if row then
        for k = 1, n do s[k] = s[k] + row[k] end
      else
        for k = 1, n do s[k] = s[k] + model.unseen[k] end
      end
    end
  end
  -- whole-word feature
  do
    local row = model.p["W:" .. text]
    if row then
      for k = 1, n do s[k] = s[k] + row[k] end
    else
      for k = 1, n do s[k] = s[k] + model.unseen[k] end
    end
  end
  -- temperature: short inputs are very uncertain; soften a bit
  local temp = 1.0 + 2.0 / math.max(1, #cs - 2)
  local m = -math.huge
  for k = 1, n do s[k] = s[k] / temp; if s[k] > m then m = s[k] end end
  local z = 0
  local p = {}
  for k = 1, n do p[k] = math.exp(s[k] - m); z = z + p[k] end
  local out = {}
  for k = 1, n do out[model.classes[k]] = p[k] / z end
  return out
end

-- language of a candidate string (used to bucket candidates)
local function cand_lang(text)
  if has_cjk(text) then return "zh" end
  if has_nordic(text) then return "sv" end
  local lt = text:lower()
  local in_en, in_sv = words.en[lt], words.sv[lt]
  if in_en and not in_sv then return "en" end
  if in_sv and not in_en then return "sv" end
  local p = classify(text)
  if p.sv > p.en then return "sv" else return "en" end
end

-- language of the most recent commit (context signal)
local function history_lang(ctx)
  local ok, t = pcall(function() return ctx.commit_history:latest_text() end)
  if not ok or not t or t == "" then return nil end
  local last = t:match("(%S+)%s*$") or t
  if last == "" then return nil end
  if has_cjk(last) then return "zh" end
  if not last:find("^[%a\128-\255]+$") then return nil end -- punctuation / numbers: no signal
  return cand_lang(last)
end

local function renorm(p)
  local z = p.zh + p.en + p.sv
  p.zh, p.en, p.sv = p.zh / z, p.en / z, p.sv / z
  return p
end

-- ------------------------------------------------------------------- filter
function F.init(env)
  env.max_scan = 60
  local cfg = env.engine.schema.config
  env.show_confidence = cfg:get_bool("trilingual/show_confidence") or false
end

local FOLD = { ["å"] = "a", ["ä"] = "a", ["ö"] = "o", ["é"] = "e", ["ü"] = "u" }
local function fold(s)
  return (s:lower():gsub("[\195][\128-\191]", function(c) return FOLD[c] or c end))
end

function F.func(input, env)
  local ctx = env.engine.context
  local inp = ctx.input or ""
  if inp == "" then
    for cand in input:iter() do yield(cand) end
    return
  end

  local p = classify(inp)
  -- context: previous word/phrase language
  local h = history_lang(ctx)
  if h then p[h] = p[h] * 1.6 end
  -- physical å/ä/ö key was pressed during this composition
  if ctx:get_property("sv_hint") == "1" then p.sv = p.sv * 4 end
  renorm(p)

  local buckets = { zh = {}, en = {}, sv = {} }
  local n = 0
  local seg_start, seg_end
  local exact_latin = false
  local typed = inp:gsub("[%s']", "")
  for cand in input:iter() do
    local lang = cand_lang(cand.text)
    if lang ~= "zh" then
      cand.comment = ""
      if fold(cand.text) == typed then exact_latin = true end
    end
    if not seg_start then seg_start, seg_end = cand.start, cand._end end
    table.insert(buckets[lang], cand)
    n = n + 1
    if n >= env.max_scan then break end
  end

  local order = { "zh", "en", "sv" }
  table.sort(order, function(a, b) return p[a] > p[b] end)
  -- the top language must actually have something to show
  while #order > 1 and #buckets[order[1]] == 0 do table.remove(order, 1) end
  local primary, second, third = order[1], order[2], order[3]

  local out = {}
  -- Latin word that is in no dictionary (names, commands, slang): offer it verbatim
  if primary ~= "zh" and not exact_latin and typed:find("^[%a]+$") and seg_start then
    out[#out + 1] = Candidate("raw", seg_start, seg_end, typed, "")
  end
  for _, c in ipairs(buckets[primary]) do out[#out + 1] = c end
  -- keep one escape hatch per other language near the top
  local function inject(list, pos, prob, thresh)
    if #list > 0 and prob >= thresh then
      local c = table.remove(list, 1)
      table.insert(out, math.min(pos, #out + 1), c)
    end
  end
  if second then inject(buckets[second], 3, p[second], 0.10) end
  if third then inject(buckets[third], 5, p[third], 0.06) end
  if second then for _, c in ipairs(buckets[second]) do out[#out + 1] = c end end
  if third then for _, c in ipairs(buckets[third]) do out[#out + 1] = c end end

  if env.show_confidence and #out > 0 then
    out[1].comment = string.format(" %s %d%%", primary, math.floor(p[primary] * 100 + 0.5))
  end
  for _, c in ipairs(out) do yield(c) end
  for cand in input:iter() do yield(cand) end
end

return F
