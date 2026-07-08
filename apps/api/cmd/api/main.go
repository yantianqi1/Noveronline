package main

import (
	"context"
	"database/sql"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/httpapi"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/traces"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"

	_ "github.com/jackc/pgx/v5/stdlib"
	"go.temporal.io/sdk/client"
)

func main() {
	addr := os.Getenv("MIROFISH_API_ADDR")
	if addr == "" {
		addr = ":8080"
	}
	databaseURL := os.Getenv("DATABASE_URL")

	authReader, closeAuthReader, err := newAuthReader(databaseURL)
	if err != nil {
		log.Fatalf("configure auth reader: %v", err)
	}
	if closeAuthReader != nil {
		defer func() {
			if err := closeAuthReader(); err != nil {
				log.Printf("close auth reader: %v", err)
			}
		}()
	}
	authSessionStore, closeAuthSessionStore, err := newAuthSessionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure auth session store: %v", err)
	}
	if closeAuthSessionStore != nil {
		defer func() {
			if err := closeAuthSessionStore(); err != nil {
				log.Printf("close auth session store: %v", err)
			}
		}()
	}

	writerStarter := workflows.WriterStarter(workflows.NewLocalWriterStarter())
	writerCanceller := workflows.WriterCanceller(workflows.NewDisabledWriterCanceller())
	helloStarter := workflows.AgentHelloStarter(workflows.NewDisabledHelloAgentStarter())
	seedStarter := workflows.SeedRunStarter(workflows.NewDisabledSeedRunStarter())
	assetIngestionStarter := workflows.AssetIngestionStarter(workflows.NewDisabledAssetIngestionStarter())
	styleExtractionStarter := workflows.StyleExtractionStarter(workflows.NewDisabledStyleExtractionStarter())
	assetReindexStarter := workflows.AssetReindexStarter(workflows.NewDisabledAssetReindexStarter())
	storyGraphBuildStarter := workflows.StoryGraphBuildStarter(workflows.NewDisabledStoryGraphBuildStarter())
	storyGraphBondGenerationStarter := workflows.StoryGraphBondGenerationStarter(workflows.NewDisabledStoryGraphBondGenerationStarter())
	writerAdmissionStore, closeWriterAdmission, err := newWriterAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure writer admission store: %v", err)
	}
	if closeWriterAdmission != nil {
		defer func() {
			if err := closeWriterAdmission(); err != nil {
				log.Printf("close writer admission store: %v", err)
			}
		}()
	}
	draftAdoptionStore, closeDraftAdoption, err := newDraftAdoptionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure draft adoption store: %v", err)
	}
	if closeDraftAdoption != nil {
		defer func() {
			if err := closeDraftAdoption(); err != nil {
				log.Printf("close draft adoption store: %v", err)
			}
		}()
	}
	draftReviewStore, closeDraftReview, err := newDraftReviewStore(databaseURL)
	if err != nil {
		log.Fatalf("configure draft review store: %v", err)
	}
	if closeDraftReview != nil {
		defer func() {
			if err := closeDraftReview(); err != nil {
				log.Printf("close draft review store: %v", err)
			}
		}()
	}
	seedAdmissionStore, closeSeedAdmission, err := newSeedAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure seed admission store: %v", err)
	}
	if closeSeedAdmission != nil {
		defer func() {
			if err := closeSeedAdmission(); err != nil {
				log.Printf("close seed admission store: %v", err)
			}
		}()
	}
	assetIngestionAdmissionStore, closeAssetIngestionAdmission, err := newAssetIngestionAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure asset ingestion admission store: %v", err)
	}
	if closeAssetIngestionAdmission != nil {
		defer func() {
			if err := closeAssetIngestionAdmission(); err != nil {
				log.Printf("close asset ingestion admission store: %v", err)
			}
		}()
	}
	styleExtractionAdmissionStore, closeStyleExtractionAdmission, err := newStyleExtractionAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure style extraction admission store: %v", err)
	}
	if closeStyleExtractionAdmission != nil {
		defer func() {
			if err := closeStyleExtractionAdmission(); err != nil {
				log.Printf("close style extraction admission store: %v", err)
			}
		}()
	}
	assetReindexAdmissionStore, closeAssetReindexAdmission, err := newAssetReindexAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure asset reindex admission store: %v", err)
	}
	if closeAssetReindexAdmission != nil {
		defer func() {
			if err := closeAssetReindexAdmission(); err != nil {
				log.Printf("close asset reindex admission store: %v", err)
			}
		}()
	}
	storyGraphAdmissionStore, closeStoryGraphAdmission, err := newStoryGraphBuildAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure story graph admission store: %v", err)
	}
	if closeStoryGraphAdmission != nil {
		defer func() {
			if err := closeStoryGraphAdmission(); err != nil {
				log.Printf("close story graph admission store: %v", err)
			}
		}()
	}
	storyGraphBondAdmissionStore, closeStoryGraphBondAdmission, err := newStoryGraphBondGenerationAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure story graph bond admission store: %v", err)
	}
	if closeStoryGraphBondAdmission != nil {
		defer func() {
			if err := closeStoryGraphBondAdmission(); err != nil {
				log.Printf("close story graph bond admission store: %v", err)
			}
		}()
	}
	var closeTemporal func()
	var temporalWorkflowClient workflows.TemporalWorkflowClient
	if temporalAddress := os.Getenv("TEMPORAL_ADDRESS"); temporalAddress != "" {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		temporalClient, err := client.DialContext(ctx, client.Options{
			HostPort:  temporalAddress,
			Namespace: temporalNamespace(),
		})
		cancel()
		if err != nil {
			log.Fatalf("connect temporal workflow backend: %v", err)
		}
		writerStarter, helloStarter, seedStarter, assetIngestionStarter, styleExtractionStarter, assetReindexStarter, storyGraphBuildStarter, storyGraphBondGenerationStarter = newTemporalStartersWithAdmission(
			temporalClient,
			os.Getenv("WRITER_TASK_QUEUE"),
			os.Getenv("HELLO_AGENT_TASK_QUEUE"),
			os.Getenv("SEED_TASK_QUEUE"),
			os.Getenv("ASSET_TASK_QUEUE"),
			os.Getenv("GRAPH_TASK_QUEUE"),
			writerAdmissionStore,
			seedAdmissionStore,
			assetIngestionAdmissionStore,
			styleExtractionAdmissionStore,
			assetReindexAdmissionStore,
			storyGraphAdmissionStore,
			storyGraphBondAdmissionStore,
		)
		if canceller, ok := writerStarter.(workflows.WriterCanceller); ok {
			writerCanceller = canceller
		}
		temporalWorkflowClient = temporalClient
		closeTemporal = temporalClient.Close
	}
	if closeTemporal != nil {
		defer closeTemporal()
	}

	writerReader, closeWriterReader, err := newWriterReader(databaseURL)
	if err != nil {
		log.Fatalf("configure writer reader: %v", err)
	}
	if closeWriterReader != nil {
		defer func() {
			if err := closeWriterReader(); err != nil {
				log.Printf("close writer reader: %v", err)
			}
		}()
	}
	manuscriptReader, closeManuscriptReader, err := newManuscriptReader(databaseURL)
	if err != nil {
		log.Fatalf("configure manuscript reader: %v", err)
	}
	if closeManuscriptReader != nil {
		defer func() {
			if err := closeManuscriptReader(); err != nil {
				log.Printf("close manuscript reader: %v", err)
			}
		}()
	}
	writerEventReader, closeWriterEvents, err := newWriterEventReader(databaseURL)
	if err != nil {
		log.Fatalf("configure writer event reader: %v", err)
	}
	if closeWriterEvents != nil {
		defer func() {
			if err := closeWriterEvents(); err != nil {
				log.Printf("close writer event reader: %v", err)
			}
		}()
	}
	workflowReader, closeWorkflowReader, err := newWorkflowReader(databaseURL)
	if err != nil {
		log.Fatalf("configure workflow reader: %v", err)
	}
	if closeWorkflowReader != nil {
		defer func() {
			if err := closeWorkflowReader(); err != nil {
				log.Printf("close workflow reader: %v", err)
			}
		}()
	}
	workflowEventReader, closeWorkflowEvents, err := newWorkflowEventReader(databaseURL)
	if err != nil {
		log.Fatalf("configure workflow event reader: %v", err)
	}
	if closeWorkflowEvents != nil {
		defer func() {
			if err := closeWorkflowEvents(); err != nil {
				log.Printf("close workflow event reader: %v", err)
			}
		}()
	}
	seedRunReader, closeSeedRunReader, err := newSeedRunReader(databaseURL)
	if err != nil {
		log.Fatalf("configure seed run reader: %v", err)
	}
	if closeSeedRunReader != nil {
		defer func() {
			if err := closeSeedRunReader(); err != nil {
				log.Printf("close seed run reader: %v", err)
			}
		}()
	}
	projectReadinessReader, closeProjectReadinessReader, err := newProjectReadinessReader(databaseURL)
	if err != nil {
		log.Fatalf("configure project readiness reader: %v", err)
	}
	if closeProjectReadinessReader != nil {
		defer func() {
			if err := closeProjectReadinessReader(); err != nil {
				log.Printf("close project readiness reader: %v", err)
			}
		}()
	}
	projectOverviewReader, closeProjectOverviewReader, err := newProjectOverviewReader(databaseURL)
	if err != nil {
		log.Fatalf("configure project overview reader: %v", err)
	}
	if closeProjectOverviewReader != nil {
		defer func() {
			if err := closeProjectOverviewReader(); err != nil {
				log.Printf("close project overview reader: %v", err)
			}
		}()
	}
	workflowCanceller, closeWorkflowCanceller, err := newWorkflowCanceller(temporalWorkflowClient, databaseURL)
	if err != nil {
		log.Fatalf("configure workflow canceller: %v", err)
	}
	if closeWorkflowCanceller != nil {
		defer func() {
			if err := closeWorkflowCanceller(); err != nil {
				log.Printf("close workflow canceller: %v", err)
			}
		}()
	}
	workflowRetrier := workflows.NewDisabledWorkflowRetrier()

	llmResolver, closeLLMResolver, err := newLLMResolver(databaseURL)
	if err != nil {
		log.Fatalf("configure LLM resolver: %v", err)
	}
	if closeLLMResolver != nil {
		defer func() {
			if err := closeLLMResolver(); err != nil {
				log.Printf("close LLM resolver: %v", err)
			}
		}()
	}
	llmBindingStore, closeLLMBindingStore, err := newLLMBindingStore(databaseURL)
	if err != nil {
		log.Fatalf("configure LLM binding store: %v", err)
	}
	if closeLLMBindingStore != nil {
		defer func() {
			if err := closeLLMBindingStore(); err != nil {
				log.Printf("close LLM binding store: %v", err)
			}
		}()
	}
	llmCatalogReader, closeLLMCatalog, err := newLLMCatalogReader(databaseURL)
	if err != nil {
		log.Fatalf("configure LLM catalog reader: %v", err)
	}
	if closeLLMCatalog != nil {
		defer func() {
			if err := closeLLMCatalog(); err != nil {
				log.Printf("close LLM catalog reader: %v", err)
			}
		}()
	}
	llmChannelStore, closeLLMChannels, err := newLLMChannelStore(databaseURL, os.Getenv("LLM_CREDENTIAL_ENCRYPTION_KEY"))
	if err != nil {
		log.Fatalf("configure LLM channel store: %v", err)
	}
	if closeLLMChannels != nil {
		defer func() {
			if err := closeLLMChannels(); err != nil {
				log.Printf("close LLM channel store: %v", err)
			}
		}()
	}
	llmModelSyncer, closeLLMModelSyncer, err := newLLMModelSyncer(databaseURL, os.Getenv("LLM_CREDENTIAL_ENCRYPTION_KEY"))
	if err != nil {
		log.Fatalf("configure LLM model syncer: %v", err)
	}
	if closeLLMModelSyncer != nil {
		defer func() {
			if err := closeLLMModelSyncer(); err != nil {
				log.Printf("close LLM model syncer: %v", err)
			}
		}()
	}

	llmSettingsReader, closeLLMSettings, err := newLLMSettingsReader(databaseURL)
	if err != nil {
		log.Fatalf("configure LLM settings reader: %v", err)
	}
	if closeLLMSettings != nil {
		defer func() {
			if err := closeLLMSettings(); err != nil {
				log.Printf("close LLM settings reader: %v", err)
			}
		}()
	}

	llmTelemetryReader, closeLLMTelemetry, err := newLLMTelemetryReader(databaseURL)
	if err != nil {
		log.Fatalf("configure LLM telemetry reader: %v", err)
	}
	if closeLLMTelemetry != nil {
		defer func() {
			if err := closeLLMTelemetry(); err != nil {
				log.Printf("close LLM telemetry reader: %v", err)
			}
		}()
	}
	traceReader, closeTraceReader, err := newTraceReader(databaseURL)
	if err != nil {
		log.Fatalf("configure agent trace reader: %v", err)
	}
	if closeTraceReader != nil {
		defer func() {
			if err := closeTraceReader(); err != nil {
				log.Printf("close agent trace reader: %v", err)
			}
		}()
	}
	traceExportAuditor, closeTraceExportAuditor, err := newTraceExportAuditor(databaseURL)
	if err != nil {
		log.Fatalf("configure agent trace export auditor: %v", err)
	}
	if closeTraceExportAuditor != nil {
		defer func() {
			if err := closeTraceExportAuditor(); err != nil {
				log.Printf("close agent trace export auditor: %v", err)
			}
		}()
	}
	sourceFileStore, closeSourceFiles, err := newSourceFileStore(databaseURL)
	if err != nil {
		log.Fatalf("configure source file store: %v", err)
	}
	if closeSourceFiles != nil {
		defer func() {
			if err := closeSourceFiles(); err != nil {
				log.Printf("close source file store: %v", err)
			}
		}()
	}
	sourceFileObjectWriter, err := newObjectWriterFromEnv()
	if err != nil {
		log.Fatalf("configure source file object writer: %v", err)
	}
	assetReader, closeAssets, err := newAssetReader(databaseURL)
	if err != nil {
		log.Fatalf("configure asset reader: %v", err)
	}
	if closeAssets != nil {
		defer func() {
			if err := closeAssets(); err != nil {
				log.Printf("close asset reader: %v", err)
			}
		}()
	}
	archiveMemoryReader, closeArchiveMemories, err := newArchiveMemoryReader(databaseURL)
	if err != nil {
		log.Fatalf("configure archive memory reader: %v", err)
	}
	if closeArchiveMemories != nil {
		defer func() {
			if err := closeArchiveMemories(); err != nil {
				log.Printf("close archive memory reader: %v", err)
			}
		}()
	}
	archiveMemoryReviewStore, closeArchiveMemoryReview, err := newArchiveMemoryReviewStore(databaseURL)
	if err != nil {
		log.Fatalf("configure archive memory review store: %v", err)
	}
	if closeArchiveMemoryReview != nil {
		defer func() {
			if err := closeArchiveMemoryReview(); err != nil {
				log.Printf("close archive memory review store: %v", err)
			}
		}()
	}
	assetAdoptionStore, closeAssetAdoptions, err := newAssetAdoptionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure asset adoption store: %v", err)
	}
	if closeAssetAdoptions != nil {
		defer func() {
			if err := closeAssetAdoptions(); err != nil {
				log.Printf("close asset adoption store: %v", err)
			}
		}()
	}
	assetMutationStore, closeAssetMutations, err := newAssetMutationStore(databaseURL)
	if err != nil {
		log.Fatalf("configure asset mutation store: %v", err)
	}
	if closeAssetMutations != nil {
		defer func() {
			if err := closeAssetMutations(); err != nil {
				log.Printf("close asset mutation store: %v", err)
			}
		}()
	}
	assetBulkActionStore, closeAssetBulkActions, err := newAssetBulkActionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure asset bulk action store: %v", err)
	}
	if closeAssetBulkActions != nil {
		defer func() {
			if err := closeAssetBulkActions(); err != nil {
				log.Printf("close asset bulk action store: %v", err)
			}
		}()
	}
	assetIngestionReader, closeAssetIngestions, err := newAssetIngestionReader(databaseURL)
	if err != nil {
		log.Fatalf("configure asset ingestion reader: %v", err)
	}
	if closeAssetIngestions != nil {
		defer func() {
			if err := closeAssetIngestions(); err != nil {
				log.Printf("close asset ingestion reader: %v", err)
			}
		}()
	}
	styleExtractionReader, closeStyleExtractions, err := newStyleExtractionReader(databaseURL)
	if err != nil {
		log.Fatalf("configure style extraction reader: %v", err)
	}
	if closeStyleExtractions != nil {
		defer func() {
			if err := closeStyleExtractions(); err != nil {
				log.Printf("close style extraction reader: %v", err)
			}
		}()
	}
	storyGraphReader, closeStoryGraphReader, err := newStoryGraphReader(databaseURL)
	if err != nil {
		log.Fatalf("configure story graph reader: %v", err)
	}
	if closeStoryGraphReader != nil {
		defer func() {
			if err := closeStoryGraphReader(); err != nil {
				log.Printf("close story graph reader: %v", err)
			}
		}()
	}
	worldlineSavedPathReader, closeWorldlineSavedPathReader, err := newWorldlineSavedPathReader(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline saved path reader: %v", err)
	}
	if closeWorldlineSavedPathReader != nil {
		defer func() {
			if err := closeWorldlineSavedPathReader(); err != nil {
				log.Printf("close worldline saved path reader: %v", err)
			}
		}()
	}
	worldlineSavedPathStore, closeWorldlineSavedPathStore, err := newWorldlineSavedPathStore(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline saved path store: %v", err)
	}
	if closeWorldlineSavedPathStore != nil {
		defer func() {
			if err := closeWorldlineSavedPathStore(); err != nil {
				log.Printf("close worldline saved path store: %v", err)
			}
		}()
	}
	worldlineSessionStarter, worldlineSessionReader, closeWorldlineSessionStore, err := newWorldlineSessionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline session store: %v", err)
	}
	if closeWorldlineSessionStore != nil {
		defer func() {
			if err := closeWorldlineSessionStore(); err != nil {
				log.Printf("close worldline session store: %v", err)
			}
		}()
	}
	worldlineStepStarter, closeWorldlineStepStarter, err := newWorldlineStepStarter(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline step starter: %v", err)
	}
	if closeWorldlineStepStarter != nil {
		defer func() {
			if err := closeWorldlineStepStarter(); err != nil {
				log.Printf("close worldline step starter: %v", err)
			}
		}()
	}
	worldlineTimelineReader, closeWorldlineTimelineReader, err := newWorldlineTimelineReader(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline timeline reader: %v", err)
	}
	if closeWorldlineTimelineReader != nil {
		defer func() {
			if err := closeWorldlineTimelineReader(); err != nil {
				log.Printf("close worldline timeline reader: %v", err)
			}
		}()
	}
	worldlineEventReader, closeWorldlineEventReader, err := newWorldlineEventReader(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline event reader: %v", err)
	}
	if closeWorldlineEventReader != nil {
		defer func() {
			if err := closeWorldlineEventReader(); err != nil {
				log.Printf("close worldline event reader: %v", err)
			}
		}()
	}
	worldlineEventAdoptionStore, closeWorldlineEventAdoptionStore, err := newWorldlineEventAdoptionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline event adoption store: %v", err)
	}
	if closeWorldlineEventAdoptionStore != nil {
		defer func() {
			if err := closeWorldlineEventAdoptionStore(); err != nil {
				log.Printf("close worldline event adoption store: %v", err)
			}
		}()
	}
	worldlineEventMutationStore, closeWorldlineEventMutationStore, err := newWorldlineEventMutationStore(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline event mutation store: %v", err)
	}
	if closeWorldlineEventMutationStore != nil {
		defer func() {
			if err := closeWorldlineEventMutationStore(); err != nil {
				log.Printf("close worldline event mutation store: %v", err)
			}
		}()
	}
	worldlinePreparationStore, closeWorldlinePreparationStore, err := newWorldlinePreparationStore(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline preparation store: %v", err)
	}
	if closeWorldlinePreparationStore != nil {
		defer func() {
			if err := closeWorldlinePreparationStore(); err != nil {
				log.Printf("close worldline preparation store: %v", err)
			}
		}()
	}
	worldlineVariableStore, closeWorldlineVariableStore, err := newWorldlineVariableStore(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline variable store: %v", err)
	}
	if closeWorldlineVariableStore != nil {
		defer func() {
			if err := closeWorldlineVariableStore(); err != nil {
				log.Printf("close worldline variable store: %v", err)
			}
		}()
	}
	characterConsoleStore, closeCharacterConsoleStore, err := newCharacterConsoleStore(databaseURL)
	if err != nil {
		log.Fatalf("configure character console store: %v", err)
	}
	if closeCharacterConsoleStore != nil {
		defer func() {
			if err := closeCharacterConsoleStore(); err != nil {
				log.Printf("close character console store: %v", err)
			}
		}()
	}

	serverConfig := withSessionAuthSecret(httpapi.Config{
		AuthReader:                      authReader,
		AuthSessionStore:                authSessionStore,
		Authorizer:                      auth.NewReaderBackedAuthorizer(authReader),
		WriterStarter:                   writerStarter,
		WriterReader:                    writerReader,
		WriterEventReader:               writerEventReader,
		WriterCanceller:                 writerCanceller,
		DraftAdoptionStore:              draftAdoptionStore,
		DraftReviewStore:                draftReviewStore,
		ManuscriptReader:                manuscriptReader,
		WorkflowReader:                  workflowReader,
		WorkflowEventReader:             workflowEventReader,
		WorkflowCanceller:               workflowCanceller,
		WorkflowRetrier:                 workflowRetrier,
		SeedStarter:                     seedStarter,
		SeedRunReader:                   seedRunReader,
		ProjectOverviewReader:           projectOverviewReader,
		ProjectReadinessReader:          projectReadinessReader,
		AgentHelloStarter:               helloStarter,
		LLMResolver:                     llmResolver,
		LLMBindingStore:                 llmBindingStore,
		LLMCatalogReader:                llmCatalogReader,
		LLMChannelStore:                 llmChannelStore,
		LLMModelSyncer:                  llmModelSyncer,
		LLMSettingsReader:               llmSettingsReader,
		LLMTelemetryReader:              llmTelemetryReader,
		TraceReader:                     traceReader,
		TraceExportAuditor:              traceExportAuditor,
		SourceFileStore:                 sourceFileStore,
		SourceFileObjectWriter:          sourceFileObjectWriter,
		AssetReader:                     assetReader,
		ArchiveMemoryReader:             archiveMemoryReader,
		ArchiveMemoryReviewStore:        archiveMemoryReviewStore,
		AssetAdoptionStore:              assetAdoptionStore,
		AssetMutationStore:              assetMutationStore,
		AssetBulkActionStore:            assetBulkActionStore,
		AssetReindexStarter:             assetReindexStarter,
		AssetIngestionStarter:           assetIngestionStarter,
		AssetIngestionReader:            assetIngestionReader,
		StyleExtractionStarter:          styleExtractionStarter,
		StyleExtractionReader:           styleExtractionReader,
		StoryGraphBuildStarter:          storyGraphBuildStarter,
		StoryGraphBondGenerationStarter: storyGraphBondGenerationStarter,
		StoryGraphReader:                storyGraphReader,
		WorldlineSavedPathReader:        worldlineSavedPathReader,
		WorldlineSavedPathStore:         worldlineSavedPathStore,
		WorldlineSessionStarter:         worldlineSessionStarter,
		WorldlineStepStarter:            worldlineStepStarter,
		WorldlineSessionReader:          worldlineSessionReader,
		WorldlineTimelineReader:         worldlineTimelineReader,
		WorldlineEventReader:            worldlineEventReader,
		WorldlineEventAdoptionStore:     worldlineEventAdoptionStore,
		WorldlineEventMutationStore:     worldlineEventMutationStore,
		WorldlineVariableStore:          worldlineVariableStore,
		WorldlinePreparationStore:       worldlinePreparationStore,
		CharacterConsoleStore:           characterConsoleStore,
	})
	server := httpapi.NewServer(serverConfig)
	log.Printf("mirofish api listening on %s", addr)
	if err := http.ListenAndServe(addr, server); err != nil {
		log.Fatal(err)
	}
}

