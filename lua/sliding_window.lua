local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)

local current = redis.call('ZCARD', key)
if current >= limit then
  return 0
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return 1
