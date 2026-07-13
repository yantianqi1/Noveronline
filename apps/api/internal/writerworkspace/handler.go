package writerworkspace

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"mirofish-novel/apps/api/internal/writerplanning"
)

type HandlerConfig struct {
	Store       Store
	Actors      ActorResolver
	Authorizer  Authorizer
	OwnerLookup OwnerProjectLookup
	Planning    writerplanning.Starter
}
type Handler struct {
	store       Store
	actors      ActorResolver
	authorizer  Authorizer
	ownerLookup OwnerProjectLookup
	planning    writerplanning.Starter
}

func NewHandler(c HandlerConfig) *Handler {
	lookup := c.OwnerLookup
	if lookup == nil {
		lookup, _ = c.Store.(OwnerProjectLookup)
	}
	return &Handler{store: c.Store, actors: c.Actors, authorizer: c.Authorizer, ownerLookup: lookup, planning: c.Planning}
}

type envelope struct {
	Data  any          `json:"data,omitempty"`
	Error *publicError `json:"error,omitempty"`
}
type publicError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func writeErr(w http.ResponseWriter, err error) {
	code := ErrorCode(err)
	status := http.StatusInternalServerError
	message := "writer workspace query failed"
	switch code {
	case CodeValidationFailed, CodeReorderInvalid:
		status = http.StatusBadRequest
		message = err.Error()
	case CodeNotFound:
		status = http.StatusNotFound
		message = "writer workspace resource not found"
	case CodeConflict:
		status = http.StatusConflict
		message = "writer workspace version conflict"
	case CodeAccessDenied:
		status = http.StatusForbidden
		message = "writer workspace access denied"
	}
	writeJSON(w, status, envelope{Error: &publicError{Code: code, Message: message}})
}
func decode(r *http.Request, v any) error {
	d := json.NewDecoder(http.MaxBytesReader(nilReaderWriter{}, r.Body, 2<<20))
	d.DisallowUnknownFields()
	if d.Decode(v) != nil {
		return coded(CodeValidationFailed, "invalid request body")
	}
	return nil
}

type nilReaderWriter struct{}

func (nilReaderWriter) Header() http.Header       { return http.Header{} }
func (nilReaderWriter) Write([]byte) (int, error) { return 0, nil }
func (nilReaderWriter) WriteHeader(int)           {}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if h.store == nil || h.actors == nil || h.authorizer == nil {
		writeErr(w, stableDBError())
		return
	}
	actor, err := h.actors.ResolveActor(r.Context(), r)
	if err != nil || actor.TenantID == "" || actor.UserID == "" {
		writeErr(w, coded(CodeAccessDenied, "writer workspace access denied"))
		return
	}
	parts := splitPath(r.URL.Path)
	if len(parts) < 2 || parts[0] != "v1" {
		http.NotFound(w, r)
		return
	}
	projectID, tenantScoped, err := h.resolveAuthorizationScope(r, actor, parts)
	if err != nil {
		writeErr(w, err)
		return
	}
	if len(parts) >= 3 && parts[1] == "tenants" && parts[2] != actor.TenantID {
		writeErr(w, coded(CodeAccessDenied, "writer workspace access denied"))
		return
	}
	private := r.URL.Query().Get("include_private") == "true"
	op := OperationRead
	if tenantScoped {
		op = OperationTenantPresetManage
	} else if r.Method != "GET" {
		op = OperationWrite
	} else if private {
		op = OperationPrivateRead
	}
	if err = h.authorizer.Authorize(r.Context(), AuthorizeInput{Actor: actor, ProjectID: projectID, Operation: op}); err != nil {
		writeErr(w, coded(CodeAccessDenied, "writer workspace access denied"))
		return
	}
	scope := Scope{TenantID: actor.TenantID, ProjectID: projectID, ActorUserID: actor.UserID, RequestID: actor.RequestID}
	h.route(w, r, scope, parts, private)
}

