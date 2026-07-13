package main

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"mirofish-novel/apps/api/internal/httpapi"

	enumspb "go.temporal.io/api/enums/v1"
	taskqueuepb "go.temporal.io/api/taskqueue/v1"
	workflowservice "go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/sdk/client"
)

type readinessTemporalClient struct {
	healthErr  error
	missingKey string
}

func (c readinessTemporalClient) CheckHealth(context.Context, *client.CheckHealthRequest) (*client.CheckHealthResponse, error) {
	return &client.CheckHealthResponse{}, c.healthErr
}

func (c readinessTemporalClient) DescribeTaskQueue(_ context.Context, queue string, queueType enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
	key := queue + ":" + queueType.String()
	if key == c.missingKey {
		return &workflowservice.DescribeTaskQueueResponse{}, nil
	}
	return &workflowservice.DescribeTaskQueueResponse{Pollers: []*taskqueuepb.PollerInfo{{Identity: "private-worker"}}}, nil
}

func TestNewProductionReadinessCheckerAllowsExplicitLocalDisabledDependencies(t *testing.T) {
	checker, closeChecker, err := newProductionReadinessChecker(productionReadinessConfig{DeploymentEnvironment: "local"})
	if err != nil {
		t.Fatal(err)
	}
	if closeChecker == nil {
		t.Fatal("expected readiness closer")
	}
	defer func() { _ = closeChecker() }()
	report := checker.Check(context.Background())
	if len(report.Dependencies) != 4 {
		t.Fatalf("unexpected dependencies: %#v", report.Dependencies)
	}
	for _, dependency := range report.Dependencies {
		if dependency.Status != "disabled" || dependency.ErrorCode != "" {
			t.Fatalf("local dependency was not explicitly disabled: %#v", dependency)
		}
	}
}

func TestNewProductionReadinessCheckerRejectsMissingProductionConfiguration(t *testing.T) {
	base := completeReadinessConfig()
	tests := []struct {
		name   string
		mutate func(*productionReadinessConfig)
	}{
		{name: "postgres", mutate: func(config *productionReadinessConfig) { config.DatabaseURL = "" }},
		{name: "redis", mutate: func(config *productionReadinessConfig) { config.RedisURL = "" }},
		{name: "temporal", mutate: func(config *productionReadinessConfig) { config.TemporalAddress = "" }},
		{name: "temporal queue", mutate: func(config *productionReadinessConfig) { config.TemporalTaskQueues[1] = "" }},
		{name: "object storage", mutate: func(config *productionReadinessConfig) { config.ObjectBucket = "" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			config := base
			config.TemporalTaskQueues = append([]string(nil), base.TemporalTaskQueues...)
			test.mutate(&config)
			checker, closeChecker, err := newProductionReadinessChecker(config)
			if closeChecker != nil {
				_ = closeChecker()
			}
			if err == nil || checker != nil {
				t.Fatalf("missing %s configuration did not fail bootstrap", test.name)
			}
		})
	}
}

func TestConcurrentReadinessCheckerIsBoundedAndMapsOnlyStableCodes(t *testing.T) {
	checker := &concurrentReadinessChecker{timeout: 20 * time.Millisecond, probes: []readinessProbe{
		{name: "postgres", check: func(context.Context) string { return "POSTGRES_UNAVAILABLE" }},
		{name: "redis", check: func(ctx context.Context) string { <-ctx.Done(); return "private redis error" }},
		{name: "temporal", check: func(context.Context) string { return "" }},
		{name: "object_storage"},
	}}
	started := time.Now()
	report := checker.Check(context.Background())
	if time.Since(started) > time.Second {
		t.Fatal("readiness checker exceeded its bound")
	}
	if len(report.Dependencies) != 4 || report.Dependencies[0].ErrorCode != "POSTGRES_UNAVAILABLE" || report.Dependencies[1].ErrorCode != "READINESS_TIMEOUT" {
		t.Fatalf("unexpected bounded report: %#v", report.Dependencies)
	}
}

