package platformratelimit

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

type Class string

const (
	ClassAuthLogin                 Class = "auth_login"
	ClassAuthSignup                Class = "auth_signup"
	ClassAuthSessionMutation       Class = "auth_session_mutation"
	ClassCollaborationInviteCreate Class = "collaboration_invite_create"
	ClassCollaborationInviteAccept Class = "collaboration_invite_accept"
	ClassLLMAdminMutation          Class = "llm_admin_mutation"
	ClassLLMProviderHealth         Class = "llm_provider_health"
)

var productionClasses = []Class{
	ClassAuthLogin,
	ClassAuthSignup,
	ClassAuthSessionMutation,
	ClassCollaborationInviteCreate,
	ClassCollaborationInviteAccept,
	ClassLLMAdminMutation,
	ClassLLMProviderHealth,
}

type Policy struct {
	Limit  int64
	Window time.Duration
}

type PolicySpec struct {
	Limit         int64 `json:"limit"`
	WindowSeconds int64 `json:"window_seconds"`
}

type Input struct {
	Class    Class
	KeyParts []string
	Cost     int64
}

type Decision struct {
	Allowed    bool
	RetryAfter time.Duration
}

type Limiter interface {
	Allow(context.Context, Input) (Decision, error)
}

type Config struct {
	URL               string
	Client            redis.UniversalClient
	KeyHMACSecret     []byte
	Prefix            string
	CommandTimeout    time.Duration
	ConnectTimeout    time.Duration
	Policies          map[Class]Policy
	RequireAllClasses bool
}

type RedisLimiter struct {
	client         redis.UniversalClient
	keySecret      []byte
	prefix         string
	commandTimeout time.Duration
	policies       map[Class]Policy
	ownedClient    bool
}

type Error struct {
	Code string
}

func (e *Error) Error() string {
	switch e.Code {
	case "RATE_LIMIT_POLICY_UNCONFIGURED":
		return "rate-limit policy is not configured"
	case "RATE_LIMIT_INPUT_INVALID":
		return "rate-limit input is invalid"
	case "RATE_LIMIT_CONFIG_INVALID":
		return "rate-limit configuration is invalid"
	default:
		return "rate-limit backend is unavailable"
	}
}

func ErrorCode(err error) string {
	var appErr *Error
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "RATE_LIMIT_BACKEND_UNAVAILABLE"
}


func ParseProductionPolicies(raw string) (map[Class]Policy, error) {
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	var encoded map[string]PolicySpec
	if err := decoder.Decode(&encoded); err != nil {
		return nil, configError()
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return nil, configError()
	}
	policies := make(map[Class]Policy, len(encoded))
	for name, spec := range encoded {
		class := Class(name)
		if !validClass(class) || spec.WindowSeconds <= 0 {
			return nil, configError()
		}
		policy := Policy{Limit: spec.Limit, Window: time.Duration(spec.WindowSeconds) * time.Second}
		if !validPolicy(policy) {
			return nil, configError()
		}
		policies[class] = policy
	}
	if err := validatePolicies(policies, true); err != nil {
		return nil, err
	}
	return policies, nil
}

func NewRedisLimiter(config Config) (*RedisLimiter, error) {
	if len(config.KeyHMACSecret) < 32 || (config.Client == nil) == (strings.TrimSpace(config.URL) == "") {
		return nil, configError()
	}
	prefix := strings.TrimSpace(config.Prefix)
	if prefix == "" {
		prefix = "mirofish:ratelimit:v1"
	}
	if !regexp.MustCompile(`^[A-Za-z0-9:_-]{1,80}$`).MatchString(prefix) {
		return nil, configError()
	}
	commandTimeout := config.CommandTimeout
	if commandTimeout <= 0 {
		commandTimeout = 500 * time.Millisecond
	}
	connectTimeout := config.ConnectTimeout
	if connectTimeout <= 0 {
		connectTimeout = 2 * time.Second
	}
	if commandTimeout > 5*time.Second || connectTimeout > 10*time.Second {
		return nil, configError()
	}
	if err := validatePolicies(config.Policies, config.RequireAllClasses); err != nil {
		return nil, err
	}
	client := config.Client
	owned := false
	if client == nil {
		options, err := redis.ParseURL(strings.TrimSpace(config.URL))
		if err != nil || (options.Protocol != 0 && options.Protocol != 2 && options.Protocol != 3) {
			return nil, configError()
		}
		options.DialTimeout = connectTimeout
		options.ReadTimeout = commandTimeout
		options.WriteTimeout = commandTimeout
		client = redis.NewClient(options)
		owned = true
	}
	limiter := &RedisLimiter{
		client: client, keySecret: append([]byte(nil), config.KeyHMACSecret...), prefix: prefix,
		commandTimeout: commandTimeout, policies: clonePolicies(config.Policies), ownedClient: owned,
	}
	ctx, cancel := context.WithTimeout(context.Background(), connectTimeout)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		_ = limiter.Close()
		return nil, backendError()
	}
	return limiter, nil
}