func (h *Handler) resolveAuthorizationScope(r *http.Request, actor Actor, parts []string) (string, bool, error) {
	if len(parts) >= 3 && parts[1] == "projects" {
		if strings.TrimSpace(parts[2]) == "" {
			return "", false, coded(CodeValidationFailed, "trusted project context is required")
		}
		return parts[2], false, nil
	}
	if len(parts) >= 4 && parts[1] == "tenants" && parts[3] == "writer-presets" {
		return "", true, nil
	}
	kind, resourceID, ok := globalResource(parts)
	if !ok || h.ownerLookup == nil {
		return "", false, coded(CodeAccessDenied, "writer workspace access denied")
	}
	owner, err := h.ownerLookup.LookupResourceOwner(r.Context(), OwnerLookupInput{
		TenantID: actor.TenantID, ActorUserID: actor.UserID, Kind: kind, ResourceID: resourceID,
	})
	if err != nil {
		return "", false, coded(CodeAccessDenied, "writer workspace access denied")
	}
	if owner.TenantScoped {
		if kind != ResourceWriterPreset {
			return "", false, coded(CodeAccessDenied, "writer workspace access denied")
		}
		return "", true, nil
	}
	if strings.TrimSpace(owner.ProjectID) == "" {
		return "", false, coded(CodeAccessDenied, "writer workspace access denied")
	}
	return owner.ProjectID, false, nil
}