func TestTemporalReadinessProbeRequiresHealthAndEveryPollerType(t *testing.T) {
	queues := []string{"maintenance", "writer"}
	if code := temporalReadinessProbe(readinessTemporalClient{}, queues)(context.Background()); code != "" {
		t.Fatalf("all pollers were not ready: %s", code)
	}
	if code := temporalReadinessProbe(readinessTemporalClient{healthErr: errors.New("private endpoint")}, queues)(context.Background()); code != "TEMPORAL_UNAVAILABLE" {
		t.Fatalf("health failure returned %q", code)
	}
	missing := "writer:" + enumspb.TASK_QUEUE_TYPE_ACTIVITY.String()
	if code := temporalReadinessProbe(readinessTemporalClient{missingKey: missing}, queues)(context.Background()); code != "TEMPORAL_POLLERS_UNAVAILABLE" {
		t.Fatalf("missing activity poller returned %q", code)
	}
}

type controlledTemporalReadinessClient struct {
	health   func(context.Context) error
	describe func(context.Context, string, enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error)
}

func (c controlledTemporalReadinessClient) CheckHealth(ctx context.Context, _ *client.CheckHealthRequest) (*client.CheckHealthResponse, error) {
	if c.health != nil {
		if err := c.health(ctx); err != nil {
			return nil, err
		}
	}
	return &client.CheckHealthResponse{}, nil
}

func (c controlledTemporalReadinessClient) DescribeTaskQueue(ctx context.Context, queue string, queueType enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
	return c.describe(ctx, queue, queueType)
}

func readyTemporalTaskQueue() *workflowservice.DescribeTaskQueueResponse {
	return &workflowservice.DescribeTaskQueueResponse{Pollers: []*taskqueuepb.PollerInfo{{Identity: "private-worker"}}}
}

func TestTemporalReadinessProbeRetriesOnlyUnavailablePollers(t *testing.T) {
	missingKey := "writer:" + enumspb.TASK_QUEUE_TYPE_ACTIVITY.String()
	var mutex sync.Mutex
	calls := make(map[string]int)
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{describe: func(_ context.Context, queue string, queueType enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
		key := queue + ":" + queueType.String()
		mutex.Lock()
		calls[key]++
		call := calls[key]
		mutex.Unlock()
		if key == missingKey && call == 1 {
			return nil, errors.New("transient private error")
		}
		return readyTemporalTaskQueue(), nil
	}}, []string{"maintenance", "writer"})

	if code := probe(context.Background()); code != "" {
		t.Fatalf("transient poller failure did not recover: %q", code)
	}
	mutex.Lock()
	defer mutex.Unlock()
	if calls[missingKey] != 2 {
		t.Fatalf("transient poller calls = %d, want 2", calls[missingKey])
	}
	for key, count := range calls {
		if key != missingKey && count != 1 {
			t.Fatalf("ready poller %s was retried %d times", key, count)
		}
	}
}

func TestTemporalReadinessProbeFailsClosedForPersistentMissingPoller(t *testing.T) {
	missingKey := "writer:" + enumspb.TASK_QUEUE_TYPE_ACTIVITY.String()
	var calls atomic.Int32
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{describe: func(_ context.Context, queue string, queueType enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
		if queue+":"+queueType.String() == missingKey {
			calls.Add(1)
			return &workflowservice.DescribeTaskQueueResponse{}, nil
		}
		return readyTemporalTaskQueue(), nil
	}}, []string{"maintenance", "writer"})

	if code := probe(context.Background()); code != "TEMPORAL_POLLERS_UNAVAILABLE" {
		t.Fatalf("persistent missing poller returned %q", code)
	}
	if calls.Load() != temporalPollerAttempts {
		t.Fatalf("persistent missing poller calls = %d, want %d", calls.Load(), temporalPollerAttempts)
	}
}

