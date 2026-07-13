package platformratelimit

import (
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func TestLiveRedisLimiterAtomicTTLFailClosedAndPrivateKeys(t *testing.T) {
	redisURL := strings.TrimSpace(os.Getenv("MIROFISH_PLATFORM_RATE_LIMIT_LIVE_REDIS_URL"))
	if redisURL == "" {
		t.Skip("set MIROFISH_PLATFORM_RATE_LIMIT_LIVE_REDIS_URL for Redis rate-limit live tests")
	}
	prefix := fmt.Sprintf("mirofish:ratelimit:live:%d", time.Now().UnixNano())
	policy := map[Class]Policy{ClassLLMProviderHealth: {Limit: 5, Window: 2 * time.Second}}
	config := Config{
		URL: redisURL, KeyHMACSecret: testSecret, Prefix: prefix, Policies: policy,
		CommandTimeout: time.Second, ConnectTimeout: 2 * time.Second,
	}
	one, err := NewRedisLimiter(config)
	if err != nil {
		t.Fatalf("first limiter: %v", err)
	}
	defer one.Close()
	two, err := NewRedisLimiter(config)
	if err != nil {
		t.Fatalf("second limiter: %v", err)
	}
	defer two.Close()
	rawParts := []string{"tenant-live-private", "actor-live-private", "channel-live-private"}
	input := Input{Class: ClassLLMProviderHealth, KeyParts: rawParts, Cost: 1}
	var allowed atomic.Int64
	var group sync.WaitGroup
	for index := 0; index < 20; index++ {
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
			} else if decision.Allowed {
				allowed.Add(1)
			}
		}(index)
	}
	group.Wait()
	if allowed.Load() != 5 {
		t.Fatalf("cross-instance limit mismatch: %d", allowed.Load())
	}
	options, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatal(err)
	}
	inspector := redis.NewClient(options)
	defer inspector.Close()
	keys, err := inspector.Keys(context.Background(), prefix+":*").Result()
	if err != nil || len(keys) != 1 {
		t.Fatalf("inspect keys: %#v %v", keys, err)
	}
	for _, private := range rawParts {
		if strings.Contains(keys[0], private) {
			t.Fatalf("live Redis key leaked %q", private)
		}
	}
	ttl, err := inspector.PTTL(context.Background(), keys[0]).Result()
	if err != nil || ttl <= 0 || ttl > 2*time.Second {
		t.Fatalf("invalid live TTL: %s %v", ttl, err)
	}
	t.Cleanup(func() { _ = inspector.Del(context.Background(), keys...).Err() })

	deadline := time.Now().Add(3 * time.Second)
	for {
		decision, err := one.Allow(context.Background(), input)
		if err == nil && decision.Allowed {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("live bucket did not expire: %#v %v", decision, err)
		}
		time.Sleep(50 * time.Millisecond)
	}
}
