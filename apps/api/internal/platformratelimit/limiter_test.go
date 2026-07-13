package platformratelimit

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

var testSecret = []byte("0123456789abcdef0123456789abcdef")

func TestFixedWindowIsAtomicAcrossLimiterInstancesAndExpires(t *testing.T) {
	server := miniredis.RunT(t)
	clientOne := redis.NewClient(&redis.Options{Addr: server.Addr()})
	clientTwo := redis.NewClient(&redis.Options{Addr: server.Addr()})
	policy := map[Class]Policy{ClassAuthLogin: {Limit: 10, Window: time.Minute}}
	one := newTestLimiter(t, clientOne, policy)
	two := newTestLimiter(t, clientTwo, policy)
	input := Input{Class: ClassAuthLogin, KeyParts: []string{"203.0.113.8", "user@example.test"}, Cost: 1}

	var allowed atomic.Int64
	var group sync.WaitGroup
	for index := 0; index < 50; index++ {
		group.Add(1)
		go func(index int) {
			defer group.Done()
			limiter := one
			if index%2 == 1 {
				limiter = two
			}
			decision, err := limiter.Allow(context.Background(), input)
			if err != nil {
				t.Errorf("allow: %v", err)
				return
			}
			if decision.Allowed {
				allowed.Add(1)
			} else if decision.RetryAfter <= 0 || decision.RetryAfter > time.Minute {
				t.Errorf("invalid retry delay: %s", decision.RetryAfter)
			}
		}(index)
	}
	group.Wait()
	if allowed.Load() != 10 {
		t.Fatalf("atomic limit mismatch: allowed=%d", allowed.Load())
	}
	server.FastForward(time.Minute)
	decision, err := one.Allow(context.Background(), input)
	if err != nil || !decision.Allowed {
		t.Fatalf("expired bucket remained blocked: %#v %v", decision, err)
	}
}

func TestRedisKeysAreHMACBoundedAndNeverContainRawIdentity(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	limiter := newTestLimiter(t, client, map[Class]Policy{ClassCollaborationInviteAccept: {Limit: 2, Window: time.Minute}})
	raw := []string{"tenant-private", "token-hash-private", "client-private"}
	if _, err := limiter.Allow(context.Background(), Input{Class: ClassCollaborationInviteAccept, KeyParts: raw, Cost: 1}); err != nil {
		t.Fatal(err)
	}
	keys := server.Keys()
	if len(keys) != 1 || !strings.HasPrefix(keys[0], "mirofish:ratelimit:v1:collaboration_invite_accept:") {
		t.Fatalf("unexpected Redis keys: %#v", keys)
	}
	for _, private := range raw {
		if strings.Contains(keys[0], private) {
			t.Fatalf("Redis key leaked %q: %s", private, keys[0])
		}
	}
	if len(strings.TrimPrefix(keys[0], "mirofish:ratelimit:v1:collaboration_invite_accept:")) != 64 {
		t.Fatalf("key digest is not SHA-256: %s", keys[0])
	}
}

func TestLimiterFailsClosedWithStableErrors(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	limiter := newTestLimiter(t, client, map[Class]Policy{ClassLLMAdminMutation: {Limit: 2, Window: time.Minute}})
	_, err := limiter.Allow(context.Background(), Input{Class: ClassAuthLogin, KeyParts: []string{"private"}, Cost: 1})
	if ErrorCode(err) != "RATE_LIMIT_POLICY_UNCONFIGURED" {
		t.Fatalf("missing policy did not fail closed: %v", err)
	}
	_, err = limiter.Allow(context.Background(), Input{Class: ClassLLMAdminMutation, KeyParts: []string{" private "}, Cost: 1})
	if ErrorCode(err) != "RATE_LIMIT_INPUT_INVALID" {
		t.Fatalf("invalid input accepted: %v", err)
	}
	serverAddress := server.Addr()
	server.Close()
	_, err = limiter.Allow(context.Background(), Input{Class: ClassLLMAdminMutation, KeyParts: []string{"private"}, Cost: 1})
	if ErrorCode(err) != "RATE_LIMIT_BACKEND_UNAVAILABLE" || strings.Contains(err.Error(), serverAddress) || strings.Contains(err.Error(), "private") {
		t.Fatalf("backend error was unsafe: %v", err)
	}
}

func TestProductionPolicyParserRequiresEveryKnownClassAndRejectsUnknownFields(t *testing.T) {
	parts := make([]string, 0, len(productionClasses))
	for _, class := range productionClasses {
		parts = append(parts, fmt.Sprintf(`%q:{"limit":10,"window_seconds":60}`, class))
	}
	policies, err := ParseProductionPolicies("{" + strings.Join(parts, ",") + "}")
	if err != nil || len(policies) != len(productionClasses) {
		t.Fatalf("valid policies rejected: %#v %v", policies, err)
	}
	for _, raw := range []string{
		`{"auth_login":{"limit":10,"window_seconds":60}}`,
		`{"auth_login":{"limit":10,"window_seconds":60,"burst":2}}`,
		`{"unknown":{"limit":10,"window_seconds":60}}`,
	} {
		if _, err := ParseProductionPolicies(raw); ErrorCode(err) != "RATE_LIMIT_CONFIG_INVALID" {
			t.Fatalf("invalid policy accepted: %s err=%v", raw, err)
		}
	}
}

func TestConstructorRequiresDedicatedSecretAndExactlyOneBackend(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	policy := map[Class]Policy{ClassAuthSessionMutation: {Limit: 1, Window: time.Minute}}
	for _, config := range []Config{
		{Client: client, KeyHMACSecret: []byte("short"), Policies: policy},
		{Client: client, URL: "redis://127.0.0.1:6379/0", KeyHMACSecret: testSecret, Policies: policy},
		{KeyHMACSecret: testSecret, Policies: policy},
		{Client: client, KeyHMACSecret: testSecret, Policies: map[Class]Policy{}},
	} {
		if _, err := NewRedisLimiter(config); ErrorCode(err) != "RATE_LIMIT_CONFIG_INVALID" {
			t.Fatalf("invalid constructor config accepted: %#v err=%v", config, err)
		}
	}
}

func newTestLimiter(t *testing.T, client redis.UniversalClient, policies map[Class]Policy) *RedisLimiter {
	t.Helper()
	limiter, err := NewRedisLimiter(Config{
		Client: client, KeyHMACSecret: testSecret, Policies: policies,
		CommandTimeout: time.Second, ConnectTimeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	return limiter
}
