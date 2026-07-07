package main

import (
	"context"
	"testing"

	"go.temporal.io/sdk/client"

	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/httpapi"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"
)

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

func TestAuthSessionSecretEnvIsCarriedIntoHTTPConfig(t *testing.T) {
	t.Setenv("MIROFISH_AUTH_SESSION_SECRET", "session-secret")

	config := withSessionAuthSecret(httpapi.Config{})

	if config.SessionAuthSecret != "session-secret" {
		t.Fatalf("expected session secret in HTTP config, got %q", config.SessionAuthSecret)
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
	reader, closeReader, err := newAssetReader("")

	if err != nil {
		t.Fatalf("new asset reader: %v", err)
	}
	if closeReader != nil {
		t.Fatal("expected no close function without database URL")
	}
	if _, ok := reader.(assets.DisabledReader); !ok {
		t.Fatalf("expected disabled asset reader, got %T", reader)
	}
}

func TestNewAssetReaderUsesSQLReaderWithDatabaseURL(t *testing.T) {
	reader, closeReader, err := newAssetReader("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
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
	if _, ok := reader.(*assets.SQLReader); !ok {
		t.Fatalf("expected SQL asset reader, got %T", reader)
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
	starter, closeStarter, err := newWorldlineStepStarter("")

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
	starter, closeStarter, err := newWorldlineStepStarter("postgres://mirofish:secret@127.0.0.1:5432/mirofish?sslmode=disable")
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
