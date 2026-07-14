package main

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"go.temporal.io/sdk/client"

	"mirofish-novel/apps/api/internal/assetcatalog"
	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/authrecovery"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/httpapi"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/observability"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"
	"mirofish-novel/apps/api/internal/writerplanning"
)

const testPlatformRateLimitPolicies = `{
		"auth_login":{"limit":5,"window_seconds":60},
		"auth_signup":{"limit":3,"window_seconds":300},
	"auth_session_mutation":{"limit":30,"window_seconds":60},
	"collaboration_invite_create":{"limit":10,"window_seconds":60},
	"collaboration_invite_accept":{"limit":10,"window_seconds":60},
	"llm_admin_mutation":{"limit":30,"window_seconds":60},
	"llm_provider_health":{"limit":5,"window_seconds":60}
}`

func TestOpenAppDatabaseUsesBoundedPool(t *testing.T) {
	db, err := openAppDatabase("postgres://app:private@127.0.0.1:1/app?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	if db.Stats().MaxOpenConnections != appDatabaseMaxOpenConnections {
		t.Fatalf("unexpected app database pool bound: %#v", db.Stats())
	}
}

func TestNewAuthRuntimeSharesOneBoundedSQLPool(t *testing.T) {
	runtime, closeRuntime, err := newAuthRuntime("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if err != nil {
		t.Fatalf("new auth runtime: %v", err)
	}
	if closeRuntime == nil || runtime.db == nil {
		t.Fatal("configured auth runtime did not expose one closeable shared pool")
	}
	defer func() {
		if err := closeRuntime(); err != nil {
			t.Fatalf("close auth runtime: %v", err)
		}
	}()
	if runtime.db.Stats().MaxOpenConnections != authDatabaseMaxOpenConnections {
		t.Fatalf("unexpected auth pool bound: %#v", runtime.db.Stats())
	}
	if _, ok := runtime.reader.(*auth.SQLReader); !ok {
		t.Fatalf("expected shared SQL reader, got %T", runtime.reader)
	}
	if _, ok := runtime.passwordAuthenticator.(*auth.SQLPasswordAuthenticator); !ok {
		t.Fatalf("expected shared SQL password authenticator, got %T", runtime.passwordAuthenticator)
	}
	if _, ok := runtime.passwordChanger.(*auth.SQLPasswordChanger); !ok {
		t.Fatalf("expected shared SQL password changer, got %T", runtime.passwordChanger)
	}
	if _, ok := runtime.sessionStore.(*auth.SQLSessionStore); !ok {
		t.Fatalf("expected shared SQL session store, got %T", runtime.sessionStore)
	}
	if _, ok := runtime.authorizer.(*auth.SQLAuthorizer); !ok {
		t.Fatalf("expected targeted SQL authorizer, got %T", runtime.authorizer)
	}
}

func TestNewAuthRuntimeKeepsUnconfiguredModeFailClosed(t *testing.T) {
	runtime, closeRuntime, err := newAuthRuntime("")
	if err != nil || closeRuntime != nil || runtime.db != nil {
		t.Fatalf("unexpected unconfigured auth runtime: db=%v close=%v err=%v", runtime.db != nil, closeRuntime != nil, err)
	}
	if _, ok := runtime.reader.(auth.DisabledReader); !ok {
		t.Fatalf("expected disabled auth reader, got %T", runtime.reader)
	}
	if runtime.passwordAuthenticator != nil || runtime.passwordChanger != nil || runtime.sessionStore != nil {
		t.Fatalf("unconfigured auth mutation dependencies must stay disabled: %#v", runtime)
	}
}

func TestNewPlatformRateLimiterIsExplicitAndProductionRequired(t *testing.T) {
	limiter, closeLimiter, err := newPlatformRateLimiter("local", "", "", "")
	if err != nil || limiter != nil || closeLimiter != nil {
		t.Fatalf("local unconfigured limiter should be explicitly disabled: limiter=%T close=%v err=%v", limiter, closeLimiter != nil, err)
	}
	if _, _, err := newPlatformRateLimiter("production", "", "", ""); err == nil {
		t.Fatal("production accepted a missing platform rate limiter")
	}
	if _, _, err := newPlatformRateLimiter("local", "redis://127.0.0.1:6379/0", "", testPlatformRateLimitPolicies); err == nil {
		t.Fatal("partial platform rate limiter configuration was accepted")
	}

	redisServer := miniredis.RunT(t)
	limiter, closeLimiter, err = newPlatformRateLimiter(
		"staging",
		"redis://"+redisServer.Addr()+"/0",
		"0123456789abcdef0123456789abcdef",
		testPlatformRateLimitPolicies,
	)
	if err != nil || limiter == nil || closeLimiter == nil {
		t.Fatalf("complete staging limiter was not constructed: limiter=%T close=%v err=%v", limiter, closeLimiter != nil, err)
	}
	if err := closeLimiter(); err != nil {
		t.Fatalf("close platform limiter: %v", err)
	}
}

func TestNewTrustedClientProofVerifierFollowsLimiterRequirement(t *testing.T) {
	verifier, err := newTrustedClientProofVerifier("", false)
	if err != nil || verifier != nil {
		t.Fatalf("optional empty verifier should be disabled: verifier=%T err=%v", verifier, err)
	}
	if _, err := newTrustedClientProofVerifier("", true); err == nil {
		t.Fatal("rate-limited deployment accepted a missing trusted client proof verifier")
	}
	if _, err := newTrustedClientProofVerifier("short", true); err == nil {
		t.Fatal("trusted client proof verifier accepted a short key")
	}
	verifier, err = newTrustedClientProofVerifier("0123456789abcdef0123456789abcdef", true)
	if err != nil || verifier == nil {
		t.Fatalf("valid trusted client proof verifier was rejected: verifier=%T err=%v", verifier, err)
	}
}

func TestNewAuthReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newAuthReader("")

	if err != nil {
		t.Fatalf("new auth reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(auth.DisabledReader); !ok {
		t.Fatalf("expected disabled auth reader, got %T", reader)
	}
}

func TestNewAuthReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newAuthReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close auth reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new auth reader: %v", err)
	}
	if _, ok := reader.(*auth.SQLReader); !ok {
		t.Fatalf("expected SQL auth reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAuthSessionStoreUsesNilWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newAuthSessionStore("")

	if err != nil {
		t.Fatalf("new auth session store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil auth session store without database URL, got %T", store)
	}
}

func TestNewAuthSessionStoreUsesSQLSessionStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newAuthSessionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close auth session store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new auth session store: %v", err)
	}
	if _, ok := store.(*auth.SQLSessionStore); !ok {
		t.Fatalf("expected SQL auth session store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewPasswordAuthenticatorUsesNilWithoutDatabaseURL(t *testing.T) {
	authenticator, closeAuthenticator, err := newPasswordAuthenticator("")

	if err != nil {
		t.Fatalf("new password authenticator: %v", err)
	}
	if closeAuthenticator != nil {
		t.Fatal("expected no close function without database URL")
	}
	if authenticator != nil {
		t.Fatalf("expected nil password authenticator without database URL, got %T", authenticator)
	}
}

func TestNewPasswordAuthenticatorUsesSQLPasswordAuthenticatorWithDatabaseURL(t *testing.T) {
	authenticator, closeAuthenticator, err := newPasswordAuthenticator("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeAuthenticator != nil {
		defer func() {
			if err := closeAuthenticator(); err != nil {
				t.Fatalf("close password authenticator: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new password authenticator: %v", err)
	}
	if _, ok := authenticator.(*auth.SQLPasswordAuthenticator); !ok {
		t.Fatalf("expected SQL password authenticator, got %T", authenticator)
	}
	if closeAuthenticator == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewPasswordChangerUsesNilWithoutDatabaseURL(t *testing.T) {
	changer, closeChanger, err := newPasswordChanger("")

	if err != nil {
		t.Fatalf("new password changer: %v", err)
	}
	if closeChanger != nil {
		t.Fatal("expected no close function without database URL")
	}
	if changer != nil {
		t.Fatalf("expected nil password changer without database URL, got %T", changer)
	}
}

func TestNewPasswordChangerUsesSQLPasswordChangerWithDatabaseURL(t *testing.T) {
	changer, closeChanger, err := newPasswordChanger("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeChanger != nil {
		defer func() {
			if err := closeChanger(); err != nil {
				t.Fatalf("close password changer: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new password changer: %v", err)
	}
	if _, ok := changer.(*auth.SQLPasswordChanger); !ok {
		t.Fatalf("expected SQL password changer, got %T", changer)
	}
	if closeChanger == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestAuthSessionSecretEnvIsCarriedIntoHTTPConfig(t *testing.T) {
	t.Setenv("MIROFISH_AUTH_SESSION_SECRET", "session-secret")
	t.Setenv("MIROFISH_DEPLOYMENT_ENV", "local")
	t.Setenv("MIROFISH_ENABLE_DEVELOPMENT_AUTH", "1")

	config := withSessionAuthSecret(httpapi.Config{})

	if config.SessionAuthSecret != "session-secret" {
		t.Fatalf("expected session secret in HTTP config, got %q", config.SessionAuthSecret)
	}
	if !config.AllowDevelopmentAuth {
		t.Fatal("expected explicit local development auth opt-in")
	}
	if config.ForceSecureSessionCookies {
		t.Fatal("local HTTP development unexpectedly forced Secure session cookies")
	}
}

func TestProductionLikeEnvironmentsForceSecureSessionCookies(t *testing.T) {
	for _, environment := range []string{"staging", "production"} {
		t.Run(environment, func(t *testing.T) {
			t.Setenv("MIROFISH_DEPLOYMENT_ENV", environment)
			config := withSessionAuthSecret(httpapi.Config{})
			if !config.ForceSecureSessionCookies {
				t.Fatalf("%s did not force Secure session cookies", environment)
			}
		})
	}
}

func TestDevelopmentAuthCannotBeEnabledOutsideLocalEnvironment(t *testing.T) {
	for _, environment := range []string{"", "staging", "production"} {
		t.Run(environment, func(t *testing.T) {
			if developmentAuthAllowed(environment, "1") {
				t.Fatalf("development auth enabled in %q environment", environment)
			}
		})
	}
	if developmentAuthAllowed("local", "0") {
		t.Fatal("development auth enabled without explicit opt-in")
	}
	if !developmentAuthAllowed("local", "true") {
		t.Fatal("development auth did not enable for explicit local opt-in")
	}
}

func TestNewTemporalStartersWiresWriterAndHelloToSharedTemporalClient(t *testing.T) {
	writerStarter, helloStarter, seedStarter, assetStarter, styleStarter, assetReindexStarter, storyGraphStarter, storyGraphBondStarter := newTemporalStarters(
		&mainRecordingTemporalClient{},
		"writer-streaming",
		"maintenance",
		"seed-heavy",
		"asset-light",
		"graph-heavy",
	)

	if _, ok := writerStarter.(*workflows.TemporalWriterStarter); !ok {
		t.Fatalf("expected temporal writer starter, got %T", writerStarter)
	}
	if _, ok := helloStarter.(*workflows.TemporalHelloAgentStarter); !ok {
		t.Fatalf("expected temporal hello starter, got %T", helloStarter)
	}
	if _, ok := seedStarter.(*workflows.TemporalSeedRunStarter); !ok {
		t.Fatalf("expected temporal seed starter, got %T", seedStarter)
	}
	if _, ok := assetStarter.(*workflows.TemporalAssetIngestionStarter); !ok {
		t.Fatalf("expected temporal asset ingestion starter, got %T", assetStarter)
	}
	if _, ok := styleStarter.(*workflows.TemporalStyleExtractionStarter); !ok {
		t.Fatalf("expected temporal style extraction starter, got %T", styleStarter)
	}
	if _, ok := assetReindexStarter.(*workflows.TemporalAssetReindexStarter); !ok {
		t.Fatalf("expected temporal asset reindex starter, got %T", assetReindexStarter)
	}
	if _, ok := storyGraphStarter.(*workflows.TemporalStoryGraphBuildStarter); !ok {
		t.Fatalf("expected temporal story graph build starter, got %T", storyGraphStarter)
	}
	if _, ok := storyGraphBondStarter.(*workflows.TemporalStoryGraphBondGenerationStarter); !ok {
		t.Fatalf("expected temporal story graph bond generation starter, got %T", storyGraphBondStarter)
	}
}

func TestNewLLMTelemetryReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newLLMTelemetryReader("")

	if err != nil {
		t.Fatalf("new telemetry reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(llm.DisabledTelemetryReader); !ok {
		t.Fatalf("expected disabled reader, got %T", reader)
	}
}

func TestNewLLMTelemetryReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newLLMTelemetryReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close telemetry reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new telemetry reader: %v", err)
	}
	if _, ok := reader.(*llm.SQLTelemetryReader); !ok {
		t.Fatalf("expected SQL telemetry reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWriterEventReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWriterEventReader("")

	if err != nil {
		t.Fatalf("new writer event reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*workflows.DisabledWriterEventReader); !ok {
		t.Fatalf("expected disabled writer event reader, got %T", reader)
	}
}

func TestNewWriterEventReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWriterEventReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close writer event reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new writer event reader: %v", err)
	}
	if _, ok := reader.(*workflows.SQLWriterEventReader); !ok {
		t.Fatalf("expected SQL writer event reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWriterReaderUsesNilReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWriterReader("")

	if err != nil {
		t.Fatalf("new writer reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if reader != nil {
		t.Fatalf("expected nil writer reader without database URL, got %T", reader)
	}
}

func TestNewWriterReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWriterReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close writer reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new writer reader: %v", err)
	}
	if _, ok := reader.(*workflows.SQLWriterReader); !ok {
		t.Fatalf("expected SQL writer reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewManuscriptReaderUsesNilReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newManuscriptReader("")

	if err != nil {
		t.Fatalf("new manuscript reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if reader != nil {
		t.Fatalf("expected nil manuscript reader without database URL, got %T", reader)
	}
}

func TestNewManuscriptReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newManuscriptReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close manuscript reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new manuscript reader: %v", err)
	}
	if _, ok := reader.(*workflows.SQLManuscriptReader); !ok {
		t.Fatalf("expected SQL manuscript reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewManuscriptArtifactExporterUsesNilWithoutDatabaseURL(t *testing.T) {
	exporter, closeExporter, err := newManuscriptArtifactExporter("")

	if err != nil {
		t.Fatalf("new manuscript artifact exporter: %v", err)
	}
	if closeExporter != nil || exporter != nil {
		t.Fatalf("expected nil exporter/closer without database URL, got exporter=%T closer=%v", exporter, closeExporter != nil)
	}
}

func TestNewWorkspaceHandlersRequireDatabaseAndExplicitArtifactRoot(t *testing.T) {
	authorizer := auth.NewReaderBackedAuthorizer(auth.NewDisabledReader())

	writerHandler, closeWriter, err := newWriterWorkspaceHandler("", authorizer, nil)
	if err != nil || writerHandler != nil || closeWriter != nil {
		t.Fatalf("expected disabled writer workspace without database: handler=%T close=%v err=%v", writerHandler, closeWriter != nil, err)
	}
	manuscriptHandler, downloadHandler, closeManuscript, err := newManuscriptWorkspaceHandlers("", "", authorizer, nil, nil, nil, nil)
	if err != nil || manuscriptHandler != nil || downloadHandler != nil || closeManuscript != nil {
		t.Fatalf("expected disabled manuscript workspace without database: workspace=%T download=%T close=%v err=%v", manuscriptHandler, downloadHandler, closeManuscript != nil, err)
	}

	databaseURL := "postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable"
	writerHandler, closeWriter, err = newWriterWorkspaceHandler(databaseURL, authorizer, nil)
	if err != nil || writerHandler == nil || closeWriter == nil {
		t.Fatalf("expected configured writer workspace: handler=%T close=%v err=%v", writerHandler, closeWriter != nil, err)
	}
	defer func() { _ = closeWriter() }()

	if _, _, _, err = newManuscriptWorkspaceHandlers(databaseURL, "", authorizer, nil, nil, nil, nil); err == nil {
		t.Fatal("expected manuscript workspace to reject an empty artifact root")
	}
	manuscriptHandler, downloadHandler, closeManuscript, err = newManuscriptWorkspaceHandlers(databaseURL, t.TempDir(), authorizer, nil, nil, nil, nil)
	if err != nil || manuscriptHandler == nil || downloadHandler == nil || closeManuscript == nil {
		t.Fatalf("expected configured manuscript workspace: workspace=%T download=%T close=%v err=%v", manuscriptHandler, downloadHandler, closeManuscript != nil, err)
	}
	defer func() { _ = closeManuscript() }()
}

type permissionRecordingAuthorizer struct {
	inputs []auth.AuthorizeInput
	errors map[auth.Permission]error
}

func (a *permissionRecordingAuthorizer) Authorize(_ context.Context, input auth.AuthorizeInput) error {
	a.inputs = append(a.inputs, input)
	return a.errors[input.Permission]
}

func TestAssetCatalogSecurityHandlerUsesCentralActorAndExplicitCapabilities(t *testing.T) {
	path := "/v1/projects/project-123/asset-catalog/assets/asset-123"

	t.Run("read-only", func(t *testing.T) {
		authorizer := &permissionRecordingAuthorizer{errors: map[auth.Permission]error{
			auth.PermissionAssetManage: &auth.AppError{Code: auth.CodeAccessDenied},
		}}
		called := false
		next := http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			called = true
			scope, ok := assetcatalog.RequestScopeFromContext(request.Context())
			if !ok || scope.ActorID != "user-123" || scope.TenantID != "tenant-123" || scope.ProjectID != "project-123" {
				t.Fatalf("unexpected asset scope: %#v ok=%v", scope, ok)
			}
			if scope.Can(assetcatalog.PermissionReadPrivate) || scope.Can(assetcatalog.PermissionMutate) || scope.Can(assetcatalog.PermissionCollections) {
				t.Fatalf("read-only actor received management capabilities: %#v", scope.Permissions)
			}
			response.WriteHeader(http.StatusNoContent)
		})
		server := httpapi.NewServer(httpapi.Config{AllowDevelopmentAuth: true, AssetCatalogHandler: assetCatalogSecurityHandler{next: next, authorizer: authorizer}})
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request.Header.Set("X-User-Id", "user-123")
		request.Header.Set("X-Tenant-Id", "tenant-123")
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)

		if response.Code != http.StatusNoContent || !called || len(authorizer.inputs) != 2 {
			t.Fatalf("unexpected read-only result: status=%d called=%v auth=%#v", response.Code, called, authorizer.inputs)
		}
	})

	for _, test := range []struct {
		name   string
		method string
		path   string
	}{
		{name: "mutation", method: http.MethodPatch, path: path},
		{name: "private read", method: http.MethodGet, path: path + "?include_private=true"},
	} {
		t.Run(test.name+" denied", func(t *testing.T) {
			authorizer := &permissionRecordingAuthorizer{errors: map[auth.Permission]error{
				auth.PermissionAssetManage: &auth.AppError{Code: auth.CodeAccessDenied},
			}}
			called := false
			server := httpapi.NewServer(httpapi.Config{AllowDevelopmentAuth: true, AssetCatalogHandler: assetCatalogSecurityHandler{
				next: http.HandlerFunc(func(http.ResponseWriter, *http.Request) { called = true }), authorizer: authorizer,
			}})
			request := httptest.NewRequest(test.method, test.path, nil)
			request.Header.Set("X-User-Id", "user-123")
			request.Header.Set("X-Tenant-Id", "tenant-123")
			response := httptest.NewRecorder()
			server.ServeHTTP(response, request)
			if response.Code != http.StatusForbidden || called {
				t.Fatalf("denied asset request reached handler: status=%d called=%v body=%s", response.Code, called, response.Body.String())
			}
		})
	}

	t.Run("optional capability lookup failure", func(t *testing.T) {
		authorizer := &permissionRecordingAuthorizer{errors: map[auth.Permission]error{
			auth.PermissionAssetManage: errors.New("database unavailable"),
		}}
		server := httpapi.NewServer(httpapi.Config{AllowDevelopmentAuth: true, AssetCatalogHandler: assetCatalogSecurityHandler{
			next:       http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Fatal("backend failure reached asset handler") }),
			authorizer: authorizer,
		}})
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request.Header.Set("X-User-Id", "user-123")
		request.Header.Set("X-Tenant-Id", "tenant-123")
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)
		if response.Code != http.StatusServiceUnavailable {
			t.Fatalf("expected authorization backend failure, got %d: %s", response.Code, response.Body.String())
		}
	})
}

func TestNewPlatformHandlersAreExplicitlyConfiguredAndFailClosed(t *testing.T) {
	for _, name := range []string{
		"AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY", "MIROFISH_RECOVERY_CLIENT_PROOF_SECRET",
		"SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TLS_MODE",
		"AUTH_RECOVERY_RESET_BASE_URL", "COLLABORATION_ACCEPT_BASE_URL",
	} {
		t.Setenv(name, "")
	}
	metrics := observability.NewRegistry()
	recovery, collaborationHandler, projectAdmin, admin, dispatcher, closeHandlers, err := newPlatformHandlers("", "", metrics, nil, nil)
	if err != nil || recovery != nil || collaborationHandler != nil || projectAdmin != nil || admin != nil || dispatcher != nil || closeHandlers != nil {
		t.Fatalf("expected platform handlers disabled without DB: recovery=%T collaboration=%T project=%T admin=%T dispatcher=%v close=%v err=%v", recovery, collaborationHandler, projectAdmin, admin, dispatcher != nil, closeHandlers != nil, err)
	}

	databaseURL := "postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable"
	recovery, collaborationHandler, projectAdmin, admin, dispatcher, closeHandlers, err = newPlatformHandlers(databaseURL, "", metrics, nil, nil)
	if err != nil || recovery == nil || collaborationHandler == nil || projectAdmin == nil || admin == nil || dispatcher != nil || closeHandlers == nil {
		t.Fatalf("expected DB-backed handlers with optional facilities fail-closed: recovery=%T collaboration=%T project=%T admin=%T dispatcher=%v close=%v err=%v", recovery, collaborationHandler, projectAdmin, admin, dispatcher != nil, closeHandlers != nil, err)
	}
	_ = closeHandlers()

	t.Setenv("AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY", "not-standard-base64")
	if _, _, _, _, _, _, err = newPlatformHandlers(databaseURL, "", metrics, nil, nil); err == nil {
		t.Fatal("expected malformed recovery token key to fail construction")
	}
	t.Setenv("AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY", "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODk=")
	t.Setenv("MIROFISH_RECOVERY_CLIENT_PROOF_SECRET", "0123456789abcdef0123456789abcdef")
	t.Setenv("SMTP_HOST", "smtp.example.test")
	if _, _, _, _, _, _, err = newPlatformHandlers(databaseURL, "", metrics, nil, nil); err == nil {
		t.Fatal("expected partial SMTP configuration to fail construction")
	}
}

func TestNewRecoveryTokenCipherRequiresStrictBase64KeyByEnvironment(t *testing.T) {
	validKey := "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODk="
	tests := []struct {
		name        string
		environment string
		key         string
		wantCipher  bool
		wantError   bool
	}{
		{name: "empty local", environment: "local"},
		{name: "missing staging", environment: "staging", wantError: true},
		{name: "missing production", environment: "production", wantError: true},
		{name: "malformed base64", environment: "local", key: "not-standard-base64", wantError: true},
		{name: "non-zero trailing padding bits", environment: "local", key: "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODl=", wantError: true},
		{name: "wrong decoded length", environment: "local", key: "c2hvcnQ=", wantError: true},
		{name: "valid 32 byte key", environment: "production", key: validKey, wantCipher: true},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			cipher, err := newRecoveryTokenCipher(test.environment, test.key)
			if (err != nil) != test.wantError {
				t.Fatalf("unexpected error state: %v", err)
			}
			if (cipher != nil) != test.wantCipher {
				t.Fatalf("unexpected cipher state: %T", cipher)
			}
		})
	}
}

func TestNewPlatformHandlersWiresRecoveryDispatcherMetrics(t *testing.T) {
	for name, value := range map[string]string{
		"MIROFISH_DEPLOYMENT_ENV":               "local",
		"AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY":   "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODk=",
		"SMTP_HOST":                             "127.0.0.1",
		"SMTP_PORT":                             "2525",
		"SMTP_USERNAME":                         "test-user",
		"SMTP_PASSWORD":                         "test-password",
		"SMTP_FROM":                             "security@example.test",
		"SMTP_TLS_MODE":                         authrecovery.SMTPModeLoopbackPlaintext,
		"AUTH_RECOVERY_RESET_BASE_URL":          "http://localhost/recovery/reset",
		"COLLABORATION_ACCEPT_BASE_URL":         "",
		"MIROFISH_RECOVERY_CLIENT_PROOF_SECRET": "",
	} {
		t.Setenv(name, value)
	}
	metrics := observability.NewRegistry()
	_, _, _, _, dispatcher, closeHandlers, err := newPlatformHandlers(
		"postgres://mirofish:secret@127.0.0.1:1/mirofish?sslmode=disable&connect_timeout=1",
		"", metrics, nil, nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = closeHandlers() }()
	if dispatcher == nil {
		t.Fatal("expected recovery dispatcher")
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if _, err := dispatcher.DispatchOne(ctx); err == nil {
		t.Fatal("expected unreachable database to fail dispatch")
	}
	response := httptest.NewRecorder()
	metrics.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	if !strings.Contains(response.Body.String(), `mirofish_auth_recovery_delivery_total{status="backend_error"} 1`) {
		t.Fatalf("constructed dispatcher did not update shared registry: %s", response.Body.String())
	}
}

func TestNewManuscriptArtifactExporterUsesSQLExporterWithDatabaseURL(t *testing.T) {
	exporter, closeExporter, err := newManuscriptArtifactExporter("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeExporter != nil {
		defer func() {
			if err := closeExporter(); err != nil {
				t.Fatalf("close manuscript artifact exporter: %v", err)
			}
		}()
	}
	if err != nil {
		t.Fatalf("new manuscript artifact exporter: %v", err)
	}
	if _, ok := exporter.(*workflows.SQLManuscriptArtifactExporter); !ok || closeExporter == nil {
		t.Fatalf("expected SQL manuscript artifact exporter with closer, got %T", exporter)
	}
}

func TestNewWorkflowReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorkflowReader("")

	if err != nil {
		t.Fatalf("new workflow reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*workflows.DisabledWorkflowReader); !ok {
		t.Fatalf("expected disabled workflow reader, got %T", reader)
	}
}

func TestNewWorkflowReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorkflowReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close workflow reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new workflow reader: %v", err)
	}
	if _, ok := reader.(*workflows.SQLWorkflowReader); !ok {
		t.Fatalf("expected SQL workflow reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorkflowEventReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorkflowEventReader("")

	if err != nil {
		t.Fatalf("new workflow event reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*workflows.DisabledWorkflowEventReader); !ok {
		t.Fatalf("expected disabled workflow event reader, got %T", reader)
	}
}

func TestNewWorkflowEventReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorkflowEventReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close workflow event reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new workflow event reader: %v", err)
	}
	if _, ok := reader.(*workflows.SQLWorkflowEventReader); !ok {
		t.Fatalf("expected SQL workflow event reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewSeedRunReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newSeedRunReader("")

	if err != nil {
		t.Fatalf("new seed run reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*workflows.DisabledSeedRunReader); !ok {
		t.Fatalf("expected disabled seed run reader, got %T", reader)
	}
}

func TestNewSeedRunReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newSeedRunReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close seed run reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new seed run reader: %v", err)
	}
	if _, ok := reader.(*workflows.SQLSeedRunReader); !ok {
		t.Fatalf("expected SQL seed run reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewProjectReadinessReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newProjectReadinessReader("")

	if err != nil {
		t.Fatalf("new project readiness reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*projectreadiness.DisabledReader); !ok {
		t.Fatalf("expected disabled project readiness reader, got %T", reader)
	}
}

func TestNewProjectReadinessReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newProjectReadinessReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close project readiness reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new project readiness reader: %v", err)
	}
	if _, ok := reader.(*projectreadiness.SQLReader); !ok {
		t.Fatalf("expected SQL project readiness reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewProjectOverviewReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newProjectOverviewReader("")

	if err != nil {
		t.Fatalf("new project overview reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*projectoverview.DisabledReader); !ok {
		t.Fatalf("expected disabled project overview reader, got %T", reader)
	}
}

func TestNewProjectOverviewReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newProjectOverviewReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close project overview reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new project overview reader: %v", err)
	}
	if _, ok := reader.(*projectoverview.SQLReader); !ok {
		t.Fatalf("expected SQL project overview reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorkflowCancellerUsesDisabledCancellerWithoutBackends(t *testing.T) {
	canceller, closeCanceller, err := newWorkflowCanceller(nil, "")

	if err != nil {
		t.Fatalf("new workflow canceller: %v", err)
	}
	if closeCanceller != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := canceller.(*workflows.DisabledWorkflowCanceller); !ok {
		t.Fatalf("expected disabled workflow canceller, got %T", canceller)
	}
}

func TestNewWorkflowCancellerUsesTemporalAndSQLStoreWithDatabaseURL(t *testing.T) {
	canceller, closeCanceller, err := newWorkflowCanceller(
		&mainRecordingTemporalClient{},
		"postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable",
	)
	if closeCanceller != nil {
		defer func() {
			if err := closeCanceller(); err != nil {
				t.Fatalf("close workflow canceller: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new workflow canceller: %v", err)
	}
	if _, ok := canceller.(*workflows.TemporalWorkflowCanceller); !ok {
		t.Fatalf("expected temporal workflow canceller, got %T", canceller)
	}
	if closeCanceller == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorkflowRetrierUsesDisabledRetrierWithoutBackends(t *testing.T) {
	retrier, closeRetrier, err := newWorkflowRetrier(nil, "", "seed-heavy-test")

	if err != nil {
		t.Fatalf("new workflow retrier: %v", err)
	}
	if closeRetrier != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := retrier.(*workflows.DisabledWorkflowRetrier); !ok {
		t.Fatalf("expected disabled workflow retrier, got %T", retrier)
	}
}

func TestNewWorkflowRetrierUsesTemporalAndSQLStoreWithDatabaseURL(t *testing.T) {
	retrier, closeRetrier, err := newWorkflowRetrier(
		&mainRecordingTemporalClient{},
		"postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable",
		"seed-live-retry-test",
	)
	if closeRetrier != nil {
		defer func() {
			if err := closeRetrier(); err != nil {
				t.Fatalf("close workflow retrier: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new workflow retrier: %v", err)
	}
	if _, ok := retrier.(*workflows.TemporalWorkflowRetrier); !ok {
		t.Fatalf("expected temporal workflow retrier, got %T", retrier)
	}
	if taskQueue := reflect.ValueOf(retrier).Elem().FieldByName("taskQueue").String(); taskQueue != "seed-live-retry-test" {
		t.Fatalf("expected seed retry task queue to follow configured seed queue, got %q", taskQueue)
	}
	if closeRetrier == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewSeedSegmentRetrierUsesDisabledRetrierWithoutDatabaseURL(t *testing.T) {
	retrier, closeRetrier, err := newSeedSegmentRetrier(&mainRecordingTemporalClient{}, "", "seed-heavy-test")

	if err != nil {
		t.Fatalf("new seed segment retrier: %v", err)
	}
	if closeRetrier != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := retrier.(*workflows.DisabledSeedSegmentRetrier); !ok {
		t.Fatalf("expected disabled seed segment retrier, got %T", retrier)
	}
}

func TestNewSeedSegmentRetrierUsesSQLRetrierWithDatabaseURL(t *testing.T) {
	retrier, closeRetrier, err := newSeedSegmentRetrier(
		&mainRecordingTemporalClient{},
		"postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable",
		"seed-segment-retry-test",
	)
	if closeRetrier != nil {
		defer func() {
			if err := closeRetrier(); err != nil {
				t.Fatalf("close seed segment retrier: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new seed segment retrier: %v", err)
	}
	if _, ok := retrier.(*workflows.SQLSeedSegmentRetrier); !ok {
		t.Fatalf("expected SQL seed segment retrier, got %T", retrier)
	}
	if taskQueue := reflect.ValueOf(retrier).Elem().FieldByName("taskQueue").String(); taskQueue != "seed-segment-retry-test" {
		t.Fatalf("expected segment retry queue to follow configured seed queue, got %q", taskQueue)
	}
	if closeRetrier == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewSeedSegmentRetrierUsesDisabledRetrierWithoutTemporal(t *testing.T) {
	retrier, closeRetrier, err := newSeedSegmentRetrier(
		nil,
		"postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable",
		"seed-heavy-test",
	)

	if err != nil {
		t.Fatalf("new seed segment retrier: %v", err)
	}
	if closeRetrier != nil {
		t.Fatal("expected no database connection without Temporal")
	}
	if _, ok := retrier.(*workflows.DisabledSeedSegmentRetrier); !ok {
		t.Fatalf("expected disabled seed segment retrier, got %T", retrier)
	}
}

func TestNewWriterAdmissionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newWriterAdmissionStore("")

	if err != nil {
		t.Fatalf("new writer admission store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil admission store without database URL, got %T", store)
	}
}

func TestNewWriterAdmissionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newWriterAdmissionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close writer admission store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new writer admission store: %v", err)
	}
	if _, ok := store.(*workflows.SQLWriterAdmissionStore); !ok {
		t.Fatalf("expected SQL writer admission store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewDraftAdoptionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newDraftAdoptionStore("")

	if err != nil {
		t.Fatalf("new draft adoption store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil draft adoption store without database URL, got %T", store)
	}
}

func TestNewDraftAdoptionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newDraftAdoptionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close draft adoption store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new draft adoption store: %v", err)
	}
	if _, ok := store.(*workflows.SQLDraftAdoptionStore); !ok {
		t.Fatalf("expected SQL draft adoption store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewDraftReviewStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newDraftReviewStore("")

	if err != nil {
		t.Fatalf("new draft review store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*workflows.DisabledDraftReviewStore); !ok {
		t.Fatalf("expected disabled draft review store without database URL, got %T", store)
	}
}

func TestNewDraftReviewStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newDraftReviewStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close draft review store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new draft review store: %v", err)
	}
	if _, ok := store.(*workflows.SQLDraftReviewStore); !ok {
		t.Fatalf("expected SQL draft review store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewDraftReviewRuntimeStoresFailClosedWithoutDatabaseURL(t *testing.T) {
	runtimeStore, issueStore, closeStore, err := newDraftReviewRuntimeStores("")
	if err != nil {
		t.Fatalf("new draft review runtime stores: %v", err)
	}
	if runtimeStore != nil || issueStore != nil || closeStore != nil {
		t.Fatalf("expected unconfigured runtime stores, got runtime=%T issue=%T close=%v", runtimeStore, issueStore, closeStore != nil)
	}
}

func TestNewDraftReviewRuntimeStoresUseSharedSQLBackend(t *testing.T) {
	runtimeStore, issueStore, closeStore, err := newDraftReviewRuntimeStores("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close draft review runtime stores: %v", err)
			}
		}()
	}
	if err != nil {
		t.Fatalf("new draft review runtime stores: %v", err)
	}
	if runtimeStore == nil {
		t.Fatal("expected SQL draft review runtime store")
	}
	if _, ok := issueStore.(*workflows.SQLDraftReviewIssueStore); !ok {
		t.Fatalf("expected SQL draft review issue store, got %T", issueStore)
	}
	if closeStore == nil {
		t.Fatal("expected shared SQL close function")
	}
}

func TestNewSeedAdmissionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newSeedAdmissionStore("")

	if err != nil {
		t.Fatalf("new seed admission store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil seed admission store without database URL, got %T", store)
	}
}

func TestNewSeedAdmissionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newSeedAdmissionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close seed admission store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new seed admission store: %v", err)
	}
	if _, ok := store.(*workflows.SQLSeedAdmissionStore); !ok {
		t.Fatalf("expected SQL seed admission store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewLLMResolverUsesDisabledResolverWithoutDatabaseURL(t *testing.T) {
	resolver, closeResolver, err := newLLMResolver("")

	if err != nil {
		t.Fatalf("new llm resolver: %v", err)
	}
	if closeResolver != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := resolver.(*llm.StaticResolver); !ok {
		t.Fatalf("expected static fail-closed resolver, got %T", resolver)
	}
}

func TestNewLLMResolverUsesSQLResolverWithDatabaseURL(t *testing.T) {
	resolver, closeResolver, err := newLLMResolver("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeResolver != nil {
		defer func() {
			if err := closeResolver(); err != nil {
				t.Fatalf("close llm resolver: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new llm resolver: %v", err)
	}
	if _, ok := resolver.(*llm.SQLResolver); !ok {
		t.Fatalf("expected SQL resolver, got %T", resolver)
	}
	if closeResolver == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewLLMBindingStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newLLMBindingStore("")

	if err != nil {
		t.Fatalf("new llm binding store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(llm.DisabledBindingStore); !ok {
		t.Fatalf("expected disabled binding store, got %T", store)
	}
}

func TestNewLLMBindingStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newLLMBindingStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close llm binding store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new llm binding store: %v", err)
	}
	if _, ok := store.(*llm.SQLBindingStore); !ok {
		t.Fatalf("expected SQL binding store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewLLMCatalogReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newLLMCatalogReader("")

	if err != nil {
		t.Fatalf("new llm catalog reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(llm.DisabledCatalogReader); !ok {
		t.Fatalf("expected disabled catalog reader, got %T", reader)
	}
}

func TestNewLLMCatalogReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newLLMCatalogReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close llm catalog reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new llm catalog reader: %v", err)
	}
	if _, ok := reader.(*llm.SQLCatalogReader); !ok {
		t.Fatalf("expected SQL catalog reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewLLMSettingsReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newLLMSettingsReader("")

	if err != nil {
		t.Fatalf("new llm settings reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(llm.DisabledSettingsReader); !ok {
		t.Fatalf("expected disabled settings reader, got %T", reader)
	}
}

func TestNewLLMSettingsReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newLLMSettingsReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close llm settings reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new llm settings reader: %v", err)
	}
	if _, ok := reader.(*llm.SQLSettingsReader); !ok {
		t.Fatalf("expected SQL settings reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewSourceFileStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "")
	store, closeStore, err := newSourceFileStore("")

	if err != nil {
		t.Fatalf("new source file store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(sourcefiles.DisabledStore); !ok {
		t.Fatalf("expected disabled source file store, got %T", store)
	}
}

func TestNewSourceFileStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "")
	store, closeStore, err := newSourceFileStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close source file store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new source file store: %v", err)
	}
	if _, ok := store.(*sourcefiles.SQLStore); !ok {
		t.Fatalf("expected SQL source file store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	bundle, closeReader, err := newAssetReaderBundle("")

	if err != nil {
		t.Fatalf("new asset reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := bundle.Reader.(assets.DisabledReader); !ok {
		t.Fatalf("expected disabled asset reader, got %T", bundle.Reader)
	}
	if bundle.QueryEmbeddingResolver != nil || bundle.SearchIndexChecker != nil {
		t.Fatalf("expected nil search capability deps without database URL, got %#v", bundle)
	}
}

func TestNewAssetReaderUsesPublicSearchReaderWithDatabaseURL(t *testing.T) {
	bundle, closeReader, err := newAssetReaderBundle("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close asset reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset reader: %v", err)
	}
	if _, ok := bundle.Reader.(*assets.PublicSearchReader); !ok {
		t.Fatalf("expected public search asset reader, got %T", bundle.Reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewArchiveMemoryReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newArchiveMemoryReader("")

	if err != nil {
		t.Fatalf("new archive memory reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(assets.DisabledArchiveMemoryReader); !ok {
		t.Fatalf("expected disabled archive memory reader, got %T", reader)
	}
}

func TestNewArchiveMemoryReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newArchiveMemoryReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close archive memory reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new archive memory reader: %v", err)
	}
	if _, ok := reader.(*assets.SQLArchiveMemoryReader); !ok {
		t.Fatalf("expected SQL archive memory reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewArchiveMemoryReviewStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newArchiveMemoryReviewStore("")

	if err != nil {
		t.Fatalf("new archive memory review store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(assets.DisabledArchiveMemoryReviewStore); !ok {
		t.Fatalf("expected disabled archive memory review store, got %T", store)
	}
}

func TestNewArchiveMemoryReviewStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newArchiveMemoryReviewStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close archive memory review store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new archive memory review store: %v", err)
	}
	if _, ok := store.(*assets.SQLArchiveMemoryReviewStore); !ok {
		t.Fatalf("expected SQL archive memory review store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetAdoptionStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetAdoptionStore("")

	if err != nil {
		t.Fatalf("new asset adoption store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(assets.DisabledAdoptionStore); !ok {
		t.Fatalf("expected disabled asset adoption store, got %T", store)
	}
}

func TestNewAssetAdoptionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetAdoptionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close asset adoption store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset adoption store: %v", err)
	}
	if _, ok := store.(*assets.SQLAdoptionStore); !ok {
		t.Fatalf("expected SQL asset adoption store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetMutationStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetMutationStore("")

	if err != nil {
		t.Fatalf("new asset mutation store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(assets.DisabledMutationStore); !ok {
		t.Fatalf("expected disabled asset mutation store, got %T", store)
	}
}

func TestNewAssetMutationStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetMutationStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close asset mutation store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset mutation store: %v", err)
	}
	if _, ok := store.(*assets.SQLMutationStore); !ok {
		t.Fatalf("expected SQL asset mutation store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetBulkActionStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetBulkActionStore("")

	if err != nil {
		t.Fatalf("new asset bulk action store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(assets.DisabledBulkActionStore); !ok {
		t.Fatalf("expected disabled asset bulk action store, got %T", store)
	}
}

func TestNewAssetBulkActionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetBulkActionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close asset bulk action store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset bulk action store: %v", err)
	}
	if _, ok := store.(*assets.SQLBulkActionStore); !ok {
		t.Fatalf("expected SQL asset bulk action store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetIngestionReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newAssetIngestionReader("")

	if err != nil {
		t.Fatalf("new asset ingestion reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*workflows.DisabledAssetIngestionReader); !ok {
		t.Fatalf("expected disabled asset ingestion reader, got %T", reader)
	}
}

func TestNewAssetIngestionReaderUsesWorkflowReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newAssetIngestionReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close asset ingestion reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset ingestion reader: %v", err)
	}
	if _, ok := reader.(*workflows.WorkflowAssetIngestionReader); !ok {
		t.Fatalf("expected workflow asset ingestion reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetIngestionAdmissionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetIngestionAdmissionStore("")

	if err != nil {
		t.Fatalf("new asset ingestion admission store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil asset ingestion admission store without database URL, got %T", store)
	}
}

func TestNewAssetIngestionAdmissionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetIngestionAdmissionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close asset ingestion admission store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset ingestion admission store: %v", err)
	}
	if _, ok := store.(*workflows.SQLAssetIngestionAdmissionStore); !ok {
		t.Fatalf("expected SQL asset ingestion admission store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewAssetReindexAdmissionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetReindexAdmissionStore("")

	if err != nil {
		t.Fatalf("new asset reindex admission store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil asset reindex admission store without database URL, got %T", store)
	}
}

func TestNewAssetReindexAdmissionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newAssetReindexAdmissionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close asset reindex admission store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new asset reindex admission store: %v", err)
	}
	if _, ok := store.(*workflows.SQLAssetReindexAdmissionStore); !ok {
		t.Fatalf("expected SQL asset reindex admission store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewStoryGraphBuildAdmissionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newStoryGraphBuildAdmissionStore("")

	if err != nil {
		t.Fatalf("new story graph admission store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil story graph admission store without database URL, got %T", store)
	}
}

func TestNewStoryGraphBuildAdmissionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newStoryGraphBuildAdmissionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close story graph admission store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new story graph admission store: %v", err)
	}
	if _, ok := store.(*workflows.SQLStoryGraphBuildAdmissionStore); !ok {
		t.Fatalf("expected SQL story graph admission store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewStoryGraphBondGenerationAdmissionStoreUsesNilStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newStoryGraphBondGenerationAdmissionStore("")

	if err != nil {
		t.Fatalf("new story graph bond admission store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if store != nil {
		t.Fatalf("expected nil story graph bond admission store without database URL, got %T", store)
	}
}

func TestNewStoryGraphBondGenerationAdmissionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newStoryGraphBondGenerationAdmissionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close story graph bond admission store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new story graph bond admission store: %v", err)
	}
	if _, ok := store.(*workflows.SQLStoryGraphBondGenerationAdmissionStore); !ok {
		t.Fatalf("expected SQL story graph bond admission store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewStoryGraphReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newStoryGraphReader("")

	if err != nil {
		t.Fatalf("new story graph reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(storygraph.DisabledReader); !ok {
		t.Fatalf("expected disabled story graph reader, got %T", reader)
	}
}

func TestNewStoryGraphReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newStoryGraphReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close story graph reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new story graph reader: %v", err)
	}
	if _, ok := reader.(*storygraph.SQLReader); !ok {
		t.Fatalf("expected SQL story graph reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewStoryGraphCandidateAdoptionStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newStoryGraphCandidateAdoptionStore("")

	if err != nil {
		t.Fatalf("new story graph candidate adoption store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(storygraph.DisabledCandidateAdoptionStore); !ok {
		t.Fatalf("expected disabled story graph candidate adoption store, got %T", store)
	}
}

func TestNewStoryGraphCandidateAdoptionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newStoryGraphCandidateAdoptionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close story graph candidate adoption store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new story graph candidate adoption store: %v", err)
	}
	if _, ok := store.(*storygraph.SQLCandidateAdoptionStore); !ok {
		t.Fatalf("expected SQL story graph candidate adoption store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineSavedPathReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorldlineSavedPathReader("")

	if err != nil {
		t.Fatalf("new worldline saved path reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*worldline.DisabledSavedPathReader); !ok {
		t.Fatalf("expected disabled worldline saved path reader, got %T", reader)
	}
}

func TestNewWorldlineSavedPathReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorldlineSavedPathReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close worldline saved path reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline saved path reader: %v", err)
	}
	if _, ok := reader.(*worldline.SQLSavedPathReader); !ok {
		t.Fatalf("expected SQL worldline saved path reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineSavedPathStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineSavedPathStore("")

	if err != nil {
		t.Fatalf("new worldline saved path store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*worldline.DisabledSavedPathStore); !ok {
		t.Fatalf("expected disabled worldline saved path store, got %T", store)
	}
}

func TestNewWorldlineSavedPathStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineSavedPathStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close worldline saved path store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline saved path store: %v", err)
	}
	if _, ok := store.(*worldline.SQLSavedPathStore); !ok {
		t.Fatalf("expected SQL worldline saved path store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlinePreparationStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlinePreparationStore("")

	if err != nil {
		t.Fatalf("new worldline preparation store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*worldline.DisabledPreparationStore); !ok {
		t.Fatalf("expected disabled worldline preparation store, got %T", store)
	}
}

func TestNewWorldlinePreparationStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlinePreparationStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close worldline preparation store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline preparation store: %v", err)
	}
	if _, ok := store.(*worldline.SQLPreparationStore); !ok {
		t.Fatalf("expected SQL worldline preparation store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineTimelineReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorldlineTimelineReader("")

	if err != nil {
		t.Fatalf("new worldline timeline reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*worldline.DisabledTimelineReader); !ok {
		t.Fatalf("expected disabled worldline timeline reader, got %T", reader)
	}
}

func TestNewWorldlineTimelineReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorldlineTimelineReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close worldline timeline reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline timeline reader: %v", err)
	}
	if _, ok := reader.(*worldline.SQLTimelineReader); !ok {
		t.Fatalf("expected SQL worldline timeline reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineEventReaderUsesDisabledReaderWithoutDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorldlineEventReader("")

	if err != nil {
		t.Fatalf("new worldline event reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(*worldline.DisabledEventReader); !ok {
		t.Fatalf("expected disabled worldline event reader, got %T", reader)
	}
}

func TestNewWorldlineEventReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newWorldlineEventReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeReader != nil {
		defer func() {
			if err := closeReader(); err != nil {
				t.Fatalf("close worldline event reader: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline event reader: %v", err)
	}
	if _, ok := reader.(*worldline.SQLEventReader); !ok {
		t.Fatalf("expected SQL worldline event reader, got %T", reader)
	}
	if closeReader == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineEventAdoptionStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineEventAdoptionStore("")

	if err != nil {
		t.Fatalf("new worldline event adoption store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*worldline.DisabledEventAdoptionStore); !ok {
		t.Fatalf("expected disabled worldline event adoption store, got %T", store)
	}
}

func TestNewWorldlineEventAdoptionStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineEventAdoptionStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close worldline event adoption store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline event adoption store: %v", err)
	}
	if _, ok := store.(*worldline.SQLEventAdoptionStore); !ok {
		t.Fatalf("expected SQL worldline event adoption store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineEventMutationStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineEventMutationStore("")

	if err != nil {
		t.Fatalf("new worldline event mutation store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*worldline.DisabledEventMutationStore); !ok {
		t.Fatalf("expected disabled worldline event mutation store, got %T", store)
	}
}

func TestNewWorldlineEventMutationStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineEventMutationStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close worldline event mutation store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline event mutation store: %v", err)
	}
	if _, ok := store.(*worldline.SQLEventMutationStore); !ok {
		t.Fatalf("expected SQL worldline event mutation store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineVariableStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineVariableStore("")

	if err != nil {
		t.Fatalf("new worldline variable store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*worldline.DisabledVariableStore); !ok {
		t.Fatalf("expected disabled worldline variable store, got %T", store)
	}
}

func TestNewWorldlineVariableStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newWorldlineVariableStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close worldline variable store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline variable store: %v", err)
	}
	if _, ok := store.(*worldline.SQLVariableStore); !ok {
		t.Fatalf("expected SQL worldline variable store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineStepStarterUsesDisabledStarterWithoutDatabaseURL(t *testing.T) {
	starter, closeStarter, err := newWorldlineStepStarter(nil, "", "")

	if err != nil {
		t.Fatalf("new worldline step starter: %v", err)
	}
	if closeStarter != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := starter.(*worldline.DisabledStepStarter); !ok {
		t.Fatalf("expected disabled worldline step starter, got %T", starter)
	}
}

func TestNewWorldlineStepStarterUsesSQLStarterWithDatabaseURL(t *testing.T) {
	starter, closeStarter, err := newWorldlineStepStarter(&mainRecordingTemporalClient{}, "postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable", "worldline-custom")
	if closeStarter != nil {
		defer func() {
			if err := closeStarter(); err != nil {
				t.Fatalf("close worldline step starter: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new worldline step starter: %v", err)
	}
	if _, ok := starter.(*worldline.SQLStepStarter); !ok {
		t.Fatalf("expected SQL worldline step starter, got %T", starter)
	}
	if closeStarter == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewWorldlineStepStarterFailsClosedWithoutTemporalClient(t *testing.T) {
	starter, closeStarter, err := newWorldlineStepStarter(nil, "postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable", "")
	if err != nil {
		t.Fatalf("new worldline step starter: %v", err)
	}
	if closeStarter != nil {
		t.Fatal("disabled starter must not retain a database handle")
	}
	if _, ok := starter.(*worldline.DisabledStepStarter); !ok {
		t.Fatalf("expected disabled worldline step starter, got %T", starter)
	}
}

func TestNewWorldlineAutoEvolutionStarterFailsClosedWithoutCompleteRuntime(t *testing.T) {
	for _, tt := range []struct {
		name     string
		client   worldline.TemporalWorkflowClient
		database string
	}{
		{name: "missing database", client: &mainRecordingTemporalClient{}},
		{name: "missing temporal", database: "postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			starter, closeStarter, err := newWorldlineAutoEvolutionStarter(tt.client, tt.database, "")
			if err != nil {
				t.Fatalf("new worldline auto-evolution starter: %v", err)
			}
			if closeStarter != nil {
				t.Fatal("disabled auto-evolution starter must not retain a database handle")
			}
			if _, ok := starter.(*worldline.DisabledAutoEvolutionStarter); !ok {
				t.Fatalf("expected disabled auto-evolution starter, got %T", starter)
			}
		})
	}
}

func TestNewWorldlineAutoEvolutionStarterUsesSQLRuntime(t *testing.T) {
	starter, closeStarter, err := newWorldlineAutoEvolutionStarter(
		&mainRecordingTemporalClient{},
		"postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable",
		"worldline-custom",
	)
	if closeStarter != nil {
		defer func() {
			if err := closeStarter(); err != nil {
				t.Fatalf("close worldline auto-evolution starter: %v", err)
			}
		}()
	}
	if err != nil {
		t.Fatalf("new worldline auto-evolution starter: %v", err)
	}
	if _, ok := starter.(*worldline.SQLAutoEvolutionStarter); !ok {
		t.Fatalf("expected SQL auto-evolution starter, got %T", starter)
	}
	if closeStarter == nil {
		t.Fatal("expected close function for configured auto-evolution runtime")
	}
}

func TestNewWorldlinePreparationStarterFailsClosedWithoutCompleteRuntime(t *testing.T) {
	for _, tt := range []struct {
		name     string
		client   worldline.TemporalWorkflowClient
		database string
	}{
		{name: "missing database", client: &mainRecordingTemporalClient{}},
		{name: "missing temporal", database: "postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			starter, closeStarter, err := newWorldlinePreparationStarter(tt.client, tt.database, "")
			if err != nil {
				t.Fatalf("new worldline preparation starter: %v", err)
			}
			if closeStarter != nil {
				t.Fatal("disabled preparation starter must not retain a database handle")
			}
			if _, ok := starter.(*worldline.DisabledPreparationStarter); !ok {
				t.Fatalf("expected disabled preparation starter, got %T", starter)
			}
		})
	}
}

func TestNewWorldlinePreparationStarterUsesSQLRuntime(t *testing.T) {
	starter, closeStarter, err := newWorldlinePreparationStarter(
		&mainRecordingTemporalClient{},
		"postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable",
		"worldline-custom",
	)
	if closeStarter != nil {
		defer func() {
			if err := closeStarter(); err != nil {
				t.Fatalf("close worldline preparation starter: %v", err)
			}
		}()
	}
	if err != nil {
		t.Fatalf("new worldline preparation starter: %v", err)
	}
	if _, ok := starter.(*worldline.SQLPreparationStarter); !ok {
		t.Fatalf("expected SQL preparation starter, got %T", starter)
	}
	if closeStarter == nil {
		t.Fatal("expected close function for configured preparation runtime")
	}
}

func TestNewCharacterConsoleStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newCharacterConsoleStore("")

	if err != nil {
		t.Fatalf("new character console store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(*characterconsole.DisabledStore); !ok {
		t.Fatalf("expected disabled character console store, got %T", store)
	}
}

func TestNewCharacterConsoleStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newCharacterConsoleStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close character console store: %v", err)
			}
		}()
	}

	if err != nil {
		t.Fatalf("new character console store: %v", err)
	}
	if _, ok := store.(*characterconsole.SQLStore); !ok {
		t.Fatalf("expected SQL character console store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewCharacterProposalStoreUsesDisabledStoreWithoutDatabaseURL(t *testing.T) {
	store, closeStore, err := newCharacterProposalStore("")
	if err != nil {
		t.Fatalf("new character proposal store: %v", err)
	}
	if closeStore != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := store.(characterconsole.DisabledProposalStore); !ok {
		t.Fatalf("expected disabled character proposal store, got %T", store)
	}
}

func TestNewCharacterProposalStoreUsesSQLStoreWithDatabaseURL(t *testing.T) {
	store, closeStore, err := newCharacterProposalStore("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
	if closeStore != nil {
		defer func() {
			if err := closeStore(); err != nil {
				t.Fatalf("close character proposal store: %v", err)
			}
		}()
	}
	if err != nil {
		t.Fatalf("new character proposal store: %v", err)
	}
	if _, ok := store.(*characterconsole.SQLProposalStore); !ok {
		t.Fatalf("expected SQL character proposal store, got %T", store)
	}
	if closeStore == nil {
		t.Fatal("expected close function with database URL")
	}
}

func TestNewObjectVerifierFromEnvDisabledWithoutEndpoint(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "")

	verifier, err := newObjectVerifierFromEnv()

	if err != nil {
		t.Fatalf("new object verifier: %v", err)
	}
	if verifier != nil {
		t.Fatalf("expected no verifier without object storage endpoint, got %T", verifier)
	}
}

func TestNewObjectVerifierFromEnvRejectsPartialConfig(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "127.0.0.1:9000")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "mirofish")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "secret")

	_, err := newObjectVerifierFromEnv()

	if code := sourcefiles.ErrorCode(err); code != "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED, got %s (%v)", code, err)
	}
}

func TestNewObjectVerifierFromEnvCreatesMinIOVerifier(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "127.0.0.1:9000")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "mirofish-uploads")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "mirofish")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "secret")
	t.Setenv("MIROFISH_OBJECT_STORAGE_USE_SSL", "false")

	verifier, err := newObjectVerifierFromEnv()

	if err != nil {
		t.Fatalf("new object verifier: %v", err)
	}
	if verifier == nil {
		t.Fatal("expected configured object verifier")
	}
}

func TestNewObjectWriterFromEnvDisabledWithoutEndpoint(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "")

	writer, err := newObjectWriterFromEnv()

	if err != nil {
		t.Fatalf("new object writer: %v", err)
	}
	if writer != nil {
		t.Fatalf("expected no writer without object storage endpoint, got %T", writer)
	}
}

func TestNewObjectWriterFromEnvRejectsPartialConfig(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "127.0.0.1:9000")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "mirofish")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "secret")

	_, err := newObjectWriterFromEnv()

	if code := sourcefiles.ErrorCode(err); code != "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED, got %s (%v)", code, err)
	}
}

func TestNewObjectWriterFromEnvCreatesMinIOWriter(t *testing.T) {
	t.Setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "127.0.0.1:9000")
	t.Setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "mirofish-uploads")
	t.Setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "mirofish")
	t.Setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "secret")
	t.Setenv("MIROFISH_OBJECT_STORAGE_USE_SSL", "false")

	writer, err := newObjectWriterFromEnv()

	if err != nil {
		t.Fatalf("new object writer: %v", err)
	}
	if writer == nil {
		t.Fatal("expected configured object writer")
	}
}

type mainRecordingTemporalClient struct{}

func (c *mainRecordingTemporalClient) ExecuteWorkflow(context.Context, client.StartWorkflowOptions, any, ...any) (client.WorkflowRun, error) {
	return nil, nil
}

func (c *mainRecordingTemporalClient) CancelWorkflow(context.Context, string, string) error {
	return nil
}

func TestNewWriterPlanningStarterRequiresTemporalAndDatabase(t *testing.T) {
	starter, closeStarter, err := newWriterPlanningStarter(nil, "postgres://app:private@127.0.0.1:1/app?sslmode=disable", "writer-planning-test")
	if err != nil || starter != nil || closeStarter != nil {
		t.Fatalf("planning starter without Temporal must be disabled: starter=%T close=%v err=%v", starter, closeStarter != nil, err)
	}
	starter, closeStarter, err = newWriterPlanningStarter(&mainRecordingTemporalClient{}, "", "writer-planning-test")
	if err != nil || starter != nil || closeStarter != nil {
		t.Fatalf("planning starter without database must be disabled: starter=%T close=%v err=%v", starter, closeStarter != nil, err)
	}
	starter, closeStarter, err = newWriterPlanningStarter(
		&mainRecordingTemporalClient{},
		"postgres://app:private@127.0.0.1:1/app?sslmode=disable",
		"writer-planning-test",
	)
	if err != nil || closeStarter == nil {
		t.Fatalf("configured planning starter was not constructed: starter=%T close=%v err=%v", starter, closeStarter != nil, err)
	}
	defer func() { _ = closeStarter() }()
	if _, ok := starter.(*writerplanning.TemporalStarter); !ok {
		t.Fatalf("expected Temporal writer planning starter, got %T", starter)
	}
}
