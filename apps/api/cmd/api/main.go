package main

import (
	"context"
	"database/sql"
	"encoding/base64"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/assetcatalog"
	"mirofish-novel/apps/api/internal/assetdistillation"
	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/authrecovery"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/collaboration"
	"mirofish-novel/apps/api/internal/httpapi"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/llmadmin"
	"mirofish-novel/apps/api/internal/manuscriptexport"
	"mirofish-novel/apps/api/internal/manuscriptworkspace"
	"mirofish-novel/apps/api/internal/observability"
	"mirofish-novel/apps/api/internal/platformratelimit"
	"mirofish-novel/apps/api/internal/projectadmin"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/registration"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/traces"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"
	"mirofish-novel/apps/api/internal/writerplanning"
	"mirofish-novel/apps/api/internal/writerworkspace"

	_ "github.com/jackc/pgx/v5/stdlib"
	"go.temporal.io/sdk/client"
)

const (
	appDatabaseMaxOpenConnections  = 4
	authDatabaseMaxOpenConnections = 8
	authDatabaseMaxIdleConnections = 4
)

func openAppDatabase(databaseURL string) (*sql.DB, error) {
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(appDatabaseMaxOpenConnections)
	db.SetMaxIdleConns(0)
	db.SetConnMaxIdleTime(time.Minute)
	db.SetConnMaxLifetime(30 * time.Minute)
	return db, nil
}

func openAuthDatabase(databaseURL string) (*sql.DB, error) {
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(authDatabaseMaxOpenConnections)
	db.SetMaxIdleConns(authDatabaseMaxIdleConnections)
	db.SetConnMaxIdleTime(5 * time.Minute)
	db.SetConnMaxLifetime(30 * time.Minute)
	return db, nil
}

type authRuntime struct {
	db                    *sql.DB
	reader                auth.Reader
	passwordAuthenticator auth.PasswordAuthenticator
	passwordChanger       auth.PasswordChanger
	registrationService   *registration.Service
	sessionStore          auth.SessionStore
	authorizer            auth.Authorizer
}

func newAuthRuntime(databaseURL string) (authRuntime, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		reader := auth.NewDisabledReader()
		return authRuntime{
			reader:              reader,
			registrationService: registration.NewService(registration.ServiceConfig{}),
			authorizer:          auth.NewReaderBackedAuthorizer(reader),
		}, nil, nil
	}
	db, err := openAuthDatabase(databaseURL)
	if err != nil {
		return authRuntime{}, nil, err
	}
	queryer := auth.NewSQLDBQueryer(db)
	reader := auth.NewSQLReader(auth.SQLReaderConfig{Queryer: queryer})
	return authRuntime{
		db:     db,
		reader: reader,
		passwordAuthenticator: auth.NewSQLPasswordAuthenticator(auth.SQLPasswordAuthenticatorConfig{
			Queryer: queryer,
			Reader:  reader,
		}),
		passwordChanger: auth.NewSQLPasswordChanger(auth.SQLPasswordChangerConfig{
			Queryer: queryer,
			Execer:  queryer,
		}),
		registrationService: registration.NewService(registration.ServiceConfig{DB: db}),
		sessionStore: auth.NewSQLSessionStore(auth.SQLSessionStoreConfig{
			Queryer: queryer,
			Execer:  queryer,
		}),
		authorizer: auth.NewSQLAuthorizer(auth.SQLAuthorizerConfig{Queryer: queryer}),
	}, db.Close, nil
}

