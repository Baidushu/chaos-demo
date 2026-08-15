local failures_key = KEYS[1]
local totals_key = KEYS[2]
local open_until_key = KEYS[3]

local action = ARGV[1]
local now = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local min_request_count = tonumber(ARGV[5])
local failure_rate_threshold = tonumber(ARGV[6])
local open_timeout = tonumber(ARGV[7])
local total_member = ARGV[8]
local failure_member = ARGV[9]

redis.call('ZREMRANGEBYSCORE', failures_key, '-inf', now - window)
redis.call('ZREMRANGEBYSCORE', totals_key, '-inf', now - window)

redis.call('ZADD', totals_key, now, total_member)
redis.call('EXPIRE', totals_key, ttl)

if action == 'failure' then
  redis.call('ZADD', failures_key, now, failure_member)
  redis.call('EXPIRE', failures_key, ttl)
end

local failure_count = redis.call('ZCARD', failures_key)
local total_count = redis.call('ZCARD', totals_key)
local failure_rate = 0
if total_count > 0 then
  failure_rate = failure_count / total_count
end

local current_open_until = tonumber(redis.call('GET', open_until_key) or '0')
if total_count >= min_request_count and failure_rate >= failure_rate_threshold and current_open_until <= now then
  local next_open_until = now + open_timeout
  redis.call('SET', open_until_key, tostring(next_open_until))
  return {1, failure_count, total_count, failure_rate, next_open_until}
end

return {0, failure_count, total_count, failure_rate, current_open_until}
