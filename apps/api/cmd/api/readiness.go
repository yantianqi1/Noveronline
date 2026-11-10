package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"mirofish-novel/apps/api/internal/httpapi"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/redis/go-redis/v9"
	enumspb "go.temporal.io/api/enums/v1"
	workflowservice "go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/sdk/client"
)

const (
	defaultReadinessTimeout = 3 * time.Second
	maxReadinessTimeout     = 10 * time.Second
	temporalPollerWorkers   = 4
	temporalPollerAttempts  = 2
	temporalPollerRetryWait = 25 * time.Millisecond
	latestRequiredMigration = "0032_email_verification"
	requiredMigrationCount  = 32
)

type productionReadinessConfig struct {
	DeploymentEnvironment  string
	Timeout                string
	DatabaseURL            string
	RequiredMigration      string
	RequiredMigrationCount int
	RedisURL               string
	TemporalAddress        string
	TemporalNamespace      string
	TemporalClient         temporalReadinessClient
	TemporalTaskQueues     []string
	ObjectEndpoint         string
	ObjectBucket           string
	ObjectAccessKey        string
	ObjectSecretKey        string
	ObjectUseSSL           bool
}

type readinessProbe struct {
	name  string
	check func(context.Context) string
}

type temporalReadinessClient interface {
	CheckHealth(context.Context, *client.CheckHealthRequest) (*client.CheckHealthResponse, error)
	DescribeTaskQueue(context.Context, string, enumspb.TaskQueueType) (*workflowservice.DescribeTaskQueueResponse, error)
}

type concurrentReadinessChecker struct {
	timeout time.Duration
	probes  []readinessProbe
}

type readinessProbeResult struct {
	index      int
	dependency httpapi.ReadinessDependency
}

func newProductionReadinessChecker(config productionReadinessConfig) (httpapi.ReadinessChecker, func() error, error) {
	timeout, err := parseReadinessTimeout(config.Timeout)
	if err != nil {
		return nil, nil, err
	}
	required := isProductionLike(config.DeploymentEnvironment)
	probes := make([]readinessProbe, 0, 4)
	closers := make([]func() error, 0, 2)
	fail := func(err error) (httpapi.ReadinessChecker, func() error, error) {
		for _, closeResource := range closers {
			_ = closeResource()
		}
		return nil, nil, err
	}

	databaseURL := strings.TrimSpace(config.DatabaseURL)
	if databaseURL == "" {
		if required {
			return fail(errors.New("readiness postgres configuration is required"))
		}
		probes = append(probes, readinessProbe{name: "postgres"})
	} else {
		requiredMigration := strings.TrimSpace(config.RequiredMigration)
		if requiredMigration == "" || config.RequiredMigrationCount <= 0 {
			return fail(errors.New("readiness schema migration configuration is incomplete"))
		}
		db, openErr := openAppDatabase(databaseURL)
		if openErr != nil {
			return fail(errors.New("readiness postgres configuration is invalid"))
		}
		closers = append(closers, appDatabaseCloser(db))
		probes = append(probes, readinessProbe{name: "postgres", check: postgresReadinessProbe(db, requiredMigration, config.RequiredMigrationCount)})
	}

	redisURL := strings.TrimSpace(config.RedisURL)
	if redisURL == "" {
		if required {
			return fail(errors.New("readiness redis configuration is required"))
		}
		probes = append(probes, readinessProbe{name: "redis"})
	} else {
		options, parseErr := redis.ParseURL(redisURL)
		if parseErr != nil {
			return fail(errors.New("readiness redis configuration is invalid"))
		}
		redisClient := redis.NewClient(options)
		closers = append(closers, redisClient.Close)
		probes = append(probes, readinessProbe{name: "redis", check: func(ctx context.Context) string {
			if err := redisClient.Ping(ctx).Err(); err != nil {
				return "REDIS_UNAVAILABLE"
			}
			return ""
		}})
	}

	temporalConfigured, temporalErr := validateTemporalReadinessConfig(config)
	if temporalErr != nil {
		return fail(temporalErr)
	}
	if !temporalConfigured {
		if required {
			return fail(errors.New("readiness temporal configuration is required"))
		}
		probes = append(probes, readinessProbe{name: "temporal"})
	} else {
		queues := append([]string(nil), config.TemporalTaskQueues...)
		probes = append(probes, readinessProbe{name: "temporal", check: temporalReadinessProbe(config.TemporalClient, queues)})
	}

	objectConfigured, objectErr := validateObjectReadinessConfig(config)
	if objectErr != nil {
		return fail(objectErr)
	}
	if !objectConfigured {
		if required {
			return fail(errors.New("readiness object storage configuration is required"))
		}
		probes = append(probes, readinessProbe{name: "object_storage"})
	} else {
		objectClient, minioErr := minio.New(strings.TrimSpace(config.ObjectEndpoint), &minio.Options{
			Creds:  credentials.NewStaticV4(strings.TrimSpace(config.ObjectAccessKey), strings.TrimSpace(config.ObjectSecretKey), ""),
			Secure: config.ObjectUseSSL,
		})
		if minioErr != nil {
			return fail(errors.New("readiness object storage configuration is invalid"))
		}
		bucket := strings.TrimSpace(config.ObjectBucket)
		probes = append(probes, readinessProbe{name: "object_storage", check: func(ctx context.Context) string {
			exists, err := objectClient.BucketExists(ctx, bucket)
			if err != nil {
				return "OBJECT_STORAGE_UNAVAILABLE"
			}
			if !exists {
				return "OBJECT_STORAGE_BUCKET_MISSING"
			}
			return ""
		}})
	}

	closeAll := func() error {
		var closeErr error
		for _, closeResource := range closers {
			closeErr = errors.Join(closeErr, closeResource())
		}
		return closeErr
	}
	return &concurrentReadinessChecker{timeout: timeout, probes: probes}, closeAll, nil
}