func TestTemporalReadinessProbeTimeoutStopsWorkers(t *testing.T) {
	var active atomic.Int32
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{describe: func(ctx context.Context, _ string, _ enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
		active.Add(1)
		defer active.Add(-1)
		<-ctx.Done()
		return nil, ctx.Err()
	}}, []string{"maintenance", "writer"})
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()

	if code := probe(ctx); code != "TEMPORAL_UNAVAILABLE" {
		t.Fatalf("timed out pollers returned %q", code)
	}
	if active.Load() != 0 {
		t.Fatalf("poller workers remained active after timeout: %d", active.Load())
	}
}

func TestTemporalReadinessProbeBoundsDescribeConcurrency(t *testing.T) {
	var active atomic.Int32
	var maximum atomic.Int32
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{describe: func(context.Context, string, enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
		current := active.Add(1)
		defer active.Add(-1)
		for {
			observed := maximum.Load()
			if current <= observed || maximum.CompareAndSwap(observed, current) {
				break
			}
		}
		time.Sleep(5 * time.Millisecond)
		return readyTemporalTaskQueue(), nil
	}}, []string{"one", "two", "three", "four", "five", "six"})

	if code := probe(context.Background()); code != "" {
		t.Fatalf("ready pollers returned %q", code)
	}
	if got := maximum.Load(); got > temporalPollerWorkers {
		t.Fatalf("maximum DescribeTaskQueue concurrency = %d, want <= %d", got, temporalPollerWorkers)
	}
	if active.Load() != 0 {
		t.Fatalf("poller workers remained active: %d", active.Load())
	}
}

func TestTemporalReadinessProbeBoundsDescribeConcurrencyAcrossRequests(t *testing.T) {
	var active atomic.Int32
	var maximum atomic.Int32
	var callsMutex sync.Mutex
	calls := make(map[string]int)
	healthBarrier := make(chan struct{})
	healthArrived := make(chan struct{}, 12)
	firstDescribe := make(chan struct{})
	describeBarrier := make(chan struct{})
	var describeOnce sync.Once
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{
		health: func(context.Context) error {
			healthArrived <- struct{}{}
			<-healthBarrier
			return nil
		},
		describe: func(_ context.Context, queue string, queueType enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
			describeOnce.Do(func() {
				close(firstDescribe)
				<-describeBarrier
			})
			callsMutex.Lock()
			calls[queue+":"+queueType.String()]++
			callsMutex.Unlock()
			current := active.Add(1)
			defer active.Add(-1)
			for {
				observed := maximum.Load()
				if current <= observed || maximum.CompareAndSwap(observed, current) {
					break
				}
			}
			time.Sleep(time.Millisecond)
			return readyTemporalTaskQueue(), nil
		},
	}, []string{"one", "two", "three", "four", "five"})

	const requestCount = 12
	results := make(chan string, requestCount)
	var requests sync.WaitGroup
	requests.Add(requestCount)
	for range requestCount {
		go func() {
			defer requests.Done()
			results <- probe(context.Background())
		}()
	}
	for range requestCount {
		<-healthArrived
	}
	close(healthBarrier)
	<-firstDescribe
	time.Sleep(10 * time.Millisecond)
	close(describeBarrier)
	requests.Wait()
	close(results)
	for code := range results {
		if code != "" {
			t.Fatalf("ready concurrent request returned %q", code)
		}
	}
	if got := maximum.Load(); got > temporalPollerWorkers {
		t.Fatalf("global maximum DescribeTaskQueue concurrency = %d, want <= %d", got, temporalPollerWorkers)
	}
	if active.Load() != 0 {
		t.Fatalf("poller workers remained active: %d", active.Load())
	}
	callsMutex.Lock()
	defer callsMutex.Unlock()
	if len(calls) != 10 {
		t.Fatalf("described targets = %d, want 10", len(calls))
	}
	for target, count := range calls {
		if count != 1 {
			t.Fatalf("coalesced target %s described %d times", target, count)
		}
	}
}

