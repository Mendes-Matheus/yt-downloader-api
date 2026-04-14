local key = KEYS[1]

local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local window_start = now - window

-- Remove antigos
redis.call("ZREMRANGEBYSCORE", key, 0, window_start)

-- Adiciona novo
redis.call("ZADD", key, now, member)

-- Conta
local count = redis.call("ZCARD", key)

-- TTL
-- redis.call("PEXPIRE", key, window)
if redis.call("TTL", key) < 0 then
    redis.call("PEXPIRE", key, window)
end

-- Pega mais antigo
-- local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
local index = count - limit
local ref = redis.call("ZRANGE", key, index, index, "WITHSCORES")

local oldest_score = now
if oldest[2] then
    oldest_score = tonumber(oldest[2])
end

if count > limit then
    -- remove o que acabou de inserir
    redis.call("ZREM", key, member)

    local retry_after = math.ceil(((oldest_score + window) - now) / 1000)
    if retry_after < 1 then
        retry_after = 1
    end

    return {0, count - 1, oldest_score, retry_after}
end

return {1, limit - count, oldest_score, 0}