func (c *concurrentReadinessChecker) Check(parent context.Context) httpapi.ReadinessReport {
	checkedAt := time.Now().UTC()
	dependencies := make([]httpapi.ReadinessDependency, len(c.probes))
	ctx, cancel := context.WithTimeout(parent, c.timeout)
	defer cancel()
	results := make(chan readinessProbeResult, len(c.probes))
	pending := make(map[int]struct{}, len(c.probes))
	for index, probe := range c.probes {
		if probe.check == nil {
			dependencies[index] = httpapi.ReadinessDependency{Name: probe.name, Status: "disabled"}
			continue
		}
		pending[index] = struct{}{}
		go func(index int, probe readinessProbe) {
			code := probe.check(ctx)
			dependency := httpapi.ReadinessDependency{Name: probe.name, Status: "ready"}
			if code != "" {
				dependency.Status = "unavailable"
				dependency.ErrorCode = code
			}
			results <- readinessProbeResult{index: index, dependency: dependency}
		}(index, probe)
	}
	for len(pending) > 0 {
		select {
		case result := <-results:
			if _, ok := pending[result.index]; ok {
				dependencies[result.index] = result.dependency
				delete(pending, result.index)
			}
		case <-ctx.Done():
			for index := range pending {
				dependencies[index] = httpapi.ReadinessDependency{
					Name: c.probes[index].name, Status: "unavailable", ErrorCode: "READINESS_TIMEOUT",
				}
			}
			pending = nil
		}
	}
	return httpapi.ReadinessReport{Dependencies: dependencies, CheckedAt: checkedAt}
}

func postgresReadinessProbe(db *sql.DB, requiredMigration string, requiredCount int) func(context.Context) string {
	return func(ctx context.Context) string {
		if err := db.PingContext(ctx); err != nil {
			return "POSTGRES_UNAVAILABLE"
		}
		var migrationPresent bool
		var migrationCount int
		err := db.QueryRowContext(ctx, `
			SELECT EXISTS(SELECT 1 FROM mirofish_schema_migrations WHERE version=$1),
			       (SELECT count(*) FROM mirofish_schema_migrations)
		`, requiredMigration).Scan(&migrationPresent, &migrationCount)
		if err != nil {
			return "POSTGRES_SCHEMA_UNAVAILABLE"
		}
		if !migrationPresent || migrationCount < requiredCount {
			return "SCHEMA_MIGRATION_INCOMPLETE"
		}
		return ""
	}
}

func temporalReadinessProbe(temporalClient temporalReadinessClient, queues []string) func(context.Context) string {
	describeSlots := make(chan struct{}, temporalPollerWorkers)
	var flightMutex sync.Mutex
	var flight *temporalPollerFlight
	return func(ctx context.Context) string {
		if _, err := temporalClient.CheckHealth(ctx, nil); err != nil {
			return "TEMPORAL_UNAVAILABLE"
		}
		targets := make([]temporalPollerTarget, 0, len(queues)*2)
		for _, queue := range queues {
			for _, queueType := range []enumspb.TaskQueueType{enumspb.TASK_QUEUE_TYPE_WORKFLOW, enumspb.TASK_QUEUE_TYPE_ACTIVITY} {
				targets = append(targets, temporalPollerTarget{queue: queue, queueType: queueType})
			}
		}

		flightMutex.Lock()
		if flight != nil {
			current := flight
			flightMutex.Unlock()
			select {
			case <-current.done:
				return current.code
			case <-ctx.Done():
				return "TEMPORAL_UNAVAILABLE"
			}
		}
		current := &temporalPollerFlight{done: make(chan struct{})}
		flight = current
		flightMutex.Unlock()

		code := checkTemporalPollers(ctx, temporalClient, targets, describeSlots)
		flightMutex.Lock()
		current.code = code
		flight = nil
		close(current.done)
		flightMutex.Unlock()
		return code
	}
}