func TestTemporalReadinessProbeFollowerCancellationDoesNotCancelLeaderOrCacheResult(t *testing.T) {
	var calls atomic.Int32
	started := make(chan struct{})
	release := make(chan struct{})
	var once sync.Once
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{describe: func(context.Context, string, enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
		calls.Add(1)
		once.Do(func() {
			close(started)
			<-release
		})
		return readyTemporalTaskQueue(), nil
	}}, []string{"maintenance", "writer"})
	leaderResult := make(chan string, 1)
	go func() { leaderResult <- probe(context.Background()) }()
	<-started

	followerCtx, cancelFollower := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancelFollower()
	if code := probe(followerCtx); code != "TEMPORAL_UNAVAILABLE" {
		t.Fatalf("cancelled follower returned %q", code)
	}
	select {
	case code := <-leaderResult:
		t.Fatalf("follower cancellation ended leader with %q", code)
	default:
	}
	close(release)
	if code := <-leaderResult; code != "" {
		t.Fatalf("leader returned %q", code)
	}
	if firstRoundCalls := calls.Load(); firstRoundCalls != 4 {
		t.Fatalf("first poller round calls = %d, want 4", firstRoundCalls)
	}

	if code := probe(context.Background()); code != "" {
		t.Fatalf("fresh probe returned %q", code)
	}
	if calls.Load() != 8 {
		t.Fatalf("completed flight was cached: total calls = %d, want 8", calls.Load())
	}
}

func TestTemporalReadinessProbeLeaderTimeoutPublishesAndClearsFlight(t *testing.T) {
	var block atomic.Bool
	block.Store(true)
	started := make(chan struct{}, temporalPollerWorkers)
	probe := temporalReadinessProbe(controlledTemporalReadinessClient{describe: func(ctx context.Context, _ string, _ enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error) {
		if block.Load() {
			started <- struct{}{}
			<-ctx.Done()
			return nil, ctx.Err()
		}
		return readyTemporalTaskQueue(), nil
	}}, []string{"maintenance", "writer"})
	leaderCtx, cancelLeader := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancelLeader()
	leaderResult := make(chan string, 1)
	go func() { leaderResult <- probe(leaderCtx) }()
	<-started
	followerResult := make(chan string, 1)
	go func() { followerResult <- probe(context.Background()) }()

	if code := <-leaderResult; code != "TEMPORAL_UNAVAILABLE" {
		t.Fatalf("timed out leader returned %q", code)
	}
	if code := <-followerResult; code != "TEMPORAL_UNAVAILABLE" {
		t.Fatalf("leader timeout was not published to follower: %q", code)
	}
	block.Store(false)
	if code := probe(context.Background()); code != "" {
		t.Fatalf("probe after timed out flight returned %q", code)
	}
}

func TestParseReadinessTimeoutIsStrictAndBounded(t *testing.T) {
	for _, raw := range []string{"invalid", "0s", "-1s", "11s"} {
		if _, err := parseReadinessTimeout(raw); err == nil {
			t.Fatalf("accepted invalid timeout %q", raw)
		}
	}
	if timeout, err := parseReadinessTimeout("5s"); err != nil || timeout != 5*time.Second {
		t.Fatalf("valid timeout failed: %s %v", timeout, err)
	}
}

func completeReadinessConfig() productionReadinessConfig {
	return productionReadinessConfig{
		DeploymentEnvironment:  "staging",
		DatabaseURL:            "postgres://app:password@127.0.0.1:5432/app?sslmode=disable",
		RequiredMigration:      latestRequiredMigration,
		RequiredMigrationCount: requiredMigrationCount,
		RedisURL:               "redis://127.0.0.1:6379/0",
		TemporalAddress:        "127.0.0.1:7233",
		TemporalNamespace:      "default",
		TemporalClient:         readinessTemporalClient{},
		TemporalTaskQueues:     []string{"maintenance", "writer"},
		ObjectEndpoint:         "127.0.0.1:9000",
		ObjectBucket:           "bucket",
		ObjectAccessKey:        "access",
		ObjectSecretKey:        "secret",
	}
}

var _ httpapi.ReadinessChecker = (*concurrentReadinessChecker)(nil)