func main() {
	addr := os.Getenv("MIROFISH_API_ADDR")
	if addr == "" {
		addr = ":8080"
	}
	databaseURL := os.Getenv("DATABASE_URL")

	authDependencies, closeAuthRuntime, err := newAuthRuntime(databaseURL)
	if err != nil {
		log.Fatalf("configure auth runtime: %v", err)
	}
	if closeAuthRuntime != nil {
		defer func() {
			if err := closeAuthRuntime(); err != nil {
				log.Printf("close auth runtime: %v", err)
			}
		}()
	}
	authReader := authDependencies.reader
	passwordAuthenticator := authDependencies.passwordAuthenticator
	passwordChanger := authDependencies.passwordChanger
	registrationService := authDependencies.registrationService
	authSessionStore := authDependencies.sessionStore

	// CONN-017: when DATABASE_URL is configured, do not silently accept writer starts
	// against an in-memory LocalWriterStarter unless ALLOW_LOCAL_WRITER_STARTER=1.
	writerStarter := workflows.WriterStarter(workflows.NewLocalWriterStarter())
	if strings.TrimSpace(databaseURL) != "" && !parseBoolEnv(os.Getenv("ALLOW_LOCAL_WRITER_STARTER")) {
		writerStarter = workflows.NewFailClosedWriterStarter()
	}
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
	writerThreadStore, closeWriterThreads, err := newWriterThreadStore(databaseURL)
	if err != nil {
		log.Fatalf("configure writer thread store: %v", err)
	}
	if closeWriterThreads != nil {
		defer func() {
			if err := closeWriterThreads(); err != nil {
				log.Printf("close writer thread store: %v", err)
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
	draftReviewReader, closeDraftReview, err := newDraftReviewStore(databaseURL)
	if err != nil {
		log.Fatalf("configure draft review reader: %v", err)
	}
	if closeDraftReview != nil {
		defer func() {
			if err := closeDraftReview(); err != nil {
				log.Printf("close draft review store: %v", err)
			}
		}()
	}
	draftReviewRuntimeStore, draftReviewIssueStore, closeDraftReviewRuntime, err := newDraftReviewRuntimeStores(databaseURL)
	if err != nil {
		log.Fatalf("configure draft review runtime store: %v", err)
	}
	if closeDraftReviewRuntime != nil {
		defer func() {
			if err := closeDraftReviewRuntime(); err != nil {
				log.Printf("close draft review runtime store: %v", err)
			}
		}()
	}
	draftReviewStore := workflows.DraftReviewStore(
		workflows.NewDraftReviewRuntimeService(nil, draftReviewReader),
	)
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
	analysisAdmissionStore, closeAnalysisAdmission, err := newAnalysisAdmissionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure analysis admission store: %v", err)
	}
	if closeAnalysisAdmission != nil {
		defer func() {
			if err := closeAnalysisAdmission(); err != nil {
				log.Printf("close analysis admission store: %v", err)
			}
		}()
	}
	analysisStarter := workflows.AnalysisRunStarter(workflows.NewFailClosedAnalysisStarter())
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
	var temporalReadinessClient client.Client
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
		analysisTaskQueue := strings.TrimSpace(os.Getenv("ANALYSIS_TASK_QUEUE"))
		if analysisTaskQueue == "" {
			analysisTaskQueue = workflows.AnalysisTaskQueue
		}
		analysisStarter = workflows.NewTemporalAnalysisStarter(workflows.TemporalAnalysisConfig{
			Client:         temporalClient,
			TaskQueue:      analysisTaskQueue,
			AdmissionStore: analysisAdmissionStore,
		})
		if canceller, ok := writerStarter.(workflows.WriterCanceller); ok {
			writerCanceller = canceller
		}
		temporalWorkflowClient = temporalClient
		temporalReadinessClient = temporalClient
		if draftReviewRuntimeStore != nil {
			draftReviewStore = workflows.NewDraftReviewRuntimeService(
				workflows.NewTemporalDraftReviewStarter(workflows.TemporalDraftReviewConfig{
					Client:         temporalClient,
					TaskQueue:      os.Getenv("WRITER_REVIEW_TASK_QUEUE"),
					AdmissionStore: draftReviewRuntimeStore,
				}),
				draftReviewReader,
			)
		}
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
	manuscriptArtifactExporter, closeManuscriptArtifactExporter, err := newManuscriptArtifactExporter(databaseURL)
	if err != nil {
		log.Fatalf("configure manuscript artifact exporter: %v", err)
	}
	if closeManuscriptArtifactExporter != nil {
		defer func() {
			if err := closeManuscriptArtifactExporter(); err != nil {
				log.Printf("close manuscript artifact exporter: %v", err)
			}
		}()
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
	analysisRunReader, analysisEventReader, analysisWorkspaceReader, analysisCandidateReader, analysisAssetImporter, closeAnalysisReaders, err := newAnalysisReaders(databaseURL)
	if err != nil {
		log.Fatalf("configure analysis readers: %v", err)
	}
	if closeAnalysisReaders != nil {
		defer func() {
			if err := closeAnalysisReaders(); err != nil {
				log.Printf("close analysis readers: %v", err)
			}
		}()
	}
	var analysisCanceller workflows.AnalysisCanceller = workflows.NewDisabledAnalysisCanceller()
	if canceller, ok := analysisStarter.(workflows.AnalysisCanceller); ok {
		analysisCanceller = canceller
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
	workflowRetrier, closeWorkflowRetrier, err := newWorkflowRetrier(temporalWorkflowClient, databaseURL, os.Getenv("SEED_TASK_QUEUE"))
	if err != nil {
		log.Fatalf("configure workflow retrier: %v", err)
	}
	if closeWorkflowRetrier != nil {
		defer func() {
			if err := closeWorkflowRetrier(); err != nil {
				log.Printf("close workflow retrier: %v", err)
			}
		}()
	}
	seedSegmentRetrier, closeSeedSegmentRetrier, err := newSeedSegmentRetrier(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("SEED_TASK_QUEUE"),
	)
	if err != nil {
		log.Fatalf("configure seed segment retrier: %v", err)
	}
	if closeSeedSegmentRetrier != nil {
		defer func() {
			if err := closeSeedSegmentRetrier(); err != nil {
				log.Printf("close seed segment retrier: %v", err)
			}
		}()
	}

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
	llmQuotaStore, closeLLMQuotaStore, err := newLLMQuotaStore(databaseURL)
	if err != nil {
		log.Fatalf("configure LLM quota store: %v", err)
	}
	if closeLLMQuotaStore != nil {
		defer func() {
			if err := closeLLMQuotaStore(); err != nil {
				log.Printf("close LLM quota store: %v", err)
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
	assetBundle, closeAssets, err := newAssetReaderBundle(databaseURL)
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
	storyGraphCandidateAdoptionStore, closeStoryGraphCandidateAdoptions, err := newStoryGraphCandidateAdoptionStore(databaseURL)
	if err != nil {
		log.Fatalf("configure story graph candidate adoption store: %v", err)
	}
	if closeStoryGraphCandidateAdoptions != nil {
		defer func() {
			if err := closeStoryGraphCandidateAdoptions(); err != nil {
				log.Printf("close story graph candidate adoption store: %v", err)
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
	worldlineStepStarter, closeWorldlineStepStarter, err := newWorldlineStepStarter(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("WORLDLINE_TASK_QUEUE"),
	)
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
	worldlineAutoEvolutionStarter, closeWorldlineAutoEvolutionStarter, err := newWorldlineAutoEvolutionStarter(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("WORLDLINE_TASK_QUEUE"),
	)
	if err != nil {
		log.Fatalf("configure worldline auto-evolution starter: %v", err)
	}
	if closeWorldlineAutoEvolutionStarter != nil {
		defer func() {
			if err := closeWorldlineAutoEvolutionStarter(); err != nil {
				log.Printf("close worldline auto-evolution starter: %v", err)
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
	worldlinePreparationStarter, closeWorldlinePreparationStarter, err := newWorldlinePreparationStarter(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("WORLDLINE_TASK_QUEUE"),
	)
	if err != nil {
		log.Fatalf("configure worldline preparation starter: %v", err)
	}
	if closeWorldlinePreparationStarter != nil {
		defer func() {
			if err := closeWorldlinePreparationStarter(); err != nil {
				log.Printf("close worldline preparation starter: %v", err)
			}
		}()
	}
	worldlineGoalStartStarter, closeWorldlineGoalStartStarter, err := newWorldlineGoalStartStarter(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("WORLDLINE_CAST_TASK_QUEUE"),
	)
	if err != nil {
		log.Fatalf("configure worldline goal-start starter: %v", err)
	}
	if closeWorldlineGoalStartStarter != nil {
		defer func() {
			if err := closeWorldlineGoalStartStarter(); err != nil {
				log.Printf("close worldline goal-start starter: %v", err)
			}
		}()
	}
	worldlineGoalStartReader, closeWorldlineGoalStartReader, err := newWorldlineGoalStartReader(databaseURL)
	if err != nil {
		log.Fatalf("configure worldline goal-start reader: %v", err)
	}
	if closeWorldlineGoalStartReader != nil {
		defer func() {
			if err := closeWorldlineGoalStartReader(); err != nil {
				log.Printf("close worldline goal-start reader: %v", err)
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
	characterProposalStore, closeCharacterProposalStore, err := newCharacterProposalStore(databaseURL)
	if err != nil {
		log.Fatalf("configure character proposal store: %v", err)
	}
	if closeCharacterProposalStore != nil {
		defer func() {
			if err := closeCharacterProposalStore(); err != nil {
				log.Printf("close character proposal store: %v", err)
			}
		}()
	}
	characterDialogueStarter, closeCharacterDialogueStarter, err := newCharacterDialogueStarter(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("CHARACTER_TASK_QUEUE"),
	)
	if err != nil {
		log.Fatalf("configure character dialogue starter: %v", err)
	}
	if closeCharacterDialogueStarter != nil {
		defer func() {
			if err := closeCharacterDialogueStarter(); err != nil {
				log.Printf("close character dialogue starter: %v", err)
			}
		}()
	}
	centralAuthorizer := authDependencies.authorizer
	writerPlanningStarter, closeWriterPlanningStarter, err := newWriterPlanningStarter(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("WRITER_PLANNING_TASK_QUEUE"),
	)
	if err != nil {
		log.Fatalf("configure writer planning starter: %v", err)
	}
	if closeWriterPlanningStarter != nil {
		defer func() {
			if err := closeWriterPlanningStarter(); err != nil {
				log.Printf("close writer planning starter: %v", err)
			}
		}()
	}
	writerWorkspaceHandler, closeWriterWorkspaceHandler, err := newWriterWorkspaceHandler(databaseURL, centralAuthorizer, writerPlanningStarter)
	if err != nil {
		log.Fatalf("configure writer workspace handler: %v", err)
	}
	if closeWriterWorkspaceHandler != nil {
		defer func() {
			if err := closeWriterWorkspaceHandler(); err != nil {
				log.Printf("close writer workspace handler: %v", err)
			}
		}()
	}
	// Shared proxy so manuscript mutations can stale proposals once distillation store is ready.
	proposalStalerProxy := &proposalStalerBridge{}
	manuscriptWorkspaceHandler, manuscriptExportHandler, closeManuscriptWorkspaceHandler, err := newManuscriptWorkspaceHandlers(
		databaseURL,
		os.Getenv("MANUSCRIPT_ARTIFACT_ROOT"),
		centralAuthorizer,
		writerStarter,
		manuscriptArtifactExporter,
		writerPlanningStarter,
		proposalStalerProxy,
	)
	if err != nil {
		log.Fatalf("configure manuscript workspace handlers: %v", err)
	}
	if closeManuscriptWorkspaceHandler != nil {
		defer func() {
			if err := closeManuscriptWorkspaceHandler(); err != nil {
				log.Printf("close manuscript workspace handlers: %v", err)
			}
		}()
	}
	assetCatalogHandler, closeAssetCatalogHandler, err := newAssetCatalogHandler(databaseURL, centralAuthorizer)
	if err != nil {
		log.Fatalf("configure asset catalog handler: %v", err)
	}
	if closeAssetCatalogHandler != nil {
		defer func() {
			if err := closeAssetCatalogHandler(); err != nil {
				log.Printf("close asset catalog handler: %v", err)
			}
		}()
	}
	assetDistillationBundle, closeAssetDistillationHandler, err := newAssetDistillationHandler(
		temporalWorkflowClient,
		databaseURL,
		os.Getenv("WRITER_PLANNING_TASK_QUEUE"),
		centralAuthorizer,
		storyGraphBuildStarter,
	)
	if err != nil {
		log.Fatalf("configure asset distillation handler: %v", err)
	}
	if closeAssetDistillationHandler != nil {
		defer func() {
			if err := closeAssetDistillationHandler(); err != nil {
				log.Printf("close asset distillation handler: %v", err)
			}
		}()
	}
	var assetDistillationHandler http.Handler
	var distillationEnqueuer httpapi.DistillationEnqueuer
	if assetDistillationBundle != nil {
		assetDistillationHandler = assetDistillationBundle
		distillationEnqueuer = assetDistillationBundle
		// CONN-004/005: same-TX adoption outbox via DraftAdoptionOutboxHook.
		attachDraftAdoptionOutbox(draftAdoptionStore, assetDistillationBundle)
		// CONN-005: manuscript content changes mark evidence-bound proposals stale.
		proposalStalerProxy.impl = assetDistillationBundle
	}
	metricsRegistry := observability.NewRegistry()
	platformRateLimiter, closePlatformRateLimiter, err := newPlatformRateLimiter(
		os.Getenv("MIROFISH_DEPLOYMENT_ENV"),
		os.Getenv("MIROFISH_AUTH_RATE_LIMIT_REDIS_URL"),
		os.Getenv("MIROFISH_RATE_LIMIT_KEY_SECRET"),
		os.Getenv("MIROFISH_RATE_LIMIT_POLICIES_JSON"),
	)
	if err != nil {
		log.Fatalf("configure platform rate limiter: %v", err)
	}
	if closePlatformRateLimiter != nil {
		defer func() {
			if err := closePlatformRateLimiter(); err != nil {
				log.Printf("close platform rate limiter: %v", err)
			}
		}()
	}
	trustedClientProofVerifier, err := newTrustedClientProofVerifier(
		os.Getenv("MIROFISH_RECOVERY_CLIENT_PROOF_SECRET"),
		platformRateLimiter != nil,
	)
	if err != nil {
		log.Fatalf("configure trusted client proof verifier: %v", err)
	}
	authRecoveryHandler, collaborationHandler, projectAdminHandler, llmAdminHandler, recoveryDispatcher, closePlatformHandlers, err := newPlatformHandlers(
		databaseURL,
		os.Getenv("LLM_CREDENTIAL_ENCRYPTION_KEY"),
		metricsRegistry,
		platformRateLimiter,
		trustedClientProofVerifier,
	)
	if err != nil {
		log.Fatalf("configure platform handlers: %v", err)
	}
	if closePlatformHandlers != nil {
		defer func() {
			if err := closePlatformHandlers(); err != nil {
				log.Printf("close platform handlers: %v", err)
			}
		}()
	}
	if recoveryDispatcher != nil {
		startAuthRecoveryDispatcher(recoveryDispatcher)
	}
	readinessChecker, closeReadinessChecker, err := newProductionReadinessChecker(productionReadinessConfig{
		DeploymentEnvironment:  os.Getenv("MIROFISH_DEPLOYMENT_ENV"),
		Timeout:                os.Getenv("MIROFISH_READINESS_TIMEOUT"),
		DatabaseURL:            databaseURL,
		RequiredMigration:      latestRequiredMigration,
		RequiredMigrationCount: requiredMigrationCount,
		RedisURL:               os.Getenv("MIROFISH_AUTH_RATE_LIMIT_REDIS_URL"),
		TemporalAddress:        os.Getenv("TEMPORAL_ADDRESS"),
		TemporalNamespace:      temporalNamespace(),
		TemporalClient:         temporalReadinessClient,
		TemporalTaskQueues: []string{
			os.Getenv("HELLO_AGENT_TASK_QUEUE"), os.Getenv("SEED_TASK_QUEUE"),
			os.Getenv("ASSET_TASK_QUEUE"), os.Getenv("GRAPH_TASK_QUEUE"),
			os.Getenv("WORLDLINE_TASK_QUEUE"), os.Getenv("CHARACTER_TASK_QUEUE"),
			os.Getenv("WRITER_REVIEW_TASK_QUEUE"), os.Getenv("WRITER_PLANNING_TASK_QUEUE"),
			os.Getenv("WRITER_TASK_QUEUE"),
			os.Getenv("LEGACY_IMPORT_TASK_QUEUE"),
		},
		ObjectEndpoint:  os.Getenv("MIROFISH_OBJECT_STORAGE_ENDPOINT"),
		ObjectBucket:    os.Getenv("MIROFISH_OBJECT_STORAGE_BUCKET"),
		ObjectAccessKey: os.Getenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY"),
		ObjectSecretKey: os.Getenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY"),
		ObjectUseSSL:    parseBoolEnv(os.Getenv("MIROFISH_OBJECT_STORAGE_USE_SSL")),
	})
	if err != nil {
		log.Fatalf("configure production readiness: %v", err)
	}
	if closeReadinessChecker != nil {
		defer func() {
			if err := closeReadinessChecker(); err != nil {
				log.Printf("close production readiness: %v", err)
			}
		}()
	}

	serverConfig := withSessionAuthSecret(httpapi.Config{
		AuthReader:                       authReader,
		PasswordAuthenticator:            passwordAuthenticator,
		PasswordChanger:                  passwordChanger,
		RegistrationService:              registrationService,
		AuthSessionStore:                 authSessionStore,
		Authorizer:                       centralAuthorizer,
		WriterStarter:                    writerStarter,
		WriterReader:                     writerReader,
		WriterEventReader:                writerEventReader,
		WriterCanceller:                  writerCanceller,
		WriterThreadStore:                writerThreadStore,
		DraftAdoptionStore:               draftAdoptionStore,
		DraftReviewStore:                 draftReviewStore,
		DraftReviewOwnerLookup:           draftReviewRuntimeStore,
		DraftReviewIssueStore:            draftReviewIssueStore,
		ManuscriptReader:                 manuscriptReader,
		ManuscriptArtifactExporter:       manuscriptArtifactExporter,
		WorkflowReader:                   workflowReader,
		WorkflowEventReader:              workflowEventReader,
		WorkflowCanceller:                workflowCanceller,
		WorkflowRetrier:                  workflowRetrier,
		SeedSegmentRetrier:               seedSegmentRetrier,
		SeedStarter:                      seedStarter,
		SeedRunReader:                    seedRunReader,
		AnalysisStarter:                  analysisStarter,
		AnalysisRunReader:                analysisRunReader,
		AnalysisEventReader:              analysisEventReader,
		AnalysisCanceller:                analysisCanceller,
		AnalysisWorkspaceReader:          analysisWorkspaceReader,
		AnalysisCandidateReader:          analysisCandidateReader,
		AnalysisAssetImporter:            analysisAssetImporter,
		ProjectOverviewReader:            projectOverviewReader,
		ProjectReadinessReader:           projectReadinessReader,
		AgentHelloStarter:                helloStarter,
		LLMResolver:                      llmResolver,
		LLMBindingStore:                  llmBindingStore,
		LLMCatalogReader:                 llmCatalogReader,
		LLMChannelStore:                  llmChannelStore,
		LLMModelSyncer:                   llmModelSyncer,
		LLMSettingsReader:                llmSettingsReader,
		LLMTelemetryReader:               llmTelemetryReader,
		LLMQuotaStore:                    llmQuotaStore,
		TraceReader:                      traceReader,
		TraceExportAuditor:               traceExportAuditor,
		SourceFileStore:                  sourceFileStore,
		SourceFileObjectWriter:           sourceFileObjectWriter,
		AssetReader:                      assetBundle.Reader,
		AssetQueryEmbeddingResolver:      assetBundle.QueryEmbeddingResolver,
		AssetSearchIndexChecker:          assetBundle.SearchIndexChecker,
		ArchiveMemoryReader:              archiveMemoryReader,
		ArchiveMemoryReviewStore:         archiveMemoryReviewStore,
		AssetAdoptionStore:               assetAdoptionStore,
		AssetMutationStore:               assetMutationStore,
		AssetBulkActionStore:             assetBulkActionStore,
		AssetReindexStarter:              assetReindexStarter,
		AssetIngestionStarter:            assetIngestionStarter,
		AssetIngestionReader:             assetIngestionReader,
		StyleExtractionStarter:           styleExtractionStarter,
		StyleExtractionReader:            styleExtractionReader,
		StoryGraphBuildStarter:           storyGraphBuildStarter,
		StoryGraphBondGenerationStarter:  storyGraphBondGenerationStarter,
		StoryGraphReader:                 storyGraphReader,
		StoryGraphCandidateAdoptionStore: storyGraphCandidateAdoptionStore,
		WorldlineSavedPathReader:         worldlineSavedPathReader,
		WorldlineSavedPathStore:          worldlineSavedPathStore,
		WorldlineSessionStarter:          worldlineSessionStarter,
		WorldlineStepStarter:             worldlineStepStarter,
		WorldlineAutoEvolutionStarter:    worldlineAutoEvolutionStarter,
		WorldlineSessionReader:           worldlineSessionReader,
		WorldlineTimelineReader:          worldlineTimelineReader,
		WorldlineEventReader:             worldlineEventReader,
		WorldlineEventAdoptionStore:      worldlineEventAdoptionStore,
		WorldlineEventMutationStore:      worldlineEventMutationStore,
		WorldlineVariableStore:           worldlineVariableStore,
		WorldlinePreparationStarter:      worldlinePreparationStarter,
		WorldlinePreparationStore:        worldlinePreparationStore,
		WorldlineGoalStartStarter:        worldlineGoalStartStarter,
		WorldlineGoalStartReader:         worldlineGoalStartReader,
		CharacterConsoleStore:            characterConsoleStore,
		CharacterProposalStore:           characterProposalStore,
		CharacterDialogueStarter:         characterDialogueStarter,
		WriterWorkspaceHandler:           writerWorkspaceHandler,
		ManuscriptWorkspaceHandler:       manuscriptWorkspaceHandler,
		ManuscriptExportHandler:          manuscriptExportHandler,
		AssetCatalogHandler:              assetCatalogHandler,
		AssetDistillationHandler:         assetDistillationHandler,
		DistillationEnqueuer:             distillationEnqueuer,
		AuthRecoveryHandler:              authRecoveryHandler,
		CollaborationHandler:             collaborationHandler,
		ProjectAdminHandler:              projectAdminHandler,
		LLMAdminHandler:                  llmAdminHandler,
		RateLimiter:                      platformRateLimiter,
		TrustedClientProofVerifier:       trustedClientProofVerifier,
		ReadinessChecker:                 readinessChecker,
	})
	server := httpapi.NewServer(serverConfig)
	rootHandler := http.NewServeMux()
	rootHandler.Handle("/metrics", metricsRegistry.Handler())
	rootHandler.Handle("/", metricsRegistry.Middleware(server))
	log.Printf("mirofish api listening on %s", addr)
	if err := http.ListenAndServe(addr, rootHandler); err != nil {
		log.Fatal(err)
	}
}

func withSessionAuthSecret(config httpapi.Config) httpapi.Config {
	config.SessionAuthSecret = strings.TrimSpace(os.Getenv("MIROFISH_AUTH_SESSION_SECRET"))
	config.ForceSecureSessionCookies = isProductionLike(os.Getenv("MIROFISH_DEPLOYMENT_ENV"))
	config.AllowDevelopmentAuth = developmentAuthAllowed(
		os.Getenv("MIROFISH_DEPLOYMENT_ENV"),
		os.Getenv("MIROFISH_ENABLE_DEVELOPMENT_AUTH"),
	)
	return config
}

func developmentAuthAllowed(deploymentEnvironment string, enabled string) bool {
	if strings.ToLower(strings.TrimSpace(deploymentEnvironment)) != "local" {
		return false
	}
	return parseBoolEnv(enabled)
}

func temporalNamespace() string {
	namespace := os.Getenv("TEMPORAL_NAMESPACE")
	if namespace == "" {
		return "default"
	}
	return namespace
}

func newPlatformRateLimiter(
	deploymentEnvironment string,
	redisURL string,
	keySecret string,
	policiesJSON string,
) (platformratelimit.Limiter, func() error, error) {
	deploymentEnvironment = strings.ToLower(strings.TrimSpace(deploymentEnvironment))
	redisURL = strings.TrimSpace(redisURL)
	keySecret = strings.TrimSpace(keySecret)
	policiesJSON = strings.TrimSpace(policiesJSON)
	configured := redisURL != "" || keySecret != "" || policiesJSON != ""
	required := deploymentEnvironment == "production" || deploymentEnvironment == "staging"
	if !configured {
		if required {
			return nil, nil, errors.New("platform rate limiter is required for staging and production")
		}
		return nil, nil, nil
	}
	if redisURL == "" || keySecret == "" || policiesJSON == "" {
		return nil, nil, errors.New("platform rate limiter configuration is incomplete")
	}
	policies, err := platformratelimit.ParseProductionPolicies(policiesJSON)
	if err != nil {
		return nil, nil, err
	}
	limiter, err := platformratelimit.NewRedisLimiter(platformratelimit.Config{
		URL:               redisURL,
		KeyHMACSecret:     []byte(keySecret),
		Prefix:            "mirofish:ratelimit:v1",
		CommandTimeout:    500 * time.Millisecond,
		ConnectTimeout:    2 * time.Second,
		Policies:          policies,
		RequireAllClasses: true,
	})
	if err != nil {
		return nil, nil, err
	}
	return limiter, limiter.Close, nil
}

func newTrustedClientProofVerifier(keyMaterial string, required bool) (*authrecovery.ClientProofVerifier, error) {
	keyMaterial = strings.TrimSpace(keyMaterial)
	if keyMaterial == "" {
		if required {
			return nil, errors.New("trusted client proof verifier is required with platform rate limiting")
		}
		return nil, nil
	}
	return authrecovery.NewClientProofVerifier([]byte(keyMaterial), nil, 2*time.Minute)
}

type writerWorkspaceActorResolver struct{}

func (writerWorkspaceActorResolver) ResolveActor(ctx context.Context, request *http.Request) (writerworkspace.Actor, error) {
	userID, ok := httpapi.ActorUserIDFromContext(ctx)
	if !ok {
		return writerworkspace.Actor{}, errors.New("authenticated actor context is required")
	}
	return writerworkspace.Actor{
		UserID: userID, TenantID: strings.TrimSpace(request.Header.Get("X-Tenant-Id")),
		RequestID: strings.TrimSpace(request.Header.Get("X-Request-Id")),
	}, nil
}

type writerWorkspaceAuthorizer struct{ base auth.Authorizer }

func (a writerWorkspaceAuthorizer) Authorize(ctx context.Context, input writerworkspace.AuthorizeInput) error {
	permission := auth.PermissionProjectRead
	switch input.Operation {
	case writerworkspace.OperationWrite:
		permission = auth.PermissionCreativeWrite
	case writerworkspace.OperationTenantPresetManage:
		permission = auth.PermissionTenantSessionManage
	}
	return a.base.Authorize(ctx, auth.AuthorizeInput{
		UserID: input.Actor.UserID, TenantID: input.Actor.TenantID, ProjectID: input.ProjectID,
		Permission: permission, RequestID: input.Actor.RequestID,
	})
}

type manuscriptContextResolver struct{ db *sql.DB }

func (r manuscriptContextResolver) ResolveManuscriptContext(ctx context.Context, request *http.Request, projectID string) (manuscriptworkspace.Scope, error) {
	userID, ok := httpapi.ActorUserIDFromContext(ctx)
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	projectID = strings.TrimSpace(projectID)
	if !ok || tenantID == "" || projectID == "" || r.db == nil {
		return manuscriptworkspace.Scope{}, errors.New("trusted manuscript context is required")
	}
	tx, err := r.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return manuscriptworkspace.Scope{}, err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err = tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", tenantID, userID); err != nil {
		return manuscriptworkspace.Scope{}, err
	}
	var existingProjectID string
	if err = tx.QueryRowContext(ctx, "SELECT project_id::text FROM projects WHERE tenant_id::text=$1 AND project_id::text=$2", tenantID, projectID).Scan(&existingProjectID); err != nil {
		return manuscriptworkspace.Scope{}, err
	}
	if err = tx.Commit(); err != nil {
		return manuscriptworkspace.Scope{}, err
	}
	return manuscriptworkspace.Scope{
		TenantID: tenantID, ProjectID: existingProjectID, ActorUserID: userID,
		RequestID: strings.TrimSpace(request.Header.Get("X-Request-Id")),
	}, nil
}

type manuscriptAuthorizer struct{ base auth.Authorizer }

func (a manuscriptAuthorizer) AuthorizeManuscript(ctx context.Context, scope manuscriptworkspace.Scope, permission string) error {
	authPermission := auth.PermissionProjectRead
	if permission == manuscriptworkspace.PermissionWrite {
		authPermission = auth.PermissionCreativeWrite
	}
	return a.base.Authorize(ctx, auth.AuthorizeInput{
		UserID: scope.ActorUserID, TenantID: scope.TenantID, ProjectID: scope.ProjectID,
		Permission: authPermission, RequestID: scope.RequestID,
	})
}

type mountedActorResolver struct{}

func (mountedActorResolver) ResolveActor(ctx context.Context, _ *http.Request) (string, error) {
	userID, ok := httpapi.ActorUserIDFromContext(ctx)
	if !ok {
		return "", errors.New("authenticated actor context is required")
	}
	return userID, nil
}

func newWriterPlanningStarter(
	temporalClient workflows.TemporalWorkflowClient,
	databaseURL string,
	taskQueue string,
) (writerplanning.Starter, func() error, error) {
	if temporalClient == nil || strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	store := writerplanning.NewSQLStore(db)
	return writerplanning.NewTemporalStarter(writerplanning.TemporalConfig{
		Client: temporalClient, Store: store, TaskQueue: taskQueue,
	}), db.Close, nil
}

func newAssetDistillationHandler(
	temporalClient workflows.TemporalWorkflowClient,
	databaseURL string,
	taskQueue string,
	authorizer auth.Authorizer,
	storyGraphBuildStarter workflows.StoryGraphBuildStarter,
) (*assetDistillationBundle, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	store := assetdistillation.NewSQLStore(db)
	var starter assetdistillation.Starter
	if temporalClient != nil {
		starter = assetdistillation.NewTemporalStarter(temporalClient, store, taskQueue)
		go runAssetDistillationDispatcher(assetdistillation.NewDispatcher(store, starter))
	}
	bundle := &assetDistillationBundle{
		store: store, enqueuer: assetdistillation.NewEnqueuer(store, starter),
		graphRebuild: storyGraphRebuildAdapter{starter: storyGraphBuildStarter},
	}
	handler := assetdistillation.NewHandler(assetdistillation.HandlerConfig{
		Store: store, Starter: starter, Actors: mountedActorResolver{},
		Authorizer: authorizer, GraphRebuild: bundle.graphRebuild,
	})
	bundle.handler = handler
	return bundle, db.Close, nil
}

type assetDistillationBundle struct {
	handler      http.Handler
	store        *assetdistillation.SQLStore
	enqueuer     *assetdistillation.Enqueuer
	graphRebuild assetdistillation.GraphRebuildStarter
}

type proposalStalerBridge struct {
	impl manuscriptworkspace.ProposalStaler
}

func (p *proposalStalerBridge) StaleProposalsForBlock(ctx context.Context, tenantID, projectID, actorUserID, blockID string) error {
	if p == nil || p.impl == nil {
		return nil
	}
	return p.impl.StaleProposalsForBlock(ctx, tenantID, projectID, actorUserID, blockID)
}

type storyGraphRebuildAdapter struct {
	starter workflows.StoryGraphBuildStarter
}

func (a storyGraphRebuildAdapter) StartAfterAssetAccept(ctx context.Context, tenantID, projectID, actorUserID, requestID, acceptedAssetID string) error {
	if a.starter == nil {
		return nil
	}
	reqID := strings.TrimSpace(requestID)
	if reqID == "" {
		reqID = "asset_accept_" + strings.TrimSpace(acceptedAssetID)
	} else {
		reqID = reqID + "_graph_" + strings.TrimSpace(acceptedAssetID)
	}
	_, err := a.starter.StartStoryGraphBuild(ctx, workflows.StartStoryGraphBuildInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ActorUserID: actorUserID,
		RequestID:   reqID,
		Mode:        "full",
		Options: map[string]any{
			"trigger":           "asset_accept",
			"accepted_asset_id": acceptedAssetID,
		},
	})
	return err
}

func (b *assetDistillationBundle) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if b == nil || b.handler == nil {
		http.Error(w, "asset distillation backend is not configured", http.StatusServiceUnavailable)
		return
	}
	b.handler.ServeHTTP(w, r)
}

func (b *assetDistillationBundle) EnqueueAfterAdoption(ctx context.Context, input httpapi.DistillationEnqueueInput) error {
	if b == nil || b.enqueuer == nil {
		return nil
	}
	return b.enqueuer.EnqueueAfterAdoption(ctx, assetdistillation.AfterAdoptionInput{
		TenantID: input.TenantID, ProjectID: input.ProjectID, ActorUserID: input.ActorUserID,
		RequestID: input.RequestID, BlockID: input.BlockID, ChapterID: input.ChapterID, SceneID: input.SceneID,
	})
}

// EnqueueAfterAdoptionInTx satisfies workflows.DraftAdoptionOutboxHook.
func (b *assetDistillationBundle) EnqueueAfterAdoptionInTx(ctx context.Context, rows workflows.DraftAdoptionSQLRows, input workflows.DraftAdoptionInput, result workflows.DraftAdoptionResult) error {
	if b == nil || b.enqueuer == nil {
		return nil
	}
	return b.enqueuer.EnqueueAfterAdoptionInTx(ctx, rows, input, result)
}

// StaleProposalsForBlock satisfies manuscriptworkspace.ProposalStaler.
func (b *assetDistillationBundle) StaleProposalsForBlock(ctx context.Context, tenantID, projectID, actorUserID, blockID string) error {
	if b == nil || b.store == nil {
		return nil
	}
	return b.store.StaleProposalsForBlock(ctx, assetdistillation.Scope{
		TenantID: tenantID, ProjectID: projectID, ActorUserID: actorUserID,
	}, blockID)
}

func runAssetDistillationDispatcher(dispatcher *assetdistillation.Dispatcher) {
	if dispatcher == nil {
		return
	}
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		started, err := dispatcher.Tick(ctx, 20)
		cancel()
		if err != nil {
			log.Printf("asset distillation dispatcher tick failed: started=%d err=%v", started, err)
		}
	}
}

func newWriterWorkspaceHandler(databaseURL string, authorizer auth.Authorizer, planning writerplanning.Starter) (http.Handler, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	store := writerworkspace.NewSQLStore(db)
	handler := writerworkspace.NewHandler(writerworkspace.HandlerConfig{
		Store: store, Actors: writerWorkspaceActorResolver{},
		Authorizer: writerWorkspaceAuthorizer{base: authorizer}, OwnerLookup: store,
		Planning: planning,
	})
	return handler, db.Close, nil
}

func newManuscriptWorkspaceHandlers(
	databaseURL string,
	artifactRoot string,
	authorizer auth.Authorizer,
	writerStarter workflows.WriterStarter,
	exporter workflows.ManuscriptArtifactExporter,
	planning writerplanning.Starter,
	proposalStaler manuscriptworkspace.ProposalStaler,
) (http.Handler, http.Handler, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil, nil
	}
	artifactStore, err := manuscriptexport.NewFileArtifactStore(artifactRoot)
	if err != nil {
		return nil, nil, nil, err
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, nil, err
	}
	store := manuscriptworkspace.NewSQLStore(db)
	commandStarter := manuscriptworkspace.NewWriterCommandStarter(writerStarter)
	commands := manuscriptworkspace.NewCommandService(store, commandStarter, commandStarter)
	generator := manuscriptexport.NewGenerator(manuscriptexport.GeneratorConfig{
		States: store, Exporter: exporter, Artifacts: artifactStore,
	})
	workspaceHandler := manuscriptworkspace.NewHandler(manuscriptworkspace.HandlerConfig{
		Store: store, Commands: commands, CommandReader: store, Exports: store,
		ExportGenerator: generator, Dedup: store, Resolver: manuscriptContextResolver{db: db},
		Authorizer: manuscriptAuthorizer{base: authorizer}, Planning: planning,
		ProposalStaler: proposalStaler,
	})
	downloadHandler := manuscriptexport.NewHandler(manuscriptexport.Config{
		Exporter: exporter, States: store, Artifacts: artifactStore,
		Authorizer: authorizer, ActorResolver: mountedActorResolver{},
	})
	return workspaceHandler, downloadHandler, db.Close, nil
}

type assetCatalogSecurityHandler struct {
	next       http.Handler
	authorizer auth.Authorizer
}

func (h assetCatalogSecurityHandler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	userID, ok := httpapi.ActorUserIDFromContext(request.Context())
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	parts := strings.Split(strings.Trim(request.URL.Path, "/"), "/")
	if !ok || tenantID == "" || len(parts) < 5 || parts[0] != "v1" || parts[1] != "projects" || parts[3] != "asset-catalog" {
		writeMountedHandlerError(response, http.StatusUnauthorized, auth.CodeUnauthenticated, "authentication is required")
		return
	}
	projectID := strings.TrimSpace(parts[2])
	requestID := strings.TrimSpace(request.Header.Get("X-Request-Id"))
	baseInput := auth.AuthorizeInput{
		UserID: userID, TenantID: tenantID, ProjectID: projectID,
		Permission: auth.PermissionProjectRead, RequestID: requestID,
	}
	if h.authorizer == nil || h.authorizer.Authorize(request.Context(), baseInput) != nil {
		writeMountedHandlerError(response, http.StatusForbidden, auth.CodeAccessDenied, "asset catalog access is required")
		return
	}
	requiresManage := request.Method != http.MethodGet || request.URL.Query().Get("include_private") == "true"
	canManage := false
	manageInput := baseInput
	manageInput.Permission = auth.PermissionAssetManage
	if err := h.authorizer.Authorize(request.Context(), manageInput); err == nil {
		canManage = true
	} else if requiresManage {
		writeMountedHandlerError(response, http.StatusForbidden, auth.CodeAccessDenied, "asset catalog management access is required")
		return
	} else if auth.ErrorCode(err) != auth.CodeAccessDenied {
		writeMountedHandlerError(response, http.StatusServiceUnavailable, auth.CodeLookupFailed, "authorization backend is unavailable")
		return
	}
	permissions := map[assetcatalog.Permission]bool{
		assetcatalog.PermissionReadPrivate: canManage,
		assetcatalog.PermissionMutate:      canManage,
		assetcatalog.PermissionCollections: canManage,
	}
	scope := assetcatalog.RequestScope{
		ActorID: userID, TenantID: tenantID, ProjectID: projectID, Permissions: permissions,
	}
	h.next.ServeHTTP(response, request.WithContext(assetcatalog.WithRequestScope(request.Context(), scope)))
}

func writeMountedHandlerError(response http.ResponseWriter, status int, code string, message string) {
	response.Header().Set("Content-Type", "application/json")
	response.Header().Set("Cache-Control", "private, no-store")
	response.WriteHeader(status)
	_, _ = response.Write([]byte(`{"error":{"code":"` + code + `","message":"` + message + `"}}`))
}

func newAssetCatalogHandler(databaseURL string, authorizer auth.Authorizer) (http.Handler, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return assetCatalogSecurityHandler{
		next: assetcatalog.NewHandler(assetcatalog.NewSQLStore(db)), authorizer: authorizer,
	}, db.Close, nil
}

type mountedCSRFVerifier struct{}

func (mountedCSRFVerifier) VerifyCSRF(ctx context.Context, _ *http.Request) error {
	if !httpapi.RequestCSRFVerified(ctx) {
		return errors.New("CSRF verification is required")
	}
	return nil
}

type mountedTrustedClientKeyResolver struct {
	verifier httpapi.TrustedClientProofVerifier
}

func (r mountedTrustedClientKeyResolver) ResolveTrustedClientKey(_ context.Context, request *http.Request) (string, error) {
	if r.verifier == nil {
		return "", errors.New("trusted client verification is unavailable")
	}
	return r.verifier.Verify(request.Header.Get(authrecovery.RecoveryClientProofHeader))
}

func newPlatformHandlers(
	databaseURL string,
	credentialKey string,
	metrics *observability.Registry,
	rateLimiter platformratelimit.Limiter,
	trustedClientVerifier *authrecovery.ClientProofVerifier,
) (http.Handler, http.Handler, http.Handler, http.Handler, *authrecovery.DeliveryDispatcher, func() error, error) {
	tokenCipher, err := newRecoveryTokenCipher(
		os.Getenv("MIROFISH_DEPLOYMENT_ENV"),
		os.Getenv("AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY"),
	)
	if err != nil {
		return nil, nil, nil, nil, nil, nil, err
	}
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil, nil, nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, nil, nil, nil, nil, err
	}
	fail := func(err error) (http.Handler, http.Handler, http.Handler, http.Handler, *authrecovery.DeliveryDispatcher, func() error, error) {
		_ = db.Close()
		return nil, nil, nil, nil, nil, nil, err
	}

	recoveryStore := authrecovery.NewSQLStore(db)
	recoveryService := authrecovery.NewService(authrecovery.ServiceConfig{DB: db, Store: recoveryStore, TokenCipher: tokenCipher})
	recoveryHandler := authrecovery.NewHandler(authrecovery.HandlerConfig{
		Service: recoveryService, ClientProofVerifier: trustedClientVerifier,
	})

	recoveryNotifier, invitationNotifier, err := configuredSMTPNotifiers()
	if err != nil {
		return fail(err)
	}
	var recoveryDispatcher *authrecovery.DeliveryDispatcher
	if recoveryNotifier != nil && tokenCipher != nil {
		recoveryDispatcher, err = authrecovery.NewDeliveryDispatcher(authrecovery.DeliveryDispatcherConfig{
			Store: recoveryStore, Notifier: recoveryNotifier, TokenCipher: tokenCipher,
			WorkerID: "api-auth-recovery", Lease: time.Minute, RetryDelay: time.Minute, MaxAttempts: 5,
			Metrics: metrics,
		})
		if err != nil {
			return fail(err)
		}
	}
	collaborationHandler := collaboration.NewHandler(collaboration.HandlerConfig{
		Service:       collaboration.NewService(collaboration.ServiceConfig{DB: db, Notifier: invitationNotifier}),
		ActorResolver: mountedActorResolver{}, CSRFVerifier: mountedCSRFVerifier{},
		RateLimiter:              rateLimiter,
		TrustedClientKeyResolver: mountedTrustedClientKeyResolver{verifier: trustedClientVerifier},
	})
	projectAdminHandler := projectadmin.NewHandler(projectadmin.HandlerConfig{
		Service:       projectadmin.NewService(projectadmin.ServiceConfig{DB: db}),
		ActorResolver: mountedActorResolver{}, CSRFVerifier: mountedCSRFVerifier{},
	})

	llmStore := llmadmin.NewSQLStore(db)
	var healthService *llmadmin.HealthService
	healthResolver, healthErr := llmadmin.NewSQLHealthCredentialResolver(llmadmin.SQLHealthCredentialResolverConfig{
		Queryer: llm.NewSQLDBQueryer(db), CredentialKeyMaterial: credentialKey,
	})
	if healthErr != nil {
		log.Printf("LLM provider health disabled: %s", llmadmin.ErrorCode(healthErr))
	} else {
		capabilityStore := llm.NewSQLChannelStore(llm.SQLChannelStoreConfig{
			Queryer: llm.NewSQLDBQueryer(db), CredentialKeyMaterial: credentialKey,
		})
		healthService = llmadmin.NewHealthService(
			healthResolver,
			llmadmin.NewHTTPHealthExecutor(http.DefaultClient, 10*time.Second, 1<<20),
			llmadmin.NewSQLHealthRecorder(db),
		).WithMetrics(metrics).WithCapabilityStore(capabilityStore)
	}
	llmAdminHandler := llmadmin.NewHandler(llmadmin.Config{
		Store: llmStore, Access: llmadmin.NewSQLAccessController(db), ActorResolver: mountedActorResolver{},
		Health: healthService, Metrics: metrics, RateLimiter: rateLimiter,
	})
	return recoveryHandler, collaborationHandler, projectAdminHandler, llmAdminHandler, recoveryDispatcher, db.Close, nil
}

func newRecoveryTokenCipher(deploymentEnvironment string, encodedKey string) (*authrecovery.TokenCipher, error) {
	deploymentEnvironment = strings.ToLower(strings.TrimSpace(deploymentEnvironment))
	encodedKey = strings.TrimSpace(encodedKey)
	if encodedKey == "" {
		if deploymentEnvironment == "staging" || deploymentEnvironment == "production" {
			return nil, errors.New("auth recovery outbox encryption key is required")
		}
		return nil, nil
	}
	decoded, err := base64.StdEncoding.Strict().DecodeString(encodedKey)
	if err != nil {
		return nil, errors.New("auth recovery outbox encryption key must use standard base64")
	}
	if len(decoded) != 32 {
		return nil, errors.New("auth recovery outbox encryption key must decode to exactly 32 bytes")
	}
	return authrecovery.NewTokenCipher(decoded)
}

func configuredSMTPNotifiers() (authrecovery.ResetNotifier, collaboration.InvitationNotifier, error) {
	host := strings.TrimSpace(os.Getenv("SMTP_HOST"))
	portValue := strings.TrimSpace(os.Getenv("SMTP_PORT"))
	username := strings.TrimSpace(os.Getenv("SMTP_USERNAME"))
	password := strings.TrimSpace(os.Getenv("SMTP_PASSWORD"))
	from := strings.TrimSpace(os.Getenv("SMTP_FROM"))
	tlsMode := strings.TrimSpace(os.Getenv("SMTP_TLS_MODE"))
	resetURL := strings.TrimSpace(os.Getenv("AUTH_RECOVERY_RESET_BASE_URL"))
	acceptURL := strings.TrimSpace(os.Getenv("COLLABORATION_ACCEPT_BASE_URL"))
	configured := host != "" || portValue != "" || username != "" || password != "" || from != "" || tlsMode != "" || resetURL != "" || acceptURL != ""
	if !configured {
		return nil, nil, nil
	}
	port, err := strconv.Atoi(portValue)
	if err != nil || port <= 0 || host == "" || username == "" || password == "" || from == "" || tlsMode == "" {
		return nil, nil, errors.New("SMTP delivery configuration is incomplete")
	}
	var recoveryNotifier authrecovery.ResetNotifier
	if resetURL != "" {
		recoveryNotifier, err = authrecovery.NewSMTPNotifier(authrecovery.SMTPNotifierConfig{
			Host: host, Port: port, Username: username, Password: password, From: from,
			ResetBaseURL: resetURL, TLSMode: tlsMode,
		})
		if err != nil {
			return nil, nil, err
		}
	}
	var invitationNotifier collaboration.InvitationNotifier
	if acceptURL != "" {
		invitationNotifier, err = collaboration.NewSMTPNotifier(collaboration.SMTPNotifierConfig{
			Host: host, Port: port, Username: username, Password: password, From: from,
			AcceptBaseURL: acceptURL, TLSMode: tlsMode,
		})
		if err != nil {
			return nil, nil, err
		}
	}
	return recoveryNotifier, invitationNotifier, nil
}

func startAuthRecoveryDispatcher(dispatcher *authrecovery.DeliveryDispatcher) {
	go func() {
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			_, err := dispatcher.DispatchOne(ctx)
			cancel()
			if err != nil {
				log.Printf("auth recovery delivery attempt failed")
			}
		}
	}()
}

func newAuthReader(databaseURL string) (auth.Reader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return auth.NewDisabledReader(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return auth.NewSQLReader(auth.SQLReaderConfig{
		Queryer: auth.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newPasswordAuthenticator(databaseURL string) (auth.PasswordAuthenticator, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := auth.NewSQLDBQueryer(db)
	return auth.NewSQLPasswordAuthenticator(auth.SQLPasswordAuthenticatorConfig{
		Queryer: queryer,
		Reader:  auth.NewSQLReader(auth.SQLReaderConfig{Queryer: queryer}),
	}), db.Close, nil
}

func newPasswordChanger(databaseURL string) (auth.PasswordChanger, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := auth.NewSQLDBQueryer(db)
	return auth.NewSQLPasswordChanger(auth.SQLPasswordChangerConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newAuthSessionStore(databaseURL string) (auth.SessionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWriterAdmissionStore(workflows.SQLWriterAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
		DB:     db,
	}), db.Close, nil
}

func newWriterThreadStore(databaseURL string) (workflows.WriterThreadStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWriterThreadStore(db), db.Close, nil
}

func newDraftAdoptionStore(databaseURL string) (workflows.DraftAdoptionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	// Outbox hook is attached after asset distillation store is available (see wireDraftAdoptionOutbox).
	return workflows.NewSQLDraftAdoptionStore(workflows.SQLDraftAdoptionStoreConfig{
		Queryer: workflows.NewSQLDBWriterDraftAdoptionQueryer(db),
	}), db.Close, nil
}

func attachDraftAdoptionOutbox(store workflows.DraftAdoptionStore, hook workflows.DraftAdoptionOutboxHook) {
	if sqlStore, ok := store.(*workflows.SQLDraftAdoptionStore); ok && hook != nil {
		sqlStore.SetOutboxHook(hook)
	}
}

func newDraftReviewStore(databaseURL string) (workflows.DraftReviewStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledDraftReviewStore(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLDraftReviewStore(workflows.SQLDraftReviewStoreConfig{
		Execer:  workflows.NewSQLDBWriterAdmissionExecer(db),
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newDraftReviewRuntimeStores(databaseURL string) (
	*workflows.SQLDraftReviewRuntimeStore,
	workflows.DraftReviewIssueStore,
	func() error,
	error,
) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, nil, err
	}
	return workflows.NewSQLDraftReviewRuntimeStore(db), workflows.NewSQLDraftReviewIssueStore(db), db.Close, nil
}

func newSeedAdmissionStore(databaseURL string) (workflows.SeedAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLSeedAdmissionStore(workflows.SQLSeedAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
	}), db.Close, nil
}

func newAnalysisAdmissionStore(databaseURL string) (workflows.AnalysisAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLAnalysisAdmissionStore(workflows.SQLAnalysisAdmissionStoreConfig{
		Execer: workflows.NewSQLDBWriterAdmissionExecer(db),
		DB:     db,
	}), db.Close, nil
}

func newAnalysisReaders(databaseURL string) (
	workflows.AnalysisRunReader,
	workflows.AnalysisEventReader,
	workflows.AnalysisWorkspaceReader,
	workflows.AnalysisCandidateReader,
	workflows.AnalysisAssetImporter,
	func() error,
	error,
) {
	if strings.TrimSpace(databaseURL) == "" {
		return &disabledAnalysisRunReaderMain{},
			workflows.NewDisabledAnalysisEventReader(),
			workflows.NewDisabledAnalysisWorkspaceReader(),
			workflows.NewDisabledAnalysisCandidateReader(),
			workflows.NewDisabledAnalysisAssetImporter(),
			nil,
			nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, nil, nil, nil, nil, err
	}
	queryer := workflows.NewSQLDBWriterEventQueryer(db)
	return workflows.NewSQLAnalysisRunReader(workflows.SQLAnalysisRunReaderConfig{Queryer: queryer}),
		workflows.NewSQLAnalysisEventReader(workflows.SQLAnalysisEventReaderConfig{Queryer: queryer}),
		workflows.NewSQLAnalysisWorkspaceReader(workflows.SQLAnalysisWorkspaceReaderConfig{Queryer: queryer}),
		workflows.NewSQLAnalysisCandidateReader(workflows.SQLAnalysisCandidateReaderConfig{Queryer: queryer}),
		workflows.NewSQLAnalysisAssetImporter(db),
		db.Close,
		nil
}

type disabledAnalysisRunReaderMain struct{}

func (r *disabledAnalysisRunReaderMain) ListAnalysisRuns(context.Context, workflows.ListAnalysisRunsInput) ([]workflows.AnalysisRun, error) {
	return nil, &workflows.AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis run reader is not configured"}
}

func (r *disabledAnalysisRunReaderMain) GetAnalysisRun(context.Context, workflows.GetAnalysisRunInput) (workflows.AnalysisRun, error) {
	return workflows.AnalysisRun{}, &workflows.AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis run reader is not configured"}
}

func newAssetIngestionAdmissionStore(databaseURL string) (workflows.AssetIngestionAdmissionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLManuscriptReader(workflows.SQLManuscriptReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newManuscriptArtifactExporter(databaseURL string) (workflows.ManuscriptArtifactExporter, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLManuscriptArtifactExporter(workflows.SQLManuscriptArtifactExporterConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}

func newWorkflowReader(databaseURL string) (workflows.WorkflowReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWorkflowReader(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return storygraph.NewSQLReader(storygraph.SQLReaderConfig{
		Queryer: storygraph.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newStoryGraphCandidateAdoptionStore(databaseURL string) (storygraph.CandidateAdoptionStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return storygraph.NewDisabledCandidateAdoptionStore(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return storygraph.NewSQLCandidateAdoptionStore(storygraph.SQLCandidateAdoptionStoreConfig{
		Queryer: storygraph.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineSavedPathReader(databaseURL string) (worldline.SavedPathReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledSavedPathReader(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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

func newWorldlineStepStarter(temporalClient worldline.TemporalWorkflowClient, databaseURL string, taskQueue string) (worldline.StepStarter, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" || temporalClient == nil {
		return worldline.NewDisabledStepStarter(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	return worldline.NewSQLStepStarter(worldline.SQLStepStarterConfig{
		Execer:    queryer,
		Client:    temporalClient,
		TaskQueue: taskQueue,
	}), db.Close, nil
}

func newWorldlineAutoEvolutionStarter(
	temporalClient worldline.TemporalWorkflowClient,
	databaseURL string,
	taskQueue string,
) (worldline.AutoEvolutionStarter, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" || temporalClient == nil {
		return worldline.NewDisabledAutoEvolutionStarter(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLAutoEvolutionStarter(worldline.SQLAutoEvolutionStarterConfig{
		Store:     worldline.NewSQLAutoEvolutionAdmissionStore(db),
		Client:    temporalClient,
		TaskQueue: taskQueue,
	}), db.Close, nil
}

func newWorldlinePreparationStore(databaseURL string) (worldline.PreparationStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledPreparationStore(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := worldline.NewSQLDBQueryer(db)
	return worldline.NewSQLPreparationStore(worldline.SQLPreparationStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newWorldlinePreparationStarter(
	temporalClient worldline.TemporalWorkflowClient,
	databaseURL string,
	taskQueue string,
) (worldline.PreparationStarter, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" || temporalClient == nil {
		return worldline.NewDisabledPreparationStarter(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLPreparationStarter(worldline.SQLPreparationStarterConfig{
		Store:     worldline.NewSQLPreparationAdmissionStore(db),
		Client:    temporalClient,
		TaskQueue: taskQueue,
	}), db.Close, nil
}

func newWorldlineGoalStartStarter(
	temporalClient worldline.TemporalWorkflowClient,
	databaseURL string,
	taskQueue string,
) (worldline.GoalStartStarter, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" || temporalClient == nil {
		return worldline.NewDisabledGoalStartStarter(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLGoalStartStarter(worldline.SQLGoalStartStarterConfig{
		Store:     worldline.NewSQLGoalStartAdmissionStore(db),
		Client:    temporalClient,
		TaskQueue: taskQueue,
	}), db.Close, nil
}

func newWorldlineGoalStartReader(databaseURL string) (worldline.GoalStartReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledGoalStartReader(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return worldline.NewSQLGoalStartReader(worldline.SQLGoalStartReaderConfig{
		Queryer: worldline.NewSQLDBQueryer(db),
	}), db.Close, nil
}

func newWorldlineTimelineReader(databaseURL string) (worldline.TimelineReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return worldline.NewDisabledTimelineReader(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	queryer := characterconsole.NewSQLDBQueryer(db)
	return characterconsole.NewSQLStore(characterconsole.SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	}), db.Close, nil
}

func newCharacterProposalStore(databaseURL string) (characterconsole.ProposalStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return characterconsole.NewDisabledProposalStore(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return characterconsole.NewSQLProposalStore(db, 100), db.Close, nil
}

func newCharacterDialogueStarter(
	temporalClient workflows.TemporalWorkflowClient,
	databaseURL string,
	taskQueue string,
) (workflows.CharacterDialogueStarter, func() error, error) {
	if temporalClient == nil || strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledCharacterDialogueStarter(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewTemporalCharacterDialogueStarter(workflows.TemporalCharacterDialogueConfig{
		Client:         temporalClient,
		TaskQueue:      taskQueue,
		AdmissionStore: workflows.NewSQLCharacterDialogueAdmissionStore(db),
	}), db.Close, nil
}

func newWorkflowCanceller(temporalClient workflows.TemporalWorkflowClient, databaseURL string) (workflows.WorkflowCanceller, func() error, error) {
	if temporalClient == nil || strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWorkflowCanceller(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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

func newWorkflowRetrier(temporalClient workflows.TemporalWorkflowClient, databaseURL string, seedTaskQueue string) (workflows.WorkflowRetrier, func() error, error) {
	if temporalClient == nil || strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledWorkflowRetrier(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	store := workflows.NewSQLWorkflowRetryStore(workflows.SQLWorkflowRetryStoreConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
		Execer:  workflows.NewSQLDBWriterAdmissionExecer(db),
	})
	return workflows.NewTemporalWorkflowRetrier(workflows.TemporalWorkflowRetrierConfig{
		Client:    temporalClient,
		Store:     store,
		TaskQueue: seedTaskQueue,
	}), db.Close, nil
}

func newSeedSegmentRetrier(
	temporalClient workflows.TemporalWorkflowClient,
	databaseURL string,
	seedTaskQueue string,
) (workflows.SeedSegmentRetrier, func() error, error) {
	if temporalClient == nil || strings.TrimSpace(databaseURL) == "" {
		return workflows.NewDisabledSeedSegmentRetrier(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLSeedSegmentRetrier(workflows.SQLSeedSegmentRetrierConfig{
		Execer:    workflows.NewSQLDBWriterAdmissionExecer(db),
		Client:    temporalClient,
		TaskQueue: seedTaskQueue,
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
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return sourcefiles.NewSQLStore(sourcefiles.SQLStoreConfig{
		Queryer:        sourcefiles.NewSQLDBQueryer(db),
		ObjectVerifier: objectVerifier,
	}), db.Close, nil
}

type assetReaderBundle struct {
	Reader                 assets.Reader
	QueryEmbeddingResolver assets.QueryEmbeddingResolver
	SearchIndexChecker     assets.SearchIndexChecker
}

func newAssetReaderBundle(databaseURL string) (assetReaderBundle, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assetReaderBundle{Reader: assets.NewDisabledReader()}, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return assetReaderBundle{}, nil, err
	}
	queryer := assets.NewSQLDBQueryer(db)
	baseReader := assets.NewSQLReader(assets.SQLReaderConfig{Queryer: queryer})
	resolver := assets.NewSQLQueryEmbeddingResolver(assets.SQLQueryEmbeddingResolverConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: os.Getenv("LLM_CREDENTIAL_ENCRYPTION_KEY"),
	})
	return assetReaderBundle{
		Reader: assets.NewPublicSearchReader(assets.PublicSearchReaderConfig{
			Base:     baseReader,
			Resolver: resolver,
			Provider: assets.NewOpenAICompatibleQueryEmbeddingProvider(nil),
			Index:    baseReader,
		}),
		QueryEmbeddingResolver: resolver,
		SearchIndexChecker:     baseReader,
	}, db.Close, nil
}

func newLLMQuotaStore(databaseURL string) (llm.QuotaPolicyStore, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, nil, nil
	}
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return llm.NewSQLQuotaStore(db), db.Close, nil
}

func newArchiveMemoryReader(databaseURL string) (assets.ArchiveMemoryReader, func() error, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return assets.NewDisabledArchiveMemoryReader(), nil, nil
	}
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
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
	db, err := openAppDatabase(databaseURL)
	if err != nil {
		return nil, nil, err
	}
	return workflows.NewSQLWriterEventReader(workflows.SQLWriterEventReaderConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(db),
	}), db.Close, nil
}