type temporalPollerTarget struct {
	queue     string
	queueType enumspb.TaskQueueType
}

type temporalPollerFlight struct {
	done chan struct{}
	code string
}

func checkTemporalPollers(
	ctx context.Context,
	temporalClient temporalReadinessClient,
	targets []temporalPollerTarget,
	describeSlots chan struct{},
) string {
	for attempt := 0; attempt < temporalPollerAttempts; attempt++ {
		var timedOut bool
		targets, timedOut = unavailableTemporalPollers(ctx, temporalClient, targets, describeSlots)
		if timedOut {
			return "TEMPORAL_UNAVAILABLE"
		}
		if len(targets) == 0 {
			return ""
		}
		if attempt+1 < temporalPollerAttempts && !waitForTemporalPollerRetry(ctx) {
			return "TEMPORAL_UNAVAILABLE"
		}
	}
	return "TEMPORAL_POLLERS_UNAVAILABLE"
}

func unavailableTemporalPollers(
	ctx context.Context,
	temporalClient temporalReadinessClient,
	targets []temporalPollerTarget,
	describeSlots chan struct{},
) ([]temporalPollerTarget, bool) {
	if len(targets) == 0 {
		return nil, false
	}
	workerCount := min(temporalPollerWorkers, len(targets))
	jobs := make(chan int, len(targets))
	ready := make([]bool, len(targets))
	for index := range targets {
		jobs <- index
	}
	close(jobs)

	var workers sync.WaitGroup
	workers.Add(workerCount)
	for range workerCount {
		go func() {
			defer workers.Done()
			for index := range jobs {
				if !acquireTemporalDescribeSlot(ctx, describeSlots) {
					return
				}
				target := targets[index]
				description, err := temporalClient.DescribeTaskQueue(ctx, target.queue, target.queueType)
				<-describeSlots
				ready[index] = err == nil && description != nil && len(description.Pollers) > 0
			}
		}()
	}
	workers.Wait()
	if ctx.Err() != nil {
		return nil, true
	}

	unavailable := make([]temporalPollerTarget, 0)
	for index, target := range targets {
		if !ready[index] {
			unavailable = append(unavailable, target)
		}
	}
	return unavailable, false
}

func acquireTemporalDescribeSlot(ctx context.Context, describeSlots chan struct{}) bool {
	if ctx.Err() != nil {
		return false
	}
	select {
	case describeSlots <- struct{}{}:
		return true
	case <-ctx.Done():
		return false
	}
}

func waitForTemporalPollerRetry(ctx context.Context) bool {
	timer := time.NewTimer(temporalPollerRetryWait)
	defer timer.Stop()
	select {
	case <-timer.C:
		return true
	case <-ctx.Done():
		return false
	}
}

func validateTemporalReadinessConfig(config productionReadinessConfig) (bool, error) {
	address := strings.TrimSpace(config.TemporalAddress)
	namespace := strings.TrimSpace(config.TemporalNamespace)
	configuredQueues := 0
	seen := make(map[string]struct{}, len(config.TemporalTaskQueues))
	for _, rawQueue := range config.TemporalTaskQueues {
		queue := strings.TrimSpace(rawQueue)
		if queue == "" {
			continue
		}
		configuredQueues++
		if _, duplicate := seen[queue]; duplicate {
			return false, errors.New("readiness temporal task queues must be unique")
		}
		seen[queue] = struct{}{}
	}
	anyConfigured := address != "" || namespace != "" || config.TemporalClient != nil || configuredQueues > 0
	if !anyConfigured {
		return false, nil
	}
	if address == "" || namespace == "" || config.TemporalClient == nil || configuredQueues != len(config.TemporalTaskQueues) || configuredQueues == 0 {
		return false, errors.New("readiness temporal configuration is incomplete")
	}
	return true, nil
}

func validateObjectReadinessConfig(config productionReadinessConfig) (bool, error) {
	values := []string{config.ObjectEndpoint, config.ObjectBucket, config.ObjectAccessKey, config.ObjectSecretKey}
	configured := 0
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			configured++
		}
	}
	if configured == 0 {
		return false, nil
	}
	if configured != len(values) {
		return false, errors.New("readiness object storage configuration is incomplete")
	}
	return true, nil
}

func parseReadinessTimeout(raw string) (time.Duration, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return defaultReadinessTimeout, nil
	}
	timeout, err := time.ParseDuration(raw)
	if err != nil || timeout <= 0 || timeout > maxReadinessTimeout {
		return 0, fmt.Errorf("readiness timeout must be between 0 and %s", maxReadinessTimeout)
	}
	return timeout, nil
}

func isProductionLike(environment string) bool {
	environment = strings.ToLower(strings.TrimSpace(environment))
	return environment == "staging" || environment == "production"
}