func (l *RedisLimiter) Allow(ctx context.Context, input Input) (Decision, error) {
	if l == nil || l.client == nil {
		return Decision{}, backendError()
	}
	policy, ok := l.policies[input.Class]
	if !ok {
		return Decision{}, &Error{Code: "RATE_LIMIT_POLICY_UNCONFIGURED"}
	}
	if !validInput(input, policy) {
		return Decision{}, &Error{Code: "RATE_LIMIT_INPUT_INVALID"}
	}
	key := l.redisKey(input.Class, input.KeyParts)
	callCtx, cancel := context.WithTimeout(ctx, l.commandTimeout)
	defer cancel()
	result, err := fixedWindowScript.Run(callCtx, l.client, []string{key}, policy.Limit, policy.Window.Milliseconds(), input.Cost).Slice()
	if err != nil || len(result) != 2 {
		return Decision{}, backendError()
	}
	allowed, ok := scriptInt(result[0])
	retryMS, retryOK := scriptInt(result[1])
	if !ok || !retryOK || (allowed != 0 && allowed != 1) || retryMS < 0 {
		return Decision{}, backendError()
	}
	decision := Decision{Allowed: allowed == 1}
	if !decision.Allowed {
		if retryMS < 1 {
			retryMS = 1
		}
		decision.RetryAfter = time.Duration(retryMS) * time.Millisecond
	}
	return decision, nil
}

func (l *RedisLimiter) Close() error {
	if l == nil || l.client == nil || !l.ownedClient {
		return nil
	}
	return l.client.Close()
}

func (l *RedisLimiter) redisKey(class Class, parts []string) string {
	mac := hmac.New(sha256.New, l.keySecret)
	writeKeyPart(mac, string(class))
	for _, part := range parts {
		writeKeyPart(mac, strings.TrimSpace(part))
	}
	return fmt.Sprintf("%s:%s:%s", l.prefix, class, hex.EncodeToString(mac.Sum(nil)))
}

func writeKeyPart(writer io.Writer, value string) {
	var length [4]byte
	binary.BigEndian.PutUint32(length[:], uint32(len(value)))
	_, _ = writer.Write(length[:])
	_, _ = writer.Write([]byte(value))
}

func validatePolicies(policies map[Class]Policy, requireAll bool) error {
	if len(policies) == 0 {
		return configError()
	}
	for class, policy := range policies {
		if !validClass(class) || !validPolicy(policy) {
			return configError()
		}
	}
	if requireAll {
		for _, class := range productionClasses {
			if _, ok := policies[class]; !ok {
				return configError()
			}
		}
	}
	return nil
}

func validPolicy(policy Policy) bool {
	return policy.Limit > 0 && policy.Limit <= 1_000_000 && policy.Window >= time.Second && policy.Window <= 24*time.Hour
}

func validClass(class Class) bool {
	for _, candidate := range productionClasses {
		if candidate == class {
			return true
		}
	}
	return false
}

func validInput(input Input, policy Policy) bool {
	if !validClass(input.Class) || input.Cost <= 0 || input.Cost > policy.Limit || len(input.KeyParts) == 0 || len(input.KeyParts) > 8 {
		return false
	}
	for _, part := range input.KeyParts {
		trimmed := strings.TrimSpace(part)
		if trimmed == "" || len(trimmed) > 512 || !bytes.Equal([]byte(trimmed), []byte(part)) {
			return false
		}
	}
	return true
}

func clonePolicies(input map[Class]Policy) map[Class]Policy {
	output := make(map[Class]Policy, len(input))
	for class, policy := range input {
		output[class] = policy
	}
	return output
}

func scriptInt(value any) (int64, bool) {
	switch typed := value.(type) {
	case int64:
		return typed, true
	case string:
		var parsed int64
		_, err := fmt.Sscan(typed, &parsed)
		return parsed, err == nil
	default:
		return 0, false
	}
}

func configError() error  { return &Error{Code: "RATE_LIMIT_CONFIG_INVALID"} }
func backendError() error { return &Error{Code: "RATE_LIMIT_BACKEND_UNAVAILABLE"} }

var fixedWindowScript = redis.NewScript(`
local current = redis.call('GET', KEYS[1])
if not current then
  redis.call('SET', KEYS[1], ARGV[3], 'PX', ARGV[2])
  return {1, tonumber(ARGV[2])}
end
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 1 then
  redis.call('DEL', KEYS[1])
  redis.call('SET', KEYS[1], ARGV[3], 'PX', ARGV[2])
  return {1, tonumber(ARGV[2])}
end
if tonumber(current) + tonumber(ARGV[3]) > tonumber(ARGV[1]) then
  return {0, ttl}
end
redis.call('INCRBY', KEYS[1], ARGV[3])
return {1, ttl}
`)