func globalResource(parts []string) (ResourceKind, string, bool) {
	if len(parts) < 3 || strings.TrimSpace(parts[2]) == "" {
		return "", "", false
	}
	kinds := map[string]ResourceKind{
		"chapters": ResourceChapter, "scenes": ResourceScene,
		"outline-versions": ResourceOutline, "book-plans": ResourceBookPlan,
		"writer-presets": ResourceWriterPreset, "forbidden-lexicon": ResourceLexiconEntry,
	}
	kind, ok := kinds[parts[1]]
	return kind, parts[2], ok
}
func splitPath(path string) []string {
	raw := strings.Split(strings.Trim(path, "/"), "/")
	for _, p := range raw {
		if p == "" {
			return nil
		}
	}
	return raw
}
func parseExpected(r *http.Request) (int64, error) {
	v := r.URL.Query().Get("expected_version")
	n, e := strconv.ParseInt(v, 10, 64)
	if e != nil || n <= 0 {
		return 0, coded(CodeValidationFailed, "expected_version is required")
	}
	return n, nil
}
func (h *Handler) route(w http.ResponseWriter, r *http.Request, s Scope, p []string, private bool) {
	ctx := r.Context()
	created := func(v any) { writeJSON(w, http.StatusCreated, envelope{Data: v}) }
	ok := func(v any) { writeJSON(w, http.StatusOK, envelope{Data: v}) }
	noContent := func() { w.WriteHeader(http.StatusNoContent) }
	if len(p) >= 4 && p[1] == "projects" && p[3] == "chapters" {
		if len(p) == 4 && r.Method == "GET" {
			v, e := h.store.ListChapters(ctx, s)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 4 && r.Method == "POST" {
			var b struct {
				Title   string `json:"title"`
				Status  string `json:"status"`
				Brief   string `json:"brief"`
				Outline string `json:"outline"`
				Content string `json:"content_text"`
				Order   *int
			}
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.CreateChapter(ctx, CreateChapterInput{Scope: s, Title: b.Title, Status: b.Status, Brief: b.Brief, Outline: b.Outline, Content: b.Content, Order: b.Order})
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
		if len(p) == 5 && p[4] == "reorder" && r.Method == "POST" {
			var b struct {
				OrderedIDs []string `json:"ordered_ids"`
			}
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			if e := h.store.ReorderChapters(ctx, s, b.OrderedIDs); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
	}
	if len(p) >= 3 && p[1] == "chapters" {
		id := p[2]
		if len(p) == 3 && r.Method == "GET" {
			v, e := h.store.GetChapter(ctx, s, id, private)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 3 && r.Method == "PATCH" {
			var b ChapterPatch
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.UpdateChapter(ctx, s, id, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 3 && r.Method == "DELETE" {
			v, e := parseExpected(r)
			if e != nil {
				writeErr(w, e)
				return
			}
			if e = h.store.DeleteChapter(ctx, s, id, v); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
		if len(p) == 4 && p[3] == "versions" && r.Method == "GET" {
			v, e := h.store.ListChapterVersions(ctx, s, id, private)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 4 && p[3] == "scenes" && r.Method == "GET" {
			v, e := h.store.ListScenes(ctx, s, id)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 4 && p[3] == "scenes" && r.Method == "POST" {
			var b struct {
				Title   string `json:"title"`
				Status  string `json:"status"`
				Brief   string `json:"brief"`
				Outline string `json:"outline"`
				Content string `json:"content_text"`
				Order   *int
			}
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.CreateScene(ctx, CreateSceneInput{Scope: s, ChapterID: id, Title: b.Title, Status: b.Status, Brief: b.Brief, Outline: b.Outline, Content: b.Content, Order: b.Order})
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
		if len(p) == 5 && p[3] == "scenes" && p[4] == "reorder" && r.Method == "POST" {
			var b struct {
				OrderedIDs []string `json:"ordered_ids"`
			}
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			if e := h.store.ReorderScenes(ctx, s, id, b.OrderedIDs); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
	}
	if len(p) >= 3 && p[1] == "scenes" {
		id := p[2]
		if len(p) == 3 && r.Method == "GET" {
			v, e := h.store.GetScene(ctx, s, id, private)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 3 && r.Method == "PATCH" {
			var b ScenePatch
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.UpdateScene(ctx, s, id, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 3 && r.Method == "DELETE" {
			v, e := parseExpected(r)
			if e != nil {
				writeErr(w, e)
				return
			}
			if e = h.store.DeleteScene(ctx, s, id, v); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
		if len(p) == 4 && p[3] == "versions" && r.Method == "GET" {
			v, e := h.store.ListSceneVersions(ctx, s, id, private)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
	}
	if len(p) >= 4 && p[1] == "projects" && p[3] == "outlines" {
		if r.Method == "GET" {
			v, e := h.store.ListOutlines(ctx, s, r.URL.Query().Get("scope_type"), r.URL.Query().Get("scope_id"))
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "POST" {
			var b CreateOutlineInput
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			b.Scope = s
			v, e := h.store.CreateOutline(ctx, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
	}
	if len(p) == 4 && p[1] == "outline-versions" && p[3] == "restore" && r.Method == "POST" {
		v, e := h.store.RestoreOutline(ctx, s, p[2])
		if e != nil {
			writeErr(w, e)
			return
		}
		created(v)
		return
	}
	if len(p) >= 4 && p[1] == "projects" && p[3] == "book-plans" {
		if len(p) == 6 && p[5] == "generations" && r.Method == "POST" {
			if h.planning == nil {
				writePlanningErr(w, &writerplanning.AppError{Code: "WRITER_PLANNING_BACKEND_UNCONFIGURED", Message: "writer planning backend is not configured"})
				return
			}
			var b struct {
				ExpectedVersion int64 `json:"expected_version"`
			}
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.planning.Start(ctx, writerplanning.StartInput{
				TenantID: s.TenantID, ProjectID: s.ProjectID, ActorUserID: s.ActorUserID,
				RequestID: s.RequestID, Kind: writerplanning.KindBookPlan,
				BookPlanID: p[4], ExpectedVersion: b.ExpectedVersion,
			})
			if e != nil {
				writePlanningErr(w, e)
				return
			}
			writeJSON(w, http.StatusAccepted, envelope{Data: v})
			return
		}
		if len(p) == 4 && r.Method == "GET" {
			v, e := h.store.ListBookPlans(ctx, s)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 4 && r.Method == "POST" {
			var b BookPlan
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.CreateBookPlan(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
	}
	if len(p) >= 3 && p[1] == "book-plans" {
		id := p[2]
		if len(p) == 3 && r.Method == "GET" {
			v, e := h.store.GetBookPlan(ctx, s, id)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 3 && r.Method == "PATCH" {
			var b BookPlanPatch
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.UpdateBookPlan(ctx, s, id, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 3 && r.Method == "DELETE" {
			v, e := parseExpected(r)
			if e != nil {
				writeErr(w, e)
				return
			}
			if e = h.store.DeleteBookPlan(ctx, s, id, v); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
		if len(p) == 4 && p[3] == "events" && r.Method == "GET" {
			after, _ := strconv.Atoi(r.URL.Query().Get("after_sequence"))
			v, e := h.store.ListBookRunEvents(ctx, s, id, after)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if len(p) == 4 && p[3] == "events" && r.Method == "POST" {
			var b BookRunEvent
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			b.BookPlanID = id
			v, e := h.store.AppendBookRunEvent(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
		if len(p) == 4 && p[3] == "runs" && r.Method == "POST" {
			var b AdmitBookRunInput
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.AdmitBookRun(ctx, s, id, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
	}
	if len(p) >= 4 && p[1] == "projects" && p[3] == "writer-presets" {
		if r.Method == "GET" {
			v, e := h.store.ListPresets(ctx, s)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "POST" {
			var b WriterPreset
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			b.Scope = "project"
			b.ProjectID = s.ProjectID
			v, e := h.store.UpsertPreset(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
	}
	if len(p) == 4 && p[1] == "tenants" && p[3] == "writer-presets" {
		if r.Method == "POST" {
			var b WriterPreset
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			b.Scope = "tenant"
			b.ProjectID = ""
			v, e := h.store.UpsertPreset(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
	}
	if len(p) == 3 && p[1] == "writer-presets" {
		if r.Method == "GET" {
			v, e := h.store.GetPreset(ctx, s, p[2])
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "PATCH" {
			var b WriterPreset
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			b.PresetID = p[2]
			existing, e := h.store.GetPreset(ctx, s, p[2])
			if e != nil {
				writeErr(w, e)
				return
			}
			b.Scope = existing.Scope
			b.ProjectID = existing.ProjectID
			v, e := h.store.UpsertPreset(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "DELETE" {
			if e := h.store.DeletePreset(ctx, s, p[2]); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
	}
	if len(p) >= 4 && p[1] == "projects" && p[3] == "forbidden-lexicon" {
		if r.Method == "GET" {
			v, e := h.store.ListLexicon(ctx, s)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "POST" {
			var b ForbiddenEntry
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			v, e := h.store.UpsertLexicon(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			created(v)
			return
		}
	}
	if len(p) == 3 && p[1] == "forbidden-lexicon" {
		if r.Method == "GET" {
			v, e := h.store.GetLexicon(ctx, s, p[2])
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "PATCH" {
			var b ForbiddenEntry
			if e := decode(r, &b); e != nil {
				writeErr(w, e)
				return
			}
			b.EntryID = p[2]
			v, e := h.store.UpsertLexicon(ctx, s, b)
			if e != nil {
				writeErr(w, e)
				return
			}
			ok(v)
			return
		}
		if r.Method == "DELETE" {
			if e := h.store.DeleteLexicon(ctx, s, p[2]); e != nil {
				writeErr(w, e)
				return
			}
			noContent()
			return
		}
	}
	http.NotFound(w, r)
}

func writePlanningErr(w http.ResponseWriter, err error) {
	code := writerplanning.ErrorCode(err)
	status, message := http.StatusInternalServerError, "writer planning request failed"
	switch code {
	case "VALIDATION_FAILED":
		status, message = http.StatusBadRequest, "invalid writer planning request"
	case "BOOK_PLAN_NOT_FOUND":
		status, message = http.StatusNotFound, "book plan was not found"
	case "BOOK_PLAN_CONFLICT", "IDEMPOTENCY_CONFLICT":
		status, message = http.StatusConflict, "book plan generation state changed"
	case "WRITER_PLANNING_BACKEND_UNCONFIGURED":
		status, message = http.StatusServiceUnavailable, "writer planning backend is not configured"
	case "WRITER_PLANNING_START_FAILED":
		status, message = http.StatusBadGateway, "writer planning workflow failed to start"
	}
	writeJSON(w, status, envelope{Error: &publicError{Code: code, Message: message}})
}
