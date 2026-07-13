package httpapi

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRetiredLegacyAndDeferredReleaseRoutesAreNotMountedBySaaS(t *testing.T) {
	server := NewServer(Config{})
	for _, test := range []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/v1/auth/oauth"},
		{http.MethodPost, "/v1/auth/mfa"},
		{http.MethodGet, "/api/v2/chapter-context/options"},
		{http.MethodPost, "/api/v2/chapter-context/builds"},
		{http.MethodPost, "/api/v2/drafts"},
		{http.MethodPost, "/api/v2/drafts/draft-id/events"},
		{http.MethodPost, "/api/v2/drafts/draft-id/revisions"},
		{http.MethodPost, "/api/v2/drafts/draft-id/finalizations"},
		{http.MethodPost, "/api/writer-agent/world-update"},
		{http.MethodGet, "/v1/worldline-sessions/session-id/branches"},
		{http.MethodGet, "/v1/worldline-sessions/session-id/comparison"},
	} {
		t.Run(test.method+" "+test.path, func(t *testing.T) {
			response := httptest.NewRecorder()
			server.ServeHTTP(response, httptest.NewRequest(test.method, test.path, nil))
			if response.Code != http.StatusNotFound {
				t.Fatalf("retired route became public: status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}