func withSessionAuthSecret(config httpapi.Config) httpapi.Config {
	config.SessionAuthSecret = strings.TrimSpace(os.Getenv("MIROFISH_AUTH_SESSION_SECRET"))
	return config
}

func temporalNamespace() string {
	namespace := os.Getenv("TEMPORAL_NAMESPACE")
	if namespace == "" {
		return "default"
	}
	return namespace
}

func newAuthReader(databaseURL string) (auth.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return auth.NewDisabledReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return auth.NewSQLReader(auth.SQLReaderConfig{
		Queryer: auth.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newAuthSessionStore(databaseURL string) (auth.SessionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := auth.NewSQLDBQueryer(db)
	return auth.NewSQLSessionStore(auth.SQLSessionStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newTemporalStarters(
	temporalClient workflows.TemporalWorkflowClient,
	writerTaskQueue string,
	helloTaskQueue string,
	seedTaskQueue string,
	assetTaskQueue string,
	graphTaskQueue string,
) (workflows.WriterStarter, workflows.AgentHelloStarter, workflows.SeedRunStarter, workflows.AssetIngestionStarter, workflows.StyleExtractionStarter, workflows.AssetReindexStarter, workflows.StoryGraphBuildStarter, workflows.StoryGraphBondGenerationStarter) {
	return newTemporalStartersWithAdmission(
		temporalClient,
		writerTaskQueue,
		helloTaskQueue,
		seedTaskQueue,
		assetTaskQueue,
		graphTaskQueue,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
	)
}

func newTemporalStartersWithAdmission(
	temporalClient workflows.TemporalWorkflowClient,
	writerTaskQueue string,
	helloTaskQueue string,
	seedTaskQueue string,
	assetTaskQueue string,
	graphTaskQueue string,
	writerAdmissionStore workflows.WriterAdmissionStore,
	seedAdmissionStore workflows.SeedAdmissionStore,
	assetIngestionAdmissionStore workflows.AssetIngestionAdmissionStore,
	styleExtractionAdmissionStore workflows.StyleExtractionAdmissionStore,
	assetReindexAdmissionStore workflows.AssetReindexAdmissionStore,
	storyGraphAdmissionStore workflows.StoryGraphBuildAdmissionStore,
	storyGraphBondAdmissionStore workflows.StoryGraphBondGenerationAdmissionStore,
) (workflows.WriterStarter, workflows.AgentHelloStarter, workflows.SeedRunStarter, workflows.AssetIngestionStarter, workflows.StyleExtractionStarter, workflows.AssetReindexStarter, workflows.StoryGraphBuildStarter, workflows.StoryGraphBondGenerationStarter) {
	return workflows.NewTemporalWriterStarter(workflows.TemporalWriterConfig{
			Client:         temporalClient,
			TaskQueue:      writerTaskQueue,
			AdmissionStore: writerAdmissionStore,
		}),
		workflows.NewTemporalHelloAgentStarter(workflows.TemporalHelloAgentConfig{
			Client:    temporalClient,
			TaskQueue: helloTaskQueue,
		}),
		workflows.NewTemporalSeedRunStarter(workflows.TemporalSeedRunConfig{
			Client:         temporalClient,
			TaskQueue:      seedTaskQueue,
			AdmissionStore: seedAdmissionStore,
		}),
		workflows.NewTemporalAssetIngestionStarter(workflows.TemporalAssetIngestionConfig{
			Client:         temporalClient,
			TaskQueue:      assetTaskQueue,
			AdmissionStore: assetIngestionAdmissionStore,
		}),
		workflows.NewTemporalStyleExtractionStarter(workflows.TemporalStyleExtractionConfig{
			Client:         temporalClient,
			TaskQueue:      assetTaskQueue,
			AdmissionStore: styleExtractionAdmissionStore,
		}),
		workflows.NewTemporalAssetReindexStarter(workflows.TemporalAssetReindexConfig{
			Client:         temporalClient,
			TaskQueue:      assetTaskQueue,
			AdmissionStore: assetReindexAdmissionStore,
		}),
		workflows.NewTemporalStoryGraphBuildStarter(workflows.TemporalStoryGraphBuildConfig{
			Client:         temporalClient,
			TaskQueue:      graphTaskQueue,
			AdmissionStore: storyGraphAdmissionStore,
		}),
		workflows.NewTemporalStoryGraphBondGenerationStarter(workflows.TemporalStoryGraphBondGenerationConfig{
			Client:         temporalClient,
			TaskQueue:      graphTaskQueue,
			AdmissionStore: storyGraphBondAdmissionStore,
		})
}

func newWriterAdmissionStore(databaseURL string) (workflows.WriterAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWriterAdmissionStore(workflows.SQLWriterAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newDraftAdoptionStore(databaseURL string) (workflows.DraftAdoptionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLDraftAdoptionStore(workflows.SQLDraftAdoptionStoreConfig{
		Queryer: workflows.NewSQLDBWriterDraftAdoptionQueryer(db),
	}), db.Close, nil
}

func newDraftReviewStore(databaseURL string) (workflows.DraftReviewStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledDraftReviewStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLDraftReviewStore(workflows.SQLDraftReviewStoreConfig{
		Execer:  workflows.NewSQLDBWriterAdmissionExecer(db),
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newSeedAdmissionStore(databaseURL string) (workflows.SeedAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLSeedAdmissionStore(workflows.SQLSeedAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newAssetIngestionAdmissionStore(databaseURL string) (workflows.AssetIngestionAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLAssetIngestionAdmissionStore(workflows.SQLAssetIngestionAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newStyleExtractionAdmissionStore(databaseURL string) (workflows.StyleExtractionAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLStyleExtractionAdmissionStore(workflows.SQLStyleExtractionAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newAssetReindexAdmissionStore(databaseURL string) (workflows.AssetReindexAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLAssetReindexAdmissionStore(workflows.SQLAssetReindexAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newStoryGraphBuildAdmissionStore(databaseURL string) (workflows.StoryGraphBuildAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLStoryGraphBuildAdmissionStore(workflows.SQLStoryGraphBuildAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newStoryGraphBondGenerationAdmissionStore(databaseURL string) (workflows.StoryGraphBondGenerationAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLStoryGraphBondGenerationAdmissionStore(workflows.SQLStoryGraphBondGenerationAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newWriterReader(databaseURL string) (workflows.WriterReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWriterReader(workflows.SQLWriterReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newManuscriptReader(databaseURL string) (workflows.ManuscriptReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLManuscriptReader(workflows.SQLManuscriptReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newWorkflowReader(databaseURL string) (workflows.WorkflowReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWorkflowReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWorkflowReader(workflows.SQLWorkflowReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newWorkflowEventReader(databaseURL string) (workflows.WorkflowEventReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWorkflowEventReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWorkflowEventReader(workflows.SQLWorkflowEventReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newSeedRunReader(databaseURL string) (workflows.SeedRunReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledSeedRunReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLSeedRunReader(workflows.SQLSeedRunReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newProjectReadinessReader(databaseURL string) (projectreadiness.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return projectreadiness.NewDisabledReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return projectreadiness.NewSQLReader(projectreadiness.SQLReaderConfig{
		Queryer: projectreadiness.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newProjectOverviewReader(databaseURL string) (projectoverview.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return projectoverview.NewDisabledReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return projectoverview.NewSQLReader(projectoverview.SQLReaderConfig{
		Queryer: projectoverview.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newStoryGraphReader(databaseURL string) (storygraph.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return storygraph.NewDisabledReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return storygraph.NewSQLReader(storygraph.SQLReaderConfig{
		Queryer: storygraph.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineSavedPathReader(databaseURL string) (worldline.SavedPathReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledSavedPathReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLSavedPathReader(worldline.SQLSavedPathReaderConfig{
		Queryer: worldline.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineSavedPathStore(databaseURL string) (worldline.SavedPathStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledSavedPathStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	return worldline.NewSQLSavedPathStore(worldline.SQLSavedPathStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newWorldlineSessionStore(databaseURL string) (worldline.SessionStarter, worldline.SessionReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledSessionStarter(), worldline.NewDisabledSessionReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	store := worldline.NewSQLSessionStore(worldline.SQLSessionStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	})
	return store, store, db.Close, nil
}

func newWorldlineStepStarter(databaseURL string) (worldline.StepStarter, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledStepStarter(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	return worldline.NewSQLStepStarter(worldline.SQLStepStarterConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newWorldlinePreparationStore(databaseURL string) (worldline.PreparationStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledPreparationStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	return worldline.NewSQLPreparationStore(worldline.SQLPreparationStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newWorldlineTimelineReader(databaseURL string) (worldline.TimelineReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledTimelineReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLTimelineReader(worldline.SQLTimelineReaderConfig{
		Queryer: worldline.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineEventReader(databaseURL string) (worldline.EventReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledEventReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLEventReader(worldline.SQLEventReaderConfig{
		Queryer: worldline.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineEventAdoptionStore(databaseURL string) (worldline.EventAdoptionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledEventAdoptionStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLEventAdoptionStore(worldline.SQLEventAdoptionStoreConfig{
		Queryer: worldline.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineEventMutationStore(databaseURL string) (worldline.EventMutationStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledEventMutationStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLEventMutationStore(worldline.SQLEventMutationStoreConfig{
		Queryer: worldline.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineVariableStore(databaseURL string) (worldline.VariableStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledVariableStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	return worldline.NewSQLVariableStore(worldline.SQLVariableStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newCharacterConsoleStore(databaseURL string) (characterconsole.Store, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return characterconsole.NewDisabledStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := characterconsole.NewSQLDBQueryer(db)
	return characterconsole.NewSQLStore(characterconsole.SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newWorkflowCanceller(temporalClient workflows.TemporalWorkflowClient, databaseURL string) (workflows.WorkflowCanceller, func() error, error) {
	if temporalClient == nil || strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWorkflowCanceller(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	store := workflows.NewSQLWorkflowCancellationStore(workflows.SQLWorkflowCancellationStoreConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
		Execer:  workflows.NewSQLDBWriterAdmissionExecer(db),
	})
	return workflows.NewTemporalWorkflowCanceller(workflows.TemporalWorkflowCancellerConfig{
		Client: temporalClient,
		Store:  store,
	}), db.Close, nil
}

func newSourceFileStore(databaseURL string) (sourcefiles.Store, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return sourcefiles.NewDisabledStore(), nil, nil
	}
	objectVerifier, err := newObjectVerifierFromEnv()
	if err != nil {
		return nil, nil, err
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return sourcefiles.NewSQLStore(sourcefiles.SQLStoreConfig{
		Queryer:        sourcefiles.NewSQLDBQueryer(db),
		ObjectVerifier: objectVerifier,
	}), db.Close, nil
}

func newAssetReader(databaseURL string) (assets.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assets.NewSQLReader(assets.SQLReaderConfig{
		Queryer: assets.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newArchiveMemoryReader(databaseURL string) (assets.ArchiveMemoryReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledArchiveMemoryReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assets.NewSQLArchiveMemoryReader(assets.SQLArchiveMemoryReaderConfig{
		Queryer: assets.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newArchiveMemoryReviewStore(databaseURL string) (assets.ArchiveMemoryReviewStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledArchiveMemoryReviewStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assets.NewSQLArchiveMemoryReviewStore(assets.SQLArchiveMemoryReviewStoreConfig{
		Queryer: assets.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newAssetAdoptionStore(databaseURL string) (assets.AdoptionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledAdoptionStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assets.NewSQLAdoptionStore(assets.SQLAdoptionStoreConfig{
		Queryer: assets.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newAssetMutationStore(databaseURL string) (assets.MutationStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledMutationStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assets.NewSQLMutationStore(assets.SQLMutationStoreConfig{
		Queryer: assets.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newAssetBulkActionStore(databaseURL string) (assets.BulkActionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledBulkActionStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assets.NewSQLBulkActionStore(assets.SQLBulkActionStoreConfig{
		Queryer: assets.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newAssetIngestionReader(databaseURL string) (workflows.AssetIngestionReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledAssetIngestionReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	workflowReader := workflows.NewSQLWorkflowReader(workflows.SQLWorkflowReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	})
	return workflows.NewWorkflowAssetIngestionReader(workflowReader), db.Close, nil
}

func newStyleExtractionReader(databaseURL string) (workflows.StyleExtractionReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledStyleExtractionReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	workflowReader := workflows.NewSQLWorkflowReader(workflows.SQLWorkflowReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	})
	return workflows.NewWorkflowStyleExtractionReader(workflowReader), db.Close, nil
}

func newObjectVerifierFromEnv() (sourcefiles.ObjectVerifier, error) {
	endpoint := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_ENDPOINT"))
	bucket := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_BUCKET"))
	accessKey := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY"))
	secretKey := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY"))
	if endpoint == "" && bucket == "" && accessKey == "" && secretKey == "" {
		return nil, nil
	}
	return sourcefiles.NewMinIOObjectVerifier(sourcefiles.MinIOObjectVerifierConfig{
		Endpoint:  endpoint,
		Bucket:    bucket,
		AccessKey: accessKey,
		SecretKey: secretKey,
		UseSSL:    parseBoolEnv(os.Getenv("MIROFISH_OBJECT_STORAGE_USE_SSL")),
	})
}

func newObjectWriterFromEnv() (sourcefiles.ObjectWriter, error) {
	endpoint := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_ENDPOINT"))
	bucket := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_BUCKET"))
	accessKey := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY"))
	secretKey := strings.TrimSpace(os.Getenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY"))
	if endpoint == "" && bucket == "" && accessKey == "" && secretKey == "" {
		return nil, nil
	}
	return sourcefiles.NewMinIOObjectWriter(sourcefiles.MinIOObjectWriterConfig{
		Endpoint:  endpoint,
		Bucket:    bucket,
		AccessKey: accessKey,
		SecretKey: secretKey,
		UseSSL:    parseBoolEnv(os.Getenv("MIROFISH_OBJECT_STORAGE_USE_SSL")),
	})
}

func parseBoolEnv(value string) bool {
	normalized := strings.TrimSpace(strings.ToLower(value))
	return normalized == "1" || normalized == "true" || normalized == "yes"
}

func newLLMResolver(databaseURL string) (llm.Resolver, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewStaticResolver(nil), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLResolver(llm.SQLResolverConfig{
		Queryer: llm.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newLLMBindingStore(databaseURL string) (llm.BindingStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewDisabledBindingStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLBindingStore(llm.SQLBindingStoreConfig{
		Queryer: llm.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newLLMCatalogReader(databaseURL string) (llm.CatalogReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewDisabledCatalogReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLCatalogReader(llm.SQLCatalogConfig{
		Queryer: llm.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newLLMChannelStore(databaseURL string, credentialKey string) (llm.ChannelStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewDisabledChannelStore(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLChannelStore(llm.SQLChannelStoreConfig{
		Queryer:               llm.NewSQLDBQueryer(db),
		CredentialKeyMaterial: credentialKey,
	}), db.Close, nil
}

func newLLMModelSyncer(databaseURL string, credentialKey string) (llm.ModelSyncer, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewDisabledModelSyncer(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLModelSyncer(llm.SQLModelSyncerConfig{
		Queryer:               llm.NewSQLDBQueryer(db),
		CredentialKeyMaterial: credentialKey,
	}), db.Close, nil
}

func newLLMSettingsReader(databaseURL string) (llm.SettingsReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewDisabledSettingsReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLSettingsReader(llm.SQLSettingsReaderConfig{
		Queryer: llm.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newLLMTelemetryReader(databaseURL string) (llm.TelemetryReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return llm.NewDisabledTelemetryReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLTelemetryReader(llm.SQLTelemetryConfig{
		Queryer: llm.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newTraceReader(databaseURL string) (traces.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return traces.NewDisabledReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return traces.NewSQLReader(traces.SQLReaderConfig{
		Queryer: traces.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newTraceExportAuditor(databaseURL string) (traces.ExportAuditor, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return traces.NewDisabledExportAuditor(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return traces.NewSQLExportAuditor(traces.SQLExportAuditorConfig{
		Queryer: traces.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWriterEventReader(databaseURL string) (workflows.WriterEventReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWriterEventReader(), nil, nil
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWriterEventReader(workflows.SQLWriterEventReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}
